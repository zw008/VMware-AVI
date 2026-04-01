"""Shared fixtures for VMware AVI tests.

Provides mock AVI sessions, K8s clients, and config objects so that
tests run without real infrastructure.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from vmware_avi.config import AkoConfig, AppConfig, ControllerConfig


# ---------------------------------------------------------------------------
# Config fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def sample_controller() -> ControllerConfig:
    return ControllerConfig(name="lab", host="10.0.0.1", username="admin")


@pytest.fixture()
def sample_ako_config() -> AkoConfig:
    return AkoConfig(kubeconfig="/tmp/fake-kubeconfig", namespace="avi-system")


@pytest.fixture()
def sample_config(
    sample_controller: ControllerConfig,
    sample_ako_config: AkoConfig,
) -> AppConfig:
    return AppConfig(
        controllers=(sample_controller,),
        default_controller="lab",
        ako=sample_ako_config,
    )


@pytest.fixture()
def config_yaml(tmp_path: Path) -> Path:
    """Write a minimal valid config.yaml and return its path."""
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "controllers:\n"
        "  - name: lab\n"
        "    host: 10.0.0.1\n"
        "default_controller: lab\n"
        "ako:\n"
        "  namespace: avi-system\n"
    )
    return cfg


# ---------------------------------------------------------------------------
# Mock AVI session
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_avi_session() -> MagicMock:
    """Return a MagicMock that behaves like avi.sdk.avi_api.ApiSession."""
    session = MagicMock()
    session.get.return_value.json.return_value = {"results": []}
    session.get_object_by_name.return_value = None
    return session


@pytest.fixture()
def _patch_avi_connect(
    mock_avi_session: MagicMock,
    sample_config: AppConfig,
) -> Any:
    """Patch load_config + AviConnectionManager.connect to return the mock session."""
    with (
        patch("vmware_avi.config.load_config", return_value=sample_config),
        patch(
            "vmware_avi.connection.AviConnectionManager.connect",
            return_value=mock_avi_session,
        ),
    ):
        yield


# ---------------------------------------------------------------------------
# Mock Kubernetes client
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_k8s_core_v1() -> MagicMock:
    """Return a MagicMock that behaves like kubernetes.client.CoreV1Api."""
    core = MagicMock()
    core.list_namespaced_pod.return_value.items = []
    core.read_namespaced_pod_log.return_value = "fake-log-line"
    return core


@pytest.fixture()
def _patch_k8s_connect(
    mock_k8s_core_v1: MagicMock,
    sample_config: AppConfig,
) -> Any:
    """Patch load_config + K8sConnectionManager to return mock K8s client."""
    with (
        patch("vmware_avi.config.load_config", return_value=sample_config),
        patch(
            "vmware_avi.k8s_connection.K8sConnectionManager.core_v1",
            return_value=mock_k8s_core_v1,
        ),
        patch(
            "vmware_avi.k8s_connection.K8sConnectionManager.get_client",
            return_value=MagicMock(),
        ),
    ):
        yield
