"""Tests for config loading, env passwords, missing config, and permissions."""

from __future__ import annotations

import os
import stat
from pathlib import Path
from unittest.mock import patch

import pytest

from vmware_avi.config import (
    AppConfig,
    ControllerConfig,
    _check_env_permissions,
    load_config,
)


@pytest.mark.unit
class TestLoadConfig:
    """Config YAML loading."""

    def test_load_valid_config(self, config_yaml: Path) -> None:
        cfg = load_config(config_yaml)
        assert isinstance(cfg, AppConfig)
        assert len(cfg.controllers) == 1
        assert cfg.controllers[0].name == "lab"
        assert cfg.controllers[0].host == "10.0.0.1"
        assert cfg.default_controller == "lab"

    def test_load_config_file_not_found(self, tmp_path: Path) -> None:
        missing = tmp_path / "nope.yaml"
        with pytest.raises(FileNotFoundError, match="Config file not found"):
            load_config(missing)

    def test_active_controller_returns_default(self, config_yaml: Path) -> None:
        cfg = load_config(config_yaml)
        assert cfg.active_controller.name == "lab"

    def test_active_controller_no_controllers(self) -> None:
        cfg = AppConfig()
        with pytest.raises(ValueError, match="No controllers configured"):
            _ = cfg.active_controller

    def test_get_controller_not_found(self, config_yaml: Path) -> None:
        cfg = load_config(config_yaml)
        with pytest.raises(KeyError, match="not found"):
            cfg.get_controller("prod")

    def test_ako_defaults(self, config_yaml: Path) -> None:
        cfg = load_config(config_yaml)
        assert cfg.ako.namespace == "avi-system"


@pytest.mark.unit
class TestControllerPassword:
    """Password resolution from env vars."""

    def test_password_from_env(self) -> None:
        ctrl = ControllerConfig(name="lab", host="10.0.0.1")
        with patch.dict(os.environ, {"LAB_PASSWORD": "s3cret"}):
            assert ctrl.password == "s3cret"

    def test_password_missing_raises(self) -> None:
        ctrl = ControllerConfig(name="lab", host="10.0.0.1")
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(OSError, match="Password not found"):
                _ = ctrl.password

    def test_password_env_key_normalisation(self) -> None:
        ctrl = ControllerConfig(name="prod-dc1", host="10.0.0.2")
        with patch.dict(os.environ, {"PROD_DC1_PASSWORD": "pw"}):
            assert ctrl.password == "pw"


@pytest.mark.unit
class TestEnvPermissions:
    """Warn when .env has open permissions."""

    def test_no_warning_when_missing(self, tmp_path: Path) -> None:
        with patch("vmware_avi.config.ENV_FILE", tmp_path / "missing"):
            _check_env_permissions()  # should not raise

    def test_warning_on_world_readable(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("SECRET=x")
        env_file.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)  # 644
        with patch("vmware_avi.config.ENV_FILE", env_file):
            import logging
            with caplog.at_level(logging.WARNING, logger="vmware-avi.config"):
                _check_env_permissions()
        assert "Security warning" in caplog.text
