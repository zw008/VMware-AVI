"""AVI Controller connection management via avisdk.

Handles multi-controller connections with session reuse.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from avi.sdk.avi_api import ApiSession

from vmware_avi.config import AppConfig, ControllerConfig, load_config

_log = logging.getLogger("vmware-avi.connection")


class AviConnectionManager:
    """Manages connections to multiple AVI Controllers."""

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._sessions: dict[str, ApiSession] = {}

    @classmethod
    def from_config(cls, config: AppConfig | None = None) -> AviConnectionManager:
        cfg = config or load_config()
        return cls(cfg)

    def connect(self, controller_name: str | None = None) -> ApiSession:
        """Connect to a controller by name, or the active controller."""
        ctrl = (
            self._config.get_controller(controller_name)
            if controller_name
            else self._config.active_controller
        )

        if ctrl.name in self._sessions:
            session = self._sessions[ctrl.name]
            try:
                session.get("cluster/runtime")
                return session
            except Exception:
                del self._sessions[ctrl.name]

        session = self._create_session(ctrl)
        self._sessions[ctrl.name] = session
        return session

    def disconnect(self, controller_name: str) -> None:
        if controller_name in self._sessions:
            try:
                self._sessions[controller_name].delete("logout")
            except Exception:
                pass
            del self._sessions[controller_name]

    def disconnect_all(self) -> None:
        for name in list(self._sessions):
            self.disconnect(name)

    def list_controllers(self) -> list[str]:
        return [c.name for c in self._config.controllers]

    def list_connected(self) -> list[str]:
        return list(self._sessions.keys())

    @staticmethod
    def _resolve_host(host: str) -> str:
        """Resolve a hostname/FQDN to an IPv4/IPv6 address.

        Returns the host unchanged if it is already an IP literal. Falls back
        to the original host if DNS resolution fails (avisdk will surface the
        network error downstream with its own message).

        Rationale: AVI Controller analytics endpoints validate the
        ``controller_ip`` header as an IP address literal and reject hostnames
        with "Invalid Controller IP6 Address: <hostname>". Resolving once at
        connect time lets users put FQDNs in config.yaml.
        """
        import ipaddress
        import socket

        try:
            ipaddress.ip_address(host)
            return host  # already an IP literal
        except ValueError:
            pass

        try:
            # getaddrinfo handles both IPv4 and IPv6; prefer IPv4 when available
            infos = socket.getaddrinfo(host, None)
            ipv4 = next((i for i in infos if i[0] == socket.AF_INET), None)
            return (ipv4 or infos[0])[4][0]
        except socket.gaierror as e:
            _log.warning("DNS resolution failed for %s: %s — using raw host", host, e)
            return host

    @classmethod
    def _create_session(cls, ctrl: ControllerConfig) -> ApiSession:
        from avi.sdk.avi_api import ApiSession

        controller_ip = cls._resolve_host(ctrl.host)
        if controller_ip != ctrl.host:
            _log.info(
                "Connecting to AVI Controller: %s (%s -> %s)",
                ctrl.name, ctrl.host, controller_ip,
            )
        else:
            _log.info("Connecting to AVI Controller: %s (%s)", ctrl.name, ctrl.host)

        return ApiSession.get_session(
            controller_ip=controller_ip,
            username=ctrl.username,
            password=ctrl.password,
            api_version=ctrl.api_version,
            tenant=ctrl.tenant,
            port=ctrl.port,
        )
