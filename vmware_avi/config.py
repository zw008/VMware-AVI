"""Configuration management for VMware AVI.

Loads AVI Controller targets and AKO settings from YAML config + environment variables.
Passwords are NEVER stored in config files — always via environment variables.
"""

from __future__ import annotations

import base64
import binascii
import logging
import os
import re
import stat
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import dotenv_values, load_dotenv, set_key

CONFIG_DIR = Path.home() / ".vmware-avi"
CONFIG_FILE = CONFIG_DIR / "config.yaml"
ENV_FILE = CONFIG_DIR / ".env"

_log = logging.getLogger("vmware-avi.config")

_PW_KEY_RE = re.compile(r"[A-Z][A-Z0-9_]*_PASSWORD")


def _is_b64_token(value: str) -> tuple[bool, str]:
    """Return ``(True, decoded)`` if ``value`` is a valid ``b64:`` token, else ``(False, "")``.

    Recognises already-encoded values (for idempotency) and decodes on read. A
    value that merely *starts with* ``b64:`` but is not valid base64 (e.g. a real
    password ``b64:hunter2``) is NOT a token — it is treated as plaintext, so such
    a password still round-trips correctly instead of being corrupted.
    """
    if not value.startswith("b64:"):
        return (False, "")
    try:
        return (True, base64.b64decode(value[4:], validate=True).decode("utf-8"))
    except (binascii.Error, ValueError, UnicodeDecodeError):
        return (False, "")


def _decode_secret(value: str) -> str:
    """Decode a ``b64:`` token; any other value passes through unchanged.

    Obfuscation to defeat casual grep — NOT encryption.
    """
    ok, decoded = _is_b64_token(value)
    return decoded if ok else value


def _autoencode_env_file(env_file: Path) -> None:
    """Rewrite plaintext ``*_PASSWORD`` values in .env to grep-safe ``b64:`` form.

    Values are read and written through python-dotenv's own parser/serializer
    (``dotenv_values`` + ``set_key``), so the stored value is exactly what
    ``load_dotenv`` would return — quoting, inline comments, and trailing
    whitespace are handled identically and the secret never drifts from the
    configured one. Idempotent (already-``b64:`` tokens are skipped); only
    ``*_PASSWORD`` keys are touched. Obfuscation, not encryption.
    """
    if not env_file.exists():
        return
    try:
        parsed = dotenv_values(env_file)
    except OSError:
        return

    changed = False
    for key, value in parsed.items():
        if not value or not _PW_KEY_RE.fullmatch(key) or _is_b64_token(value)[0]:
            continue
        encoded = "b64:" + base64.b64encode(value.encode("utf-8")).decode("ascii")
        try:
            set_key(str(env_file), key, encoded, quote_mode="never")
            changed = True
        except OSError as exc:
            _log.warning("Could not auto-encode %s in %s: %s", key, env_file, exc)

    if not changed:
        return
    try:
        os.chmod(env_file, 0o600)
    except OSError:
        pass
    _log.warning(
        "Auto-encoded plaintext password(s) in %s to b64: (grep-safe; "
        "obfuscation, not encryption).",
        env_file,
    )


# Auto-encode any plaintext passwords in .env, then load it into the environment
_autoencode_env_file(ENV_FILE)
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
        return _decode_secret(pw)


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
