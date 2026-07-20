"""A failed AVI tool must not look like a successful one.

Every MCP tool in this skill runs a CLI ops function and hands back whatever it
printed. The ops layer reports failure the way a CLI does — print a red message,
then ``raise SystemExit(1)`` — and ``_capture_output`` caught that exception and
discarded it. The red text came back as the tool's ordinary return value.

Nothing downstream could tell the two apart. A model asking for a Virtual
Service that does not exist received the string "Virtual Service 'web-01' not
found." as a *successful* result, which is issue #31's reported failure mode:
the agent reads it as a finding and reports it to the user as fact rather than
recognising a fault and retrying with a corrected name.

Unhandled exceptions had the opposite problem — a missing config file raised
``FileNotFoundError`` straight out of the tool with its raw text, which can
carry paths and connection detail.

These tests pin both directions: failures are unmistakable, successes are
untouched, and neither leaks raw exception text.
"""

from __future__ import annotations

import pytest
from rich.console import Console

from vmware_avi.mcp_server import server as srv


@pytest.fixture
def op(monkeypatch):
    """Build an ops-style callable in a module that owns a ``console``.

    ``_capture_output`` swaps the *defining module's* ``console`` for a capturing
    one, so a test double has to live somewhere with that attribute. Binding it
    onto this test module mirrors how the real ops modules are laid out.
    """
    import sys

    mod = sys.modules[__name__]
    monkeypatch.setattr(mod, "console", Console(), raising=False)

    def _make(body):
        body.__module__ = __name__
        return body

    return _make


def test_successful_output_is_returned_unchanged(op):
    def fine():
        console.print("web-01  enabled  10.0.0.1")  # noqa: F821 — swapped in by _capture_output

    assert srv._capture_output(op(fine)).strip() == "web-01  enabled  10.0.0.1"


def test_failure_is_marked_as_an_error(op):
    def failing():
        console.print("[red]Virtual Service 'web-01' not found.[/red]")  # noqa: F821
        raise SystemExit(1)

    out = srv._capture_output(op(failing))
    assert out.startswith("Error:"), f"failure came back indistinguishable from success: {out!r}"


def test_failure_preserves_the_teaching_text(op):
    """The ops message is the useful part — wrapping must not replace it."""

    def failing():
        console.print(  # noqa: F821
            "[red]Virtual Service 'web-01' not found. "
            "Run vs_list to see available Virtual Services.[/red]"
        )
        raise SystemExit(1)

    out = srv._capture_output(op(failing))
    assert "web-01" in out
    assert "vs_list" in out


def test_failure_names_something_to_act_on_even_when_the_op_did_not(op):
    """A bare failure still has to leave the model somewhere to go."""

    def failing():
        console.print("[red]something went wrong[/red]")  # noqa: F821
        raise SystemExit(1)

    out = srv._capture_output(op(failing))
    assert "vmware-avi" in out


def test_clean_early_exit_is_not_an_error(op):
    """``SystemExit(0)`` is an ops function returning early, not failing."""

    def early():
        console.print("nothing to do")  # noqa: F821
        raise SystemExit(0)

    out = srv._capture_output(op(early))
    assert not out.startswith("Error:")
    assert "nothing to do" in out


def test_unexpected_exception_becomes_a_teaching_error(op):
    def broken():
        raise FileNotFoundError("/Users/someone/.vmware-avi/config.yaml")

    out = srv._capture_output(op(broken))
    assert out.startswith("Error:")
    assert "vmware-avi" in out


def test_unexpected_exception_does_not_leak_raw_text(op):
    """Exception text can carry hosts, paths and response bodies."""

    def broken():
        raise RuntimeError("https://admin:hunter2@avi.internal:443/api/virtualservice")

    out = srv._capture_output(op(broken))
    assert "hunter2" not in out


def test_console_is_restored_after_a_failure(op):
    """The swap is global to the ops module; leaking it would silently redirect
    every later CLI call in the same process into a dead buffer."""
    import sys

    mod = sys.modules[__name__]
    before = mod.console

    def failing():
        raise SystemExit(1)

    srv._capture_output(op(failing))
    assert mod.console is before
