"""`helm get values` must not hand an agent the Controller password.

`helm get values <release>` returns the release's **user-supplied** values. An
AKO installed the documented way — `helm install --set avicredentials.password=…`
— therefore carries that password in its output, and `show_ako_config` printed
that output verbatim. In MCP mode the print *is* the tool result, so the
credential went straight into an agent's context.

Sanitisation does not help here: `sanitize()` truncates and strips control
characters, and a password survives both. This is the one place in the family
that needs redaction rather than cleaning, and the two are not interchangeable.

Redaction is structural — the YAML is parsed and re-emitted — because a regex
and the parser that actually reads the document disagree about quoting, folded
scalars and indentation (踩坑 #38). Unparseable input yields nothing rather than
a guess: a half-redacted secret is not a redacted secret.
"""

from __future__ import annotations

import pytest

from vmware_avi._safety import redact_yaml

VALUES = """\
ControllerSettings:
  controllerHost: avi.internal
  serviceEngineGroupName: Default-Group
avicredentials:
  username: admin
  password: hunter2
persistentVolumeClaim: ako-pvc
"""


def test_password_is_removed():
    out = redact_yaml(VALUES)
    assert "hunter2" not in out
    assert "<redacted>" in out


def test_everything_else_survives():
    """Redaction must not cost the operator the values they came to read."""
    out = redact_yaml(VALUES)
    for kept in ("avi.internal", "Default-Group", "admin", "ako-pvc"):
        assert kept in out, f"{kept!r} should not have been redacted"


@pytest.mark.parametrize(
    "key", ["password", "passwd", "apiToken", "client_secret", "PRIVATE_KEY", "apiKey"]
)
def test_credential_shaped_keys_are_caught_in_any_case_or_nesting(key):
    out = redact_yaml(f"outer:\n  inner:\n    {key}: s3cret\n")
    assert "s3cret" not in out, f"{key!r} was not treated as a credential"


def test_unparseable_input_yields_nothing_rather_than_a_guess():
    """A partial dump or an error page must not be printed unredacted."""
    assert redact_yaml("this: is: not: valid: yaml: [") == ""


def test_empty_document_is_not_mistaken_for_content():
    assert redact_yaml("") == ""
    assert redact_yaml("---\n") == ""


def test_show_ako_config_never_prints_the_password(monkeypatch, capsys):
    """End-to-end through the real ops function, not just the helper."""
    import subprocess

    from vmware_avi.ops import ako_config

    monkeypatch.setattr(ako_config, "_find_ako_release", lambda ns: "ako-1234")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **kw: subprocess.CompletedProcess(a[0], 0, VALUES, ""),
    )
    ako_config.show_ako_config("avi-system")

    out = capsys.readouterr().out
    assert "hunter2" not in out, "the Controller password reached the tool output"
    assert "avi.internal" in out, "redaction removed the values the operator needs"
