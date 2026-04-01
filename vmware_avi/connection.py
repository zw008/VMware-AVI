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
    def _create_session(ctrl: ControllerConfig) -> ApiSession:
        from avi.sdk.avi_api import ApiSession

        _log.info("Connecting to AVI Controller: %s (%s)", ctrl.name, ctrl.host)
        return ApiSession.get_session(
            controller_ip=ctrl.host,
            username=ctrl.username,
            password=ctrl.password,
            api_version=ctrl.api_version,
            tenant=ctrl.tenant,
            port=ctrl.port,
        )
