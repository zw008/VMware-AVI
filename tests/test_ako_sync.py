"""Tests for K8s-Controller sync diagnostics."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


def _make_ingress(ns: str, name: str) -> SimpleNamespace:
    return SimpleNamespace(metadata=SimpleNamespace(namespace=ns, name=name))


@pytest.mark.unit
class TestCheckSyncStatus:
    """ako_sync.check_sync_status — compares K8s Ingress count vs AVI VS count."""

    def test_counts_match(self, sample_config: MagicMock) -> None:
        mock_net = MagicMock()
        mock_net.list_ingress_for_all_namespaces.return_value.items = [
            _make_ingress("default", "web"),
        ]

        mock_session = MagicMock()
        mock_session.get.return_value.json.return_value = {
            "results": [{"name": "web"}],
        }

        with (
            patch("vmware_avi.ops.ako_sync.load_config", return_value=sample_config),
            patch("vmware_avi.ops.ako_sync.K8sConnectionManager") as MockK8s,
            patch("vmware_avi.ops.ako_sync.AviConnectionManager") as MockAvi,
            patch("vmware_avi.ops.ako_sync.NetworkingV1Api", return_value=mock_net),
        ):
            MockK8s.return_value.get_client.return_value = MagicMock()
            MockAvi.return_value.connect.return_value = mock_session

            from vmware_avi.ops.ako_sync import check_sync_status
            check_sync_status()  # should not raise

    def test_counts_mismatch(self, sample_config: MagicMock) -> None:
        mock_net = MagicMock()
        mock_net.list_ingress_for_all_namespaces.return_value.items = [
            _make_ingress("default", "web"),
            _make_ingress("default", "api"),
        ]

        mock_session = MagicMock()
        mock_session.get.return_value.json.return_value = {
            "results": [{"name": "web"}],
        }

        with (
            patch("vmware_avi.ops.ako_sync.load_config", return_value=sample_config),
            patch("vmware_avi.ops.ako_sync.K8sConnectionManager") as MockK8s,
            patch("vmware_avi.ops.ako_sync.AviConnectionManager") as MockAvi,
            patch("vmware_avi.ops.ako_sync.NetworkingV1Api", return_value=mock_net),
        ):
            MockK8s.return_value.get_client.return_value = MagicMock()
            MockAvi.return_value.connect.return_value = mock_session

            from vmware_avi.ops.ako_sync import check_sync_status
            check_sync_status()  # should not raise (just prints warning)


@pytest.mark.unit
class TestShowSyncDiff:
    """ako_sync.show_sync_diff — identifies Ingresses missing on Controller."""

    def test_diff_shows_missing(self, sample_config: MagicMock) -> None:
        mock_net = MagicMock()
        mock_net.list_ingress_for_all_namespaces.return_value.items = [
            _make_ingress("default", "missing-svc"),
        ]

        mock_session = MagicMock()
        mock_session.get.return_value.json.return_value = {"results": []}

        with (
            patch("vmware_avi.ops.ako_sync.load_config", return_value=sample_config),
            patch("vmware_avi.ops.ako_sync.K8sConnectionManager") as MockK8s,
            patch("vmware_avi.ops.ako_sync.AviConnectionManager") as MockAvi,
            patch("vmware_avi.ops.ako_sync.NetworkingV1Api", return_value=mock_net),
        ):
            MockK8s.return_value.get_client.return_value = MagicMock()
            MockAvi.return_value.connect.return_value = mock_session

            from vmware_avi.ops.ako_sync import show_sync_diff
            show_sync_diff()  # prints table with missing entry
