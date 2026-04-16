"""Tests for VS analytics and error log operations."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


@pytest.mark.unit
class TestShowAnalytics:
    """analytics.show_analytics — queries AVI metrics collection endpoint."""

    @pytest.mark.usefixtures("_patch_avi_connect")
    def test_not_found(self, mock_avi_session: MagicMock) -> None:
        mock_avi_session.get_object_by_name.return_value = None
        from vmware_avi.ops.analytics import show_analytics
        with pytest.raises(SystemExit):
            show_analytics("missing")

    @pytest.mark.usefixtures("_patch_avi_connect")
    def test_uses_post_with_body(self, mock_avi_session: MagicMock) -> None:
        """AVI 22.x rejects GET on analytics/metrics/collection with HTTP 404
        'Pl. use Post request'. The client must POST with params in the body.
        """
        mock_avi_session.get_object_by_name.return_value = {
            "name": "web-vs", "uuid": "vs-abc",
        }
        mock_avi_session.post.return_value.json.return_value = {"series": []}

        from vmware_avi.ops.analytics import show_analytics
        show_analytics("web-vs")

        mock_avi_session.post.assert_called_once()
        args, kwargs = mock_avi_session.post.call_args
        assert args[0] == "analytics/metrics/collection"
        body = kwargs.get("data") or (args[1] if len(args) > 1 else None)
        assert body is not None
        # /analytics/metrics/collection is a *collections* API — queries must
        # be wrapped in metric_requests[]. A top-level metric_id/entity_uuid
        # yields HTTP 404 {"error": "Empty Request"}.
        assert "metric_requests" in body
        assert isinstance(body["metric_requests"], list)
        req = body["metric_requests"][0]
        assert req["entity_uuid"] == "vs-abc"
        assert "metric_id" in req
        assert req["step"] == 300
        # Must not call GET on the collection endpoint (would 404 on 22.x).
        for call in mock_avi_session.get.call_args_list:
            assert call.args[0] != "analytics/metrics/collection"

    @pytest.mark.usefixtures("_patch_avi_connect")
    def test_renders_series_dict_shape(self, mock_avi_session: MagicMock) -> None:
        """Collection endpoint returns {series: {uuid: [...]}}; must render."""
        mock_avi_session.get_object_by_name.return_value = {
            "name": "web-vs", "uuid": "vs-abc",
        }
        mock_avi_session.post.return_value.json.return_value = {
            "series": {
                "vs-abc": [
                    {
                        "header": {
                            "name": "l4_client.avg_bandwidth",
                            "units": "BITS_PER_SECOND",
                            "statistics": {"mean": 1234.5},
                        },
                        "data": [{"value": 2000.0}],
                    },
                ],
            },
        }
        from vmware_avi.ops.analytics import show_analytics
        show_analytics("web-vs")  # should not raise


@pytest.mark.unit
class TestShowErrorLogs:
    """analytics.show_error_logs — still uses GET on analytics/logs."""

    @pytest.mark.usefixtures("_patch_avi_connect")
    def test_invalid_duration(self, mock_avi_session: MagicMock) -> None:
        mock_avi_session.get_object_by_name.return_value = {
            "name": "web-vs", "uuid": "vs-abc",
        }
        from vmware_avi.ops.analytics import show_error_logs
        with pytest.raises(SystemExit):
            show_error_logs("web-vs", since="bogus")

    @pytest.mark.usefixtures("_patch_avi_connect")
    def test_passes_duration_seconds(self, mock_avi_session: MagicMock) -> None:
        mock_avi_session.get_object_by_name.return_value = {
            "name": "web-vs", "uuid": "vs-abc",
        }
        mock_avi_session.get.return_value.json.return_value = {"results": []}
        from vmware_avi.ops.analytics import show_error_logs
        show_error_logs("web-vs", since="30m")
        mock_avi_session.get.assert_called_once()
        _, kwargs = mock_avi_session.get.call_args
        assert kwargs["params"]["duration"] == str(30 * 60)
