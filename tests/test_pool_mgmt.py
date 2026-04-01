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
