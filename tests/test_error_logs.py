"""Tests for VS error-log operations (analytics.show_error_logs)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


@pytest.mark.unit
class TestShowErrorLogs:
    """analytics.show_error_logs — queries AVI /analytics/logs."""

    @pytest.mark.usefixtures("_patch_avi_connect")
    def test_not_found(self, mock_avi_session: MagicMock) -> None:
        mock_avi_session.get_object_by_name.return_value = None
        from vmware_avi.ops.analytics import show_error_logs
        with pytest.raises(SystemExit):
            show_error_logs("missing")

    @pytest.mark.usefixtures("_patch_avi_connect")
    def test_invalid_duration(self, mock_avi_session: MagicMock) -> None:
        mock_avi_session.get_object_by_name.return_value = {
            "name": "web-vs", "uuid": "vs-abc",
        }
        from vmware_avi.ops.analytics import show_error_logs
        with pytest.raises(SystemExit):
            show_error_logs("web-vs", since="bogus")

    @pytest.mark.usefixtures("_patch_avi_connect")
    def test_passes_virtualservice_uuid_as_url_param(
        self, mock_avi_session: MagicMock,
    ) -> None:
        """AVI 22.x requires the VS UUID as the ``virtualservice`` URL param;
        putting it only in ``filter=co(vs_uuid,...)`` yields HTTP 400
        'VirtualService ID required'.
        """
        mock_avi_session.get_object_by_name.return_value = {
            "name": "web-vs", "uuid": "vs-abc",
        }
        mock_avi_session.get.return_value.json.return_value = {"results": []}

        from vmware_avi.ops.analytics import show_error_logs
        show_error_logs("web-vs", since="30m")

        mock_avi_session.get.assert_called_once()
        _, kwargs = mock_avi_session.get.call_args
        params = kwargs["params"]
        assert params["virtualservice"] == "vs-abc"
        assert params["duration"] == str(30 * 60)
        # Filter should no longer carry the vs_uuid clause — AVI rejects it
        # as insufficient without the explicit URL param.
        assert "vs_uuid" not in params.get("filter", "")
