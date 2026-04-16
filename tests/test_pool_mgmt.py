"""Tests for pool member management operations."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


SAMPLE_POOL = {
    "name": "web-pool",
    "uuid": "pool-1",
    "servers": [
        {"ip": {"addr": "10.0.0.11"}, "port": 8080, "enabled": True, "ratio": 1},
        {"ip": {"addr": "10.0.0.12"}, "port": 8080, "enabled": True, "ratio": 2},
    ],
}


def _pool_list_session(
    mock_avi_session: MagicMock,
    *,
    inventory: list[dict],
    pools: list[dict],
    poolgroups: dict[str, dict] | None = None,
) -> None:
    """Wire up session.get to dispatch by path for list_pools scenarios."""
    poolgroups = poolgroups or {}

    def _dispatch(path: str, *args, **kwargs) -> MagicMock:
        resp = MagicMock()
        if path == "virtualservice-inventory":
            resp.json.return_value = {"results": inventory}
        elif path == "pool":
            resp.json.return_value = {"results": pools}
        elif path.startswith("poolgroup/"):
            pg_uuid = path.split("/", 1)[1]
            resp.json.return_value = poolgroups.get(pg_uuid, {})
        else:
            resp.json.return_value = {}
        return resp

    mock_avi_session.get.side_effect = _dispatch


@pytest.mark.unit
class TestListPools:
    """pool_mgmt.list_pools — especially the vs_filter matching logic."""

    @pytest.mark.usefixtures("_patch_avi_connect")
    def test_no_filter_shows_all_pools(self, mock_avi_session: MagicMock) -> None:
        _pool_list_session(
            mock_avi_session,
            inventory=[],
            pools=[SAMPLE_POOL, {**SAMPLE_POOL, "name": "db-pool", "uuid": "pool-2"}],
        )
        from vmware_avi.ops.pool_mgmt import list_pools
        list_pools()
        # virtualservice-inventory must NOT be queried when no filter is set.
        called_paths = [c.args[0] for c in mock_avi_session.get.call_args_list]
        assert "virtualservice-inventory" not in called_paths

    @pytest.mark.usefixtures("_patch_avi_connect")
    def test_filter_uses_inventory_endpoint_not_virtualservice(
        self, mock_avi_session: MagicMock,
    ) -> None:
        """The bug: /virtualservice omits pool_ref for K8S/policy-driven
        VSes (always empty string), so filtering off it matches zero pools.
        /virtualservice-inventory exposes the real pool graph via
        top-level pools[] / poolgroups[] arrays — must use that."""
        _pool_list_session(
            mock_avi_session,
            inventory=[
                {
                    "config": {"name": "web-vs"},
                    "pools": ["/api/pool/pool-1"],
                    "poolgroups": [],
                },
            ],
            pools=[SAMPLE_POOL],
        )
        from vmware_avi.ops.pool_mgmt import list_pools
        list_pools(vs_filter="web")

        called_paths = [c.args[0] for c in mock_avi_session.get.call_args_list]
        assert "virtualservice-inventory" in called_paths
        # The buggy codepath hit /virtualservice with a fields= param —
        # guard against its return.
        for call in mock_avi_session.get.call_args_list:
            if call.args[0] == "virtualservice":
                pytest.fail(
                    "list_pools queried /virtualservice; pool_ref is empty "
                    "on K8S/policy-driven VSes so this always misses.",
                )

    @pytest.mark.usefixtures("_patch_avi_connect")
    def test_filter_matches_pool_via_direct_ref(
        self, mock_avi_session: MagicMock,
    ) -> None:
        _pool_list_session(
            mock_avi_session,
            inventory=[
                {
                    "config": {"name": "web-vs"},
                    "pools": ["/api/pool/pool-1"],
                    "poolgroups": [],
                },
                {
                    "config": {"name": "db-vs"},
                    "pools": ["/api/pool/pool-2"],
                    "poolgroups": [],
                },
            ],
            pools=[
                SAMPLE_POOL,  # pool-1 / web-pool
                {**SAMPLE_POOL, "name": "db-pool", "uuid": "pool-2"},
            ],
        )
        from vmware_avi.ops.pool_mgmt import list_pools
        # Should include only the pool referenced by web-vs, not db-vs.
        list_pools(vs_filter="web")

    @pytest.mark.usefixtures("_patch_avi_connect")
    def test_filter_resolves_pool_group_members(
        self, mock_avi_session: MagicMock,
    ) -> None:
        _pool_list_session(
            mock_avi_session,
            inventory=[
                {
                    "config": {"name": "canary-vs"},
                    "pools": [],
                    "poolgroups": ["/api/poolgroup/poolgroup-pg1"],
                },
            ],
            pools=[
                SAMPLE_POOL,  # pool-1 — member of the pool group
                {**SAMPLE_POOL, "name": "unrelated", "uuid": "pool-99"},
            ],
            poolgroups={
                "poolgroup-pg1": {
                    "members": [{"pool_ref": "/api/pool/pool-1"}],
                },
            },
        )
        from vmware_avi.ops.pool_mgmt import list_pools
        list_pools(vs_filter="canary")
        called_paths = [c.args[0] for c in mock_avi_session.get.call_args_list]
        assert any(p == "poolgroup/poolgroup-pg1" for p in called_paths), \
            "expected poolgroup membership to be resolved for VSes with poolgroups"


@pytest.mark.unit
class TestListPoolMembers:
    """pool_mgmt.list_pool_members — lists members of a pool."""

    @pytest.mark.usefixtures("_patch_avi_connect")
    def test_pool_not_found(self, mock_avi_session: MagicMock) -> None:
        mock_avi_session.get_object_by_name.return_value = None
        from vmware_avi.ops.pool_mgmt import list_pool_members
        with pytest.raises(SystemExit):
            list_pool_members("missing-pool")

    @pytest.mark.usefixtures("_patch_avi_connect")
    def test_pool_with_members(self, mock_avi_session: MagicMock) -> None:
        mock_avi_session.get_object_by_name.return_value = SAMPLE_POOL
        from vmware_avi.ops.pool_mgmt import list_pool_members
        list_pool_members("web-pool")
        mock_avi_session.get_object_by_name.assert_called_once_with("pool", "web-pool")


@pytest.mark.unit
class TestTogglePoolMember:
    """pool_mgmt.toggle_pool_member — enable/disable with double_confirm."""

    @pytest.mark.usefixtures("_patch_avi_connect")
    def test_enable_member(self, mock_avi_session: MagicMock) -> None:
        pool = {**SAMPLE_POOL, "servers": [{**s} for s in SAMPLE_POOL["servers"]]}
        mock_avi_session.get_object_by_name.return_value = pool
        from vmware_avi.ops.pool_mgmt import toggle_pool_member
        toggle_pool_member("web-pool", "10.0.0.11", enable=True)
        mock_avi_session.put.assert_called_once()

    @pytest.mark.usefixtures("_patch_avi_connect")
    def test_disable_member_cancelled(self, mock_avi_session: MagicMock) -> None:
        with patch("vmware_avi._safety.double_confirm", return_value=False):
            from vmware_avi.ops.pool_mgmt import toggle_pool_member
            toggle_pool_member("web-pool", "10.0.0.11", enable=False)
            mock_avi_session.put.assert_not_called()

    @pytest.mark.usefixtures("_patch_avi_connect")
    def test_disable_member_confirmed(self, mock_avi_session: MagicMock) -> None:
        pool = {**SAMPLE_POOL, "servers": [{**s} for s in SAMPLE_POOL["servers"]]}
        mock_avi_session.get_object_by_name.return_value = pool
        with patch("vmware_avi._safety.double_confirm", return_value=True):
            from vmware_avi.ops.pool_mgmt import toggle_pool_member
            toggle_pool_member("web-pool", "10.0.0.11", enable=False)
            mock_avi_session.put.assert_called_once()

    @pytest.mark.usefixtures("_patch_avi_connect")
    def test_server_not_found_in_pool(self, mock_avi_session: MagicMock) -> None:
        mock_avi_session.get_object_by_name.return_value = SAMPLE_POOL
        from vmware_avi.ops.pool_mgmt import toggle_pool_member
        with pytest.raises(SystemExit):
            toggle_pool_member("web-pool", "99.99.99.99", enable=True)
