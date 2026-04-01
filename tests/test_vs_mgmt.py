"""Tests for Virtual Service management operations."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.unit
class TestListVirtualServices:
    """vs_mgmt.list_virtual_services — lists VS from AVI Controller."""

    @pytest.mark.usefixtures("_patch_avi_connect")
    def test_list_empty(self, mock_avi_session: MagicMock) -> None:
        mock_avi_session.get.return_value.json.return_value = {"results": []}
        from vmware_avi.ops.vs_mgmt import list_virtual_services
        list_virtual_services()  # should not raise

    @pytest.mark.usefixtures("_patch_avi_connect")
    def test_list_with_results(self, mock_avi_session: MagicMock) -> None:
        mock_avi_session.get.return_value.json.return_value = {
            "results": [
                {
                    "name": "web-vs",
                    "enabled": True,
                    "uuid": "vs-1234567890ab",
                    "vip": [{"ip_address": {"addr": "192.168.1.10"}}],
                },
            ],
        }
        from vmware_avi.ops.vs_mgmt import list_virtual_services
        list_virtual_services()
        mock_avi_session.get.assert_called_once()


@pytest.mark.unit
class TestShowVsStatus:
    """vs_mgmt.show_vs_status — detailed VS info."""

    @pytest.mark.usefixtures("_patch_avi_connect")
    def test_status_not_found(self, mock_avi_session: MagicMock) -> None:
        mock_avi_session.get_object_by_name.return_value = None
        from vmware_avi.ops.vs_mgmt import show_vs_status
        with pytest.raises(SystemExit):
            show_vs_status("missing")

    @pytest.mark.usefixtures("_patch_avi_connect")
    def test_status_found(self, mock_avi_session: MagicMock) -> None:
        mock_avi_session.get_object_by_name.return_value = {
            "name": "web-vs",
            "enabled": True,
            "uuid": "vs-abc",
            "vip": [{"ip_address": {"addr": "10.0.0.5"}}],
            "pool_ref": "https://ctrl/api/pool/pool-1?name=web-pool",
        }
        from vmware_avi.ops.vs_mgmt import show_vs_status
        show_vs_status("web-vs")  # should not raise


@pytest.mark.unit
class TestToggleVs:
    """vs_mgmt.toggle_vs — enable/disable with double_confirm guard."""

    @pytest.mark.usefixtures("_patch_avi_connect")
    def test_enable_does_not_require_confirm(self, mock_avi_session: MagicMock) -> None:
        mock_avi_session.get_object_by_name.return_value = {
            "name": "web-vs", "uuid": "vs-1", "enabled": False,
        }
        from vmware_avi.ops.vs_mgmt import toggle_vs
        toggle_vs("web-vs", enable=True)
        mock_avi_session.put.assert_called_once()

    @pytest.mark.usefixtures("_patch_avi_connect")
    def test_disable_calls_double_confirm(self, mock_avi_session: MagicMock) -> None:
        mock_avi_session.get_object_by_name.return_value = {
            "name": "web-vs", "uuid": "vs-1", "enabled": True,
        }
        with patch("vmware_avi._safety.double_confirm", return_value=True):
            from vmware_avi.ops.vs_mgmt import toggle_vs
            toggle_vs("web-vs", enable=False)
            mock_avi_session.put.assert_called_once()

    @pytest.mark.usefixtures("_patch_avi_connect")
    def test_disable_cancelled(self, mock_avi_session: MagicMock) -> None:
        with patch("vmware_avi._safety.double_confirm", return_value=False):
            from vmware_avi.ops.vs_mgmt import toggle_vs
            toggle_vs("web-vs", enable=False)
            mock_avi_session.put.assert_not_called()
