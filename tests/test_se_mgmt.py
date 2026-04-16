"""Tests for Service Engine management operations."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


def _se_health_session(
    mock_avi_session: MagicMock,
    *,
    vs_inventory: list[dict],
    se_inventory: list[dict],
) -> None:
    """Wire session.get to dispatch by endpoint for check_se_health."""

    def _dispatch(path: str, *args, **kwargs) -> MagicMock:
        resp = MagicMock()
        if path == "virtualservice-inventory":
            resp.json.return_value = {"results": vs_inventory}
        elif path == "serviceengine-inventory":
            resp.json.return_value = {"results": se_inventory}
        else:
            resp.json.return_value = {}
        return resp

    mock_avi_session.get.side_effect = _dispatch


@pytest.mark.unit
class TestCheckSeHealth:
    """se_mgmt.check_se_health — VS count derivation."""

    @pytest.mark.usefixtures("_patch_avi_connect")
    def test_vs_count_inverted_from_vs_inventory(
        self, mock_avi_session: MagicMock, capsys: pytest.CaptureFixture,
    ) -> None:
        """The bug: 22.x SE runtime has no VS list field, so reading
        runtime.se_vs_list / vs_ref / virtualservice_refs always yielded 0.
        check_se_health must reconstruct the count by inverting the VS→SE
        placement map from /virtualservice-inventory."""
        _se_health_session(
            mock_avi_session,
            vs_inventory=[
                {
                    "uuid": "vs-1",
                    "runtime": {
                        "vip_summary": [
                            {"service_engine": [
                                {"uuid": "se-a"}, {"uuid": "se-b"},
                            ]},
                        ],
                    },
                },
                {
                    "uuid": "vs-2",
                    "runtime": {
                        "vip_summary": [
                            {"service_engine": [{"uuid": "se-a"}]},
                        ],
                    },
                },
            ],
            se_inventory=[
                {
                    "uuid": "se-a",
                    "config": {"name": "Avi-se-a"},
                    "runtime": {"oper_status": {"state": "OPER_UP"}},
                },
                {
                    "uuid": "se-b",
                    "config": {"name": "Avi-se-b"},
                    "runtime": {"oper_status": {"state": "OPER_UP"}},
                },
            ],
        )
        from vmware_avi.ops.se_mgmt import check_se_health
        check_se_health()

        # /virtualservice-inventory must be queried — that's the source of truth.
        paths = [c.args[0] for c in mock_avi_session.get.call_args_list]
        assert "virtualservice-inventory" in paths
        assert "serviceengine-inventory" in paths

        out = capsys.readouterr().out
        # se-a hosts both VSes; se-b only hosts vs-1.
        assert "Avi-se-a" in out and "VS count: 2" in out
        assert "Avi-se-b" in out and "VS count: 1" in out

    @pytest.mark.usefixtures("_patch_avi_connect")
    def test_vs_with_multiple_vips_on_same_se_counts_once(
        self, mock_avi_session: MagicMock, capsys: pytest.CaptureFixture,
    ) -> None:
        """A VS with two VIPs both landing on the same SE should still be
        counted as one VS for that SE, not two."""
        _se_health_session(
            mock_avi_session,
            vs_inventory=[
                {
                    "uuid": "vs-1",
                    "runtime": {
                        "vip_summary": [
                            {"service_engine": [{"uuid": "se-a"}]},
                            {"service_engine": [{"uuid": "se-a"}]},
                        ],
                    },
                },
            ],
            se_inventory=[
                {
                    "uuid": "se-a",
                    "config": {"name": "Avi-se-a"},
                    "runtime": {"oper_status": {"state": "OPER_UP"}},
                },
            ],
        )
        from vmware_avi.ops.se_mgmt import check_se_health
        check_se_health()
        out = capsys.readouterr().out
        assert "VS count: 1" in out
        assert "VS count: 2" not in out

    @pytest.mark.usefixtures("_patch_avi_connect")
    def test_idle_se_reports_zero(
        self, mock_avi_session: MagicMock, capsys: pytest.CaptureFixture,
    ) -> None:
        """A genuinely unused SE should report 0 — ensure we don't
        accidentally invent a non-zero count."""
        _se_health_session(
            mock_avi_session,
            vs_inventory=[],
            se_inventory=[
                {
                    "uuid": "se-idle",
                    "config": {"name": "Avi-se-idle"},
                    "runtime": {"oper_status": {"state": "OPER_UP"}},
                },
            ],
        )
        from vmware_avi.ops.se_mgmt import check_se_health
        check_se_health()
        assert "VS count: 0" in capsys.readouterr().out
