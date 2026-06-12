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
            # ako_sync imports NetworkingV1Api lazily inside the function, so
            # patch it at the source module, not on ako_sync itself.
            patch("kubernetes.client.NetworkingV1Api", return_value=mock_net),
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
            # ako_sync imports NetworkingV1Api lazily inside the function, so
            # patch it at the source module, not on ako_sync itself.
            patch("kubernetes.client.NetworkingV1Api", return_value=mock_net),
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
            # ako_sync imports NetworkingV1Api lazily inside the function, so
            # patch it at the source module, not on ako_sync itself.
            patch("kubernetes.client.NetworkingV1Api", return_value=mock_net),
        ):
            MockK8s.return_value.get_client.return_value = MagicMock()
            MockAvi.return_value.connect.return_value = mock_session

            from vmware_avi.ops.ako_sync import show_sync_diff
            show_sync_diff()  # prints table with missing entry

    def test_shard_mode_ingress_not_flagged_missing(
        self, sample_config: MagicMock
    ) -> None:
        """Regression (issue #13): an Ingress whose short name is NOT a VS-name
        suffix but IS represented by an AKO pool must not be flagged "Missing".

        In default shard mode AKO folds many Ingresses into shared parent VSes
        (e.g. 'Shared-L7-0') and represents them via pools named from the
        cluster/namespace/host/path/ingress. The Ingress name appears as a
        '-'-delimited token in the pool name, never as a VS suffix.
        """
        mock_net = MagicMock()
        mock_net.list_ingress_for_all_namespaces.return_value.items = [
            _make_ingress("default", "web"),
        ]

        # First api_get -> /virtualservice (only shared shard VSes, no per-
        # Ingress VS); second api_get -> /pool (AKO-named pool carrying 'web').
        vs_resp = MagicMock()
        vs_resp.json.return_value = {"results": [{"name": "Shared-L7-0"}]}
        pool_resp = MagicMock()
        pool_resp.json.return_value = {
            "results": [{"name": "cluster--default-myapp.example.com_-web"}],
        }
        mock_session = MagicMock()
        mock_session.get.side_effect = [vs_resp, pool_resp]

        with (
            patch("vmware_avi.ops.ako_sync.load_config", return_value=sample_config),
            patch("vmware_avi.ops.ako_sync.K8sConnectionManager") as MockK8s,
            patch("vmware_avi.ops.ako_sync.AviConnectionManager") as MockAvi,
            patch("kubernetes.client.NetworkingV1Api", return_value=mock_net),
            patch("vmware_avi.ops.ako_sync.console") as mock_console,
        ):
            MockK8s.return_value.get_client.return_value = MagicMock()
            MockAvi.return_value.connect.return_value = mock_session

            from vmware_avi.ops.ako_sync import show_sync_diff
            show_sync_diff()

            # The rendered table is passed to console.print; assert no row was
            # added for the sharded Ingress (table has zero data rows).
            printed_tables = [
                call.args[0]
                for call in mock_console.print.call_args_list
                if call.args and hasattr(call.args[0], "row_count")
            ]
            assert printed_tables, "expected a Sync Diff table to be printed"
            assert printed_tables[0].row_count == 0, (
                "shard-mode Ingress backed by an AKO pool was wrongly flagged "
                "Missing on Controller"
            )
