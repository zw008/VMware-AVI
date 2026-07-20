"""A controller must declare its environment, and writes are scoped by it.

Policy rules scope by environment ("irreversible work in production needs a
second person"). Environment used to be derived from the *target's name*, so
those rules only fired when an operator happened to name a controller the exact
string in the rule — nobody names a controller "production", so the control was
configured and inert.

Environment is now an explicit `environment:` declaration in config.yaml. The
rollout is two steps, because the end state refuses operations that work today:

  * the shipped baseline sets ``require_declared_environment: warn`` — an
    undeclared write RUNS and logs a warning naming the fix;
  * the next major release ships ``true`` and REFUSES it.

Both behaviours are pinned here (the ``baseline`` and ``enforcing`` fixtures),
so the enforcing release is a one-word change to a path already under test
rather than a leap. Reads are never gated under either setting.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from vmware_avi.config import AkoConfig, AppConfig, ControllerConfig
from vmware_policy.decorators import PolicyDenied
from vmware_policy.environment import set_environment_resolver
from vmware_policy.policy import get_policy_engine, reset_policy_engine


def _config(environment: str) -> AppConfig:
    return AppConfig(
        controllers=(
            ControllerConfig(
                name="lab", host="10.0.0.1", config_username="admin", environment=environment
            ),
        ),
        default_controller="lab",
        ako=AkoConfig(kubeconfig="/tmp/fake-kubeconfig", namespace="avi-system"),
    )


@pytest.fixture()
def declared(request: pytest.FixtureRequest):
    """Run the MCP server's real resolver over a config we control.

    ``request.param`` is what the controller declares — "" for an unlabelled
    controller.
    """
    from vmware_avi.mcp_server import server

    with patch("vmware_avi.mcp_server.server._cached_config", return_value=_config(request.param)):
        set_environment_resolver(server._environment_for)
        yield
    set_environment_resolver(None)


@pytest.fixture()
def baseline():
    """The shipped policy baseline — currently the warn-only migration setting."""
    reset_policy_engine()
    get_policy_engine()
    yield
    reset_policy_engine()


@pytest.fixture()
def enforcing(tmp_path):
    """The same rules with the requirement switched on, as the next major
    release will ship it."""
    rules = tmp_path / "rules.yaml"
    rules.write_text("require_declared_environment: true\n")
    reset_policy_engine()
    get_policy_engine(rules)
    yield
    reset_policy_engine()


# ---------------------------------------------------------------------------
# Migration window (shipped today): undeclared writes run, but warn
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("declared", [""], indirect=True)
def test_undeclared_write_runs_and_warns_under_baseline(declared, baseline) -> None:
    """Nothing breaks for operators who have not labelled their estate yet."""
    from vmware_avi.mcp_server import server

    with patch("vmware_avi.ops.ako_config.upgrade_ako") as mock_upgrade:
        server.ako_config_upgrade(dry_run=False, confirmed=True)

    mock_upgrade.assert_called_once()

    result = get_policy_engine().check_allowed(
        "ako_config_upgrade", env="", risk_level="medium"
    )
    assert result.allowed is True
    assert result.rule == "undeclared_environment_warning"
    assert "future release will refuse" in result.reason.lower()


# ---------------------------------------------------------------------------
# Enforcing release: undeclared writes are refused
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("declared", [""], indirect=True)
def test_undeclared_write_is_denied_when_enforcing(declared, enforcing) -> None:
    from vmware_avi.mcp_server import server

    with patch("vmware_avi.ops.ako_config.upgrade_ako") as mock_upgrade:
        with pytest.raises(PolicyDenied) as excinfo:
            server.ako_config_upgrade(dry_run=False, confirmed=True)

    # The operation must not have reached the estate.
    mock_upgrade.assert_not_called()
    assert excinfo.value.result.rule == "undeclared_environment"


@pytest.mark.unit
@pytest.mark.parametrize("declared", [""], indirect=True)
def test_denial_names_the_config_key(declared, enforcing) -> None:
    """An operator has to be able to act on the refusal without reading code."""
    from vmware_avi.mcp_server import server

    with patch("vmware_avi.ops.ako_config.upgrade_ako"):
        with pytest.raises(PolicyDenied) as excinfo:
            server.ako_config_upgrade(dry_run=False, confirmed=True)

    reason = str(excinfo.value)
    assert "environment" in reason
    assert "config.yaml" in reason


@pytest.mark.unit
@pytest.mark.parametrize("declared", ["lab"], indirect=True)
def test_declared_controller_allows_writes_when_enforcing(declared, enforcing) -> None:
    """Declaring the environment is all it takes to be unblocked."""
    from vmware_avi.mcp_server import server

    with patch("vmware_avi.ops.ako_config.upgrade_ako") as mock_upgrade:
        server.ako_config_upgrade(dry_run=False, confirmed=True)

    mock_upgrade.assert_called_once()


# ---------------------------------------------------------------------------
# Reads are never gated, under either setting
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("declared", ["", "lab"], indirect=True)
@pytest.mark.parametrize("mode", ["baseline", "enforcing"])
def test_reads_are_never_gated(declared, mode, request) -> None:
    """Inspection must keep working on an estate nobody has labelled yet."""
    request.getfixturevalue(mode)
    from vmware_avi.mcp_server import server

    with patch("vmware_avi.ops.ako_config.show_ako_config") as mock_show:
        server.ako_config_show()

    mock_show.assert_called_once()


# ---------------------------------------------------------------------------
# Wiring
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestResolverIsRegisteredAtImport:
    def test_importing_the_server_wires_the_resolver(self) -> None:
        """Dropping set_environment_resolver() would brick every write later.

        Without a resolver every controller reads as undeclared. Under today's
        warn setting that is invisible — the writes still run — so a lost
        registration would only surface when the enforcing release lands and
        refuses everything. Pin the registration itself.
        """
        import importlib

        import vmware_policy.environment as env_mod
        from vmware_avi.mcp_server import server

        set_environment_resolver(None)
        try:
            importlib.reload(server)
            assert env_mod._resolver is not None
            assert env_mod._resolver is server._environment_for
        finally:
            set_environment_resolver(None)


@pytest.mark.unit
class TestConfigParsesTheDeclaration:
    def test_environment_is_read_from_yaml(self, tmp_path) -> None:
        from vmware_avi.config import load_config

        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text(
            "controllers:\n"
            "  - name: lab\n"
            "    host: 10.0.0.1\n"
            "    environment: lab\n"
            "  - name: prod\n"
            "    host: 10.0.0.2\n"
            "default_controller: lab\n"
        )
        cfg = load_config(cfg_file)

        assert cfg.environment_for("lab") == "lab"
        # Declaring nothing must read as undeclared, not as a default.
        assert cfg.environment_for("prod") == ""
        # An omitted controller resolves via default_controller, so policy and
        # the connection layer never disagree about which host is in play.
        assert cfg.environment_for(None) == "lab"
        # An unknown name is undeclared rather than an exception escaping into
        # a tool call.
        assert cfg.environment_for("nope") == ""

    def test_whitespace_only_declaration_is_undeclared(self, tmp_path) -> None:
        from vmware_avi.config import load_config

        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text(
            "controllers:\n"
            "  - name: lab\n"
            "    host: 10.0.0.1\n"
            "    environment: '   '\n"
            "default_controller: lab\n"
        )
        assert load_config(cfg_file).environment_for("lab") == ""

    def test_unreadable_config_reads_as_undeclared(self) -> None:
        """A broken config must fail closed, not raise into the tool call."""
        from vmware_avi.mcp_server import server

        with patch(
            "vmware_avi.config.load_config", side_effect=FileNotFoundError("no config")
        ):
            assert server._environment_for("lab") == ""
