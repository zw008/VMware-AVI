"""Tests for AKO pod troubleshooting operations."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


def _make_pod(
    name: str = "ako-0",
    phase: str = "Running",
    ready: bool = True,
    restarts: int = 0,
    image: str = "projects.registry.vmware.com/ako/ako:1.11.3",
) -> SimpleNamespace:
    """Build a lightweight pod-like namespace tree."""
    cs = SimpleNamespace(restart_count=restarts, ready=ready)
    container = SimpleNamespace(image=image)
    return SimpleNamespace(
        metadata=SimpleNamespace(name=name),
        status=SimpleNamespace(phase=phase, container_statuses=[cs]),
        spec=SimpleNamespace(containers=[container]),
    )


def _pod_items(pod: SimpleNamespace) -> MagicMock:
    result = MagicMock()
    result.items = [pod]
    return result


@pytest.mark.unit
class TestCheckAkoStatus:
    """ako_pod.check_ako_status — reports pod phase / readiness."""

    def test_healthy_pod(self, mock_k8s_core_v1: MagicMock, sample_config: MagicMock) -> None:
        pod = _make_pod()
        mock_k8s_core_v1.list_namespaced_pod.return_value = _pod_items(pod)
        mock_k8s_core_v1.read_namespaced_pod.return_value = pod

        with (
            patch("vmware_avi.ops.ako_pod.load_config", return_value=sample_config),
            patch("vmware_avi.ops.ako_pod.K8sConnectionManager") as MockK8s,
        ):
            MockK8s.return_value.core_v1.return_value = mock_k8s_core_v1
            MockK8s.return_value.namespace = "avi-system"
            from vmware_avi.ops.ako_pod import check_ako_status
            check_ako_status()

    def test_no_pod_found(self, mock_k8s_core_v1: MagicMock, sample_config: MagicMock) -> None:
        mock_k8s_core_v1.list_namespaced_pod.return_value.items = []
        with (
            patch("vmware_avi.ops.ako_pod.load_config", return_value=sample_config),
            patch("vmware_avi.ops.ako_pod.K8sConnectionManager") as MockK8s,
        ):
            MockK8s.return_value.core_v1.return_value = mock_k8s_core_v1
            MockK8s.return_value.namespace = "avi-system"
            from vmware_avi.ops.ako_pod import check_ako_status
            with pytest.raises(SystemExit):
                check_ako_status()


@pytest.mark.unit
class TestViewAkoLogs:
    """ako_pod.view_ako_logs — delegates to core_v1.read_namespaced_pod_log."""

    def test_view_logs(self, mock_k8s_core_v1: MagicMock, sample_config: MagicMock) -> None:
        pod = _make_pod()
        mock_k8s_core_v1.list_namespaced_pod.return_value = _pod_items(pod)
        mock_k8s_core_v1.read_namespaced_pod_log.return_value = "log-line"

        with (
            patch("vmware_avi.ops.ako_pod.load_config", return_value=sample_config),
            patch("vmware_avi.ops.ako_pod.K8sConnectionManager") as MockK8s,
        ):
            MockK8s.return_value.core_v1.return_value = mock_k8s_core_v1
            MockK8s.return_value.namespace = "avi-system"
            from vmware_avi.ops.ako_pod import view_ako_logs
            view_ako_logs(tail=50)
            mock_k8s_core_v1.read_namespaced_pod_log.assert_called_once()


@pytest.mark.unit
class TestParseDuration:
    """ako_pod._parse_duration — converts human strings to seconds."""

    def test_minutes(self) -> None:
        from vmware_avi.ops.ako_pod import _parse_duration
        assert _parse_duration("30m") == 1800

    def test_hours(self) -> None:
        from vmware_avi.ops.ako_pod import _parse_duration
        assert _parse_duration("2h") == 7200

    def test_seconds(self) -> None:
        from vmware_avi.ops.ako_pod import _parse_duration
        assert _parse_duration("90s") == 90

    def test_invalid(self) -> None:
        from vmware_avi.ops.ako_pod import _parse_duration
        assert _parse_duration("abc") is None
