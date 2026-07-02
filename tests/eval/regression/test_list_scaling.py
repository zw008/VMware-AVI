"""Regression evals for REST/K8s N+1 scaling fixes.

These pin the *collection mechanism* (not the rendered output): the audited
findings were that list_pools issued a poolgroup GET per pool group, and
check_ingress_annotations issued a secret GET per Ingress-TLS entry. Both must
now use a single bulk list call.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.unit
class TestListPoolsBulkPoolGroup:
    """pool_mgmt.list_pools must resolve pool groups with ONE list call."""

    @pytest.mark.usefixtures("_patch_avi_connect")
    def test_single_poolgroup_list_no_per_pg_gets(
        self, mock_avi_session: MagicMock,
    ) -> None:
        inventory = [
            {
                "config": {"name": "web-vs"},
                "pools": [],
                "poolgroups": ["/api/poolgroup/pg-1"],
            },
            {
                "config": {"name": "web-canary-vs"},
                "pools": [],
                "poolgroups": ["/api/poolgroup/pg-2"],
            },
        ]
        poolgroups = {
            "pg-1": {"members": [{"pool_ref": "/api/pool/pool-1"}]},
            "pg-2": {"members": [{"pool_ref": "/api/pool/pool-2"}]},
        }
        pools = [
            {"name": "web-pool", "uuid": "pool-1", "servers": [{}], "enabled": True},
            {"name": "canary-pool", "uuid": "pool-2", "servers": [{}], "enabled": True},
        ]

        def _dispatch(path: str, *args, **kwargs) -> MagicMock:
            resp = MagicMock()
            if path == "virtualservice-inventory":
                resp.json.return_value = {"results": inventory}
            elif path == "pool":
                resp.json.return_value = {"results": pools}
            elif path == "poolgroup":
                resp.json.return_value = {
                    "results": [{"uuid": u, **pg} for u, pg in poolgroups.items()]
                }
            else:
                resp.json.return_value = {}
            return resp

        mock_avi_session.get.side_effect = _dispatch

        from vmware_avi.ops.pool_mgmt import list_pools
        list_pools(vs_filter="web")

        called_paths = [c.args[0] for c in mock_avi_session.get.call_args_list]
        # Exactly one bulk poolgroup list call regardless of how many pool
        # groups are referenced (2 here) — the N+1 would have issued one GET
        # per pool group ("poolgroup/pg-1", "poolgroup/pg-2", ...).
        assert called_paths.count("poolgroup") == 1
        assert not any(p.startswith("poolgroup/") for p in called_paths)


def _ingress(name: str, secret_names: list[str]) -> SimpleNamespace:
    return SimpleNamespace(
        metadata=SimpleNamespace(name=name, annotations={}),
        spec=SimpleNamespace(
            ingress_class_name="avi",
            tls=[SimpleNamespace(secret_name=s) for s in secret_names],
        ),
    )


@pytest.mark.unit
class TestCheckIngressAnnotationsBulkSecrets:
    """ako_ingress.check_ingress_annotations must list secrets ONCE per ns."""

    def test_single_secret_list_no_per_ingress_reads(
        self, sample_config: MagicMock,
    ) -> None:
        mock_net = MagicMock()
        mock_net.list_namespaced_ingress.return_value.items = [
            _ingress("ing-a", ["tls-a", "tls-shared"]),
            _ingress("ing-b", ["tls-b", "tls-shared"]),
        ]

        mock_core = MagicMock()
        mock_core.list_namespaced_secret.return_value.items = [
            SimpleNamespace(metadata=SimpleNamespace(name="tls-a")),
            SimpleNamespace(metadata=SimpleNamespace(name="tls-shared")),
        ]

        with (
            patch("vmware_avi.ops.ako_ingress.load_config", return_value=sample_config),
            patch("vmware_avi.ops.ako_ingress.K8sConnectionManager") as MockK8s,
            patch("kubernetes.client.NetworkingV1Api", return_value=mock_net),
        ):
            MockK8s.from_config.return_value.get_client.return_value = MagicMock()
            MockK8s.from_config.return_value.core_v1.return_value = mock_core

            from vmware_avi.ops.ako_ingress import check_ingress_annotations
            check_ingress_annotations("default")

        # One bulk list for the namespace; the per-Ingress-per-TLS read is gone.
        assert mock_core.list_namespaced_secret.call_count == 1
        mock_core.list_namespaced_secret.assert_called_once_with("default")
        mock_core.read_namespaced_secret.assert_not_called()
