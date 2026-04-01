"""Configuration management for VMware AVI.

Loads AVI Controller targets and AKO settings from YAML config + environment variables.
Passwords are NEVER stored in config files — always via environment variables.
"""

from __future__ import annotations

import logging
import os
import stat
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

CONFIG_DIR = Path.home() / ".vmware-avi"
CONFIG_FILE = CONFIG_DIR / "config.yaml"
ENV_FILE = CONFIG_DIR / ".env"

_log = logging.getLogger("vmware-avi.config")

load_dotenv(ENV_FILE)


def _check_env_permissions() -> None:
    """Warn if .env file has permissions wider than owner-only (600)."""
    if not ENV_FILE.exists():
        return
    try:
        mode = ENV_FILE.stat().st_mode
        if mode & (stat.S_IRWXG | stat.S_IRWXO):
            _log.warning(
                "Security warning: %s has permissions %s (should be 600). "
                "Run: chmod 600 %s",
                ENV_FILE,
                oct(stat.S_IMODE(mode)),
                ENV_FILE,
            )
    except OSError:
        pass


_check_env_permissions()


@dataclass(frozen=True)
class ControllerConfig:
    """An AVI Controller connection target."""

    name: str
    host: str
    username: str = "admin"
    api_version: str = "22.1.4"
    tenant: str = "admin"
    port: int = 443
    verify_ssl: bool = True

    @property
    def password(self) -> str:
        env_key = f"{self.name.upper().replace('-', '_')}_PASSWORD"
        pw = os.environ.get(env_key, "")
        if not pw:
            raise OSError(
                f"Password not found. Set environment variable: {env_key}"
            )
        return pw


@dataclass(frozen=True)
class AkoConfig:
    """AKO (Avi Kubernetes Operator) connection settings."""

    kubeconfig: str = str(Path.home() / ".kube" / "config")
    default_context: str = ""
    namespace: str = "avi-system"


@dataclass(frozen=True)
class AppConfig:
    """Top-level application config."""

    controllers: tuple[ControllerConfig, ...] = ()
    default_controller: str = ""
    ako: AkoConfig = field(default_factory=AkoConfig)

    def get_controller(self, name: str) -> ControllerConfig:
        for c in self.controllers:
            if c.name == name:
                return c
        available = ", ".join(c.name for c in self.controllers)
        raise KeyError(f"Controller '{name}' not found. Available: {available}")

    @property
    def active_controller(self) -> ControllerConfig:
        if self.default_controller:
            return self.get_controller(self.default_controller)
        if not self.controllers:
            raise ValueError("No controllers configured. Check config.yaml")
        return self.controllers[0]


def load_config(config_path: Path | None = None) -> AppConfig:
    """Load config from YAML file, with env var overrides for passwords."""
    path = config_path or CONFIG_FILE
    if not path.exists():
        raise FileNotFoundError(
            f"Config file not found: {path}\n"
            f"Copy config.example.yaml to {CONFIG_FILE} and edit it."
        )

    with open(path) as f:
        raw = yaml.safe_load(f) or {}

    controllers = tuple(
        ControllerConfig(
            name=c["name"],
            host=c["host"],
            username=c.get("username", "admin"),
            api_version=c.get("api_version", "22.1.4"),
            tenant=c.get("tenant", "admin"),
            port=c.get("port", 443),
            verify_ssl=c.get("verify_ssl", True),
        )
        for c in raw.get("controllers", [])
    )

    ako_raw = raw.get("ako", {})
    ako = AkoConfig(
        kubeconfig=ako_raw.get("kubeconfig", str(Path.home() / ".kube" / "config")),
        default_context=ako_raw.get("default_context", ""),
        namespace=ako_raw.get("namespace", "avi-system"),
    )

    return AppConfig(
        controllers=controllers,
        default_controller=raw.get("default_controller", ""),
        ako=ako,
    )
