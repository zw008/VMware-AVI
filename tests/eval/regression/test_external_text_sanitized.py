"""Externally-sourced text reaches the agent inert, on the success path too.

The family rule (CLAUDE.md, "数据消毒") is that any text originating outside the
skill passes ``sanitize()`` before an agent can read it. AVI honoured that on
its *error* paths and skipped it on its *success* paths, because ops functions
do not return data — they print through Rich to a console the MCP server swaps
out and captures. Whatever those functions print IS the tool result.

Two distinct failures follow from printing raw external text through Rich:

1. ``console.print`` parses ``[...]`` as style markup. ``[bold]`` is swallowed
   rather than shown, so a pod log can restyle the transcript an agent reads;
   and a bare ``[/]`` — which needs no attacker, just a log line that happens
   to contain it — raises ``MarkupError`` and takes the whole command down.
2. Rich does not strip control characters. ``sanitize`` does, and it must run
   *before* the markup lever, because stripping ESC out of ``\\x1b[31m`` leaves
   ``[31m`` — text Rich would then read as markup.

So both levers are load-bearing: ``sanitize()`` for the bytes, ``markup=False``
for the parse. Neither alone is sufficient, and the tests below pin each.

The two paths covered here are the ones that carry the least-trusted text in
the skill:

* ``view_ako_logs`` — raw Kubernetes pod logs, i.e. whatever any workload in
  the cluster wrote to stdout.
* ``show_error_logs`` — the request ``uri_path`` recorded by the load balancer,
  i.e. a string chosen by any unauthenticated client on the internet that sent
  the VS a request that 4xx'd.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from io import StringIO
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from rich.console import Console


@contextmanager
def _capturing(module) -> Iterator[StringIO]:
    """Replace a module's Rich console with a capturing one, as MCP does.

    Mirrors ``vmware_avi.mcp_server.server._capture_output``: the console is
    rebound on the module object, so ops code that resolves ``console`` at call
    time writes into the buffer instead of the terminal.

    A context manager rather than a swap/restore pair because the pair is easy
    to write in the wrong order — reading the "original" after the swap
    restores the capturing console instead of the real one and leaks a
    StringIO into every later test in the session.
    """
    buf = StringIO()
    original = module.console
    module.console = Console(file=buf, force_terminal=False, width=200)
    try:
        yield buf
    finally:
        module.console = original


# Payload carrying all three hazards at once: markup that would be swallowed,
# an unbalanced closing tag that raises MarkupError, and control characters
# (ESC-based ANSI, BEL) that Rich passes straight through.
HOSTILE = "start [bold]INJECTED[/bold] mid [/] \x1b[31mred\x07 end"


# ---------------------------------------------------------------------------
# Kubernetes pod logs — view_ako_logs
# ---------------------------------------------------------------------------


def _run_view_logs(log_text: str, sample_config) -> str:
    from vmware_avi.ops import ako_pod

    pod = SimpleNamespace(metadata=SimpleNamespace(name="ako-0"))
    core = MagicMock()
    core.list_namespaced_pod.return_value.items = [pod]
    core.read_namespaced_pod_log.return_value = log_text

    with (
        _capturing(ako_pod) as buf,
        patch("vmware_avi.ops.ako_pod.load_config", return_value=sample_config),
        patch("vmware_avi.ops.ako_pod.K8sConnectionManager") as mock_k8s_cls,
    ):
        mock_k8s_cls.from_config.return_value = mock_k8s_cls.return_value
        mock_k8s_cls.return_value.core_v1.return_value = core
        mock_k8s_cls.return_value.namespace = "avi-system"
        ako_pod.view_ako_logs(tail=50)
    return buf.getvalue()


@pytest.mark.unit
def test_pod_log_markup_is_shown_not_interpreted(sample_config) -> None:
    """A log line's ``[bold]`` must reach the agent as characters, not styling.

    Interpreted markup is worse than ugly: the tags vanish from the text the
    agent reads, so a workload writing to stdout can edit the transcript of a
    tool it does not own.
    """
    out = _run_view_logs("app started [bold]ALL CHECKS PASSED[/bold]", sample_config)
    assert "[bold]ALL CHECKS PASSED[/bold]" in out


@pytest.mark.unit
def test_pod_log_with_unbalanced_tag_does_not_kill_the_command(sample_config) -> None:
    """``[/]`` anywhere in a pod log used to raise MarkupError mid-print.

    No attacker required — any log line containing ``[/]`` made
    ``vmware-avi ako logs`` unusable, and the failure surfaced as a Rich
    traceback rather than as anything about AKO.
    """
    out = _run_view_logs("closing [/] tag", sample_config)
    assert "closing [/] tag" in out


@pytest.mark.unit
def test_pod_log_control_characters_are_stripped(sample_config) -> None:
    """ESC and BEL must not reach a terminal or an agent's context."""
    out = _run_view_logs(HOSTILE, sample_config)
    assert "\x1b" not in out
    assert "\x07" not in out
    # Stripping ESC leaves "[31m", which Rich would parse as markup — the
    # markup lever has to hold after sanitize has run.
    assert "[31m" in out


@pytest.mark.unit
def test_pod_log_line_length_is_bounded(sample_config) -> None:
    """One monster line must not blow the agent's context budget.

    ``tail`` bounds how many lines arrive; sanitize bounds how long each one
    can be. Without the per-line cap a single 10MB log line is a whole
    context window.

    Counted rather than matched as a run: Rich soft-wraps a long line to the
    console width, so the 500 surviving characters arrive split across
    display rows.
    """
    # "Z" appears nowhere in the "AKO Logs (ako-0)" header, so every hit in
    # the capture came from the log body.
    out = _run_view_logs("Z" * 50_000, sample_config)
    assert out.count("Z") == 500


@pytest.mark.unit
def test_pod_log_keeps_its_line_structure(sample_config) -> None:
    """Sanitizing must not collapse a multi-line log into one line."""
    out = _run_view_logs("first line\nsecond line\nthird line", sample_config)
    for expected in ("first line", "second line", "third line"):
        assert expected in out
    assert out.count("\n") >= 3


# ---------------------------------------------------------------------------
# Client-supplied request paths — show_error_logs
# ---------------------------------------------------------------------------


def _run_error_logs(uri_path: str, mock_avi_session: MagicMock) -> str:
    from vmware_avi.ops import analytics

    mock_avi_session.get_object_by_name.return_value = {"name": "web-vs", "uuid": "vs-abc"}
    mock_avi_session.get.return_value.json.return_value = {
        "results": [
            {
                "report_timestamp": "2026-07-20T10:00:00Z",
                "response_code": 404,
                "uri_path": uri_path,
                "client_ip": "203.0.113.9",
            }
        ]
    }

    with _capturing(analytics) as buf:
        analytics.show_error_logs("web-vs", since="1h")
    return buf.getvalue()


@pytest.mark.usefixtures("_patch_avi_connect")
@pytest.mark.unit
def test_request_uri_markup_is_shown_not_interpreted(mock_avi_session: MagicMock) -> None:
    """``uri_path`` is chosen by whoever sent the request — treat it as hostile.

    This is the widest-open input in the skill: no authentication is needed to
    put a string here, only an HTTP request to the load balancer that 4xx's.
    """
    out = _run_error_logs("/[bold]admin[/bold]", mock_avi_session)
    assert "[bold]admin[/bold]" in out


@pytest.mark.usefixtures("_patch_avi_connect")
@pytest.mark.unit
def test_request_uri_with_unbalanced_tag_does_not_kill_the_command(
    mock_avi_session: MagicMock,
) -> None:
    """One crafted request must not make the error-log view unusable."""
    out = _run_error_logs("/oops[/]", mock_avi_session)
    assert "/oops[/]" in out


@pytest.mark.usefixtures("_patch_avi_connect")
@pytest.mark.unit
def test_request_uri_control_characters_are_stripped(mock_avi_session: MagicMock) -> None:
    out = _run_error_logs("/x\x1b[31m\x07y", mock_avi_session)
    assert "\x1b" not in out
    assert "\x07" not in out


@pytest.mark.usefixtures("_patch_avi_connect")
@pytest.mark.unit
def test_request_uri_stays_bounded(mock_avi_session: MagicMock) -> None:
    """The 80-char cap predates this fix and must survive it.

    ``sanitize`` strips before it truncates, so padding the front with control
    characters can no longer push a payload past the cut-off — which is what a
    bare ``[:80]`` slice allowed.
    """
    out = _run_error_logs("\x00" * 200 + "B" * 200, mock_avi_session)
    assert "B" * 81 not in out
    assert "B" * 80 in out
