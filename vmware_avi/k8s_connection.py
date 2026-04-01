"""Kubernetes connection management for AKO operations.

Uses kubeconfig for authentication, supports context switching.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kubernetes.client import ApiClient, AppsV1Api, CoreV1Api

from vmware_avi.config import AkoConfig, AppConfig, load_config

_log = logging.getLogger("vmware-avi.k8s")


class K8sConnectionManager:
    """Manages Kubernetes API connections for AKO operations."""

    def __init__(self, ako_config: AkoConfig) -> None:
        self._config = ako_config
        self._client: ApiClient | None = None

    @classmethod
    def from_config(cls, config: AppConfig | None = None) -> K8sConnectionManager:
        cfg = config or load_config()
        return cls(cfg.ako)

    def get_client(self, context: str | None = None) -> ApiClient:
        """Get or create a Kubernetes API client."""
        from kubernetes import client, config

        target_context = context or self._config.default_context or None

        config.load_kube_config(
            config_file=self._config.kubeconfig,
            context=target_context,
        )
        self._client = client.ApiClient()
        _log.info(
            "Connected to K8s (kubeconfig=%s, context=%s)",
            self._config.kubeconfig,
            target_context or "current",
        )
        return self._client

    def core_v1(self, context: str | None = None) -> CoreV1Api:
        from kubernetes.client import CoreV1Api

        return CoreV1Api(self.get_client(context))

    def apps_v1(self, context: str | None = None) -> AppsV1Api:
        from kubernetes.client import AppsV1Api

        return AppsV1Api(self.get_client(context))

    @property
    def namespace(self) -> str:
        return self._config.namespace
