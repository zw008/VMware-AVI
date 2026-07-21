"""Teaching error translation for the CLI.

avisdk raises ``APIError`` on a failed login (HTTP 401/403) and ``SSLError`` on
a TLS verification failure; the connection layer raises ``AviApiError`` for
translated REST errors. A raw traceback tells the user nothing about *where* to
fix the problem. ``cli_errors`` catches these and prints a message that names
the exact files to edit (``~/.vmware-avi/.env`` for the password,
``config.yaml`` for username/host/tenant), then exits non-zero.
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any

import typer
from rich.console import Console
from vmware_policy import PolicyDenied

console = Console()

_ENV_HINT = (
    "Fix the password in ~/.vmware-avi/.env "
    "(env var {NAME_UPPER}_PASSWORD), and the username/host/tenant in "
    "~/.vmware-avi/config.yaml. Re-run [cyan]vmware-avi init[/] to set them up."
)
_TLS_HINT = (
    "TLS certificate verification failed. AVI Controllers commonly ship "
    "self-signed certs — set [cyan]verify_ssl: false[/] for that controller in "
    "~/.vmware-avi/config.yaml (only safe on trusted networks)."
)


def _is_auth_error(exc: BaseException) -> bool:
    """A 401/403 login failure from avisdk surfaces as ``APIError`` whose
    message contains the status code, or our translated ``AviApiError``."""
    from vmware_avi.connection import AviApiError

    if isinstance(exc, AviApiError):
        return exc.status_code in (401, 403)
    text = str(exc)
    return "Status Code 401" in text or "Status Code 403" in text


def teach_and_exit(exc: BaseException) -> None:
    """If ``exc`` is an avisdk/connection auth or TLS failure, print a teaching
    message and raise ``typer.Exit(1)``. Otherwise return so the caller can
    re-raise the original exception unchanged.

    Shared by the ``cli_errors`` decorator (read commands) and ``_run_audited``
    (write commands) so both surfaces give identical guidance.
    """
    from avi.sdk.avi_api import APIError, SSLError

    if isinstance(exc, SSLError):
        console.print(f"[red]TLS error:[/] {exc}")
        console.print(_TLS_HINT)
        raise typer.Exit(1) from exc
    if isinstance(exc, APIError):
        if _is_auth_error(exc):
            console.print(f"[red]Authentication failed:[/] {exc}")
            console.print(_ENV_HINT)
        else:
            console.print(f"[red]AVI API error:[/] {exc}")
        raise typer.Exit(1) from exc

    from vmware_avi.connection import AviApiError

    if isinstance(exc, AviApiError) and _is_auth_error(exc):
        console.print(f"[red]Authentication failed:[/] {exc}")
        console.print(_ENV_HINT)
        raise typer.Exit(1) from exc


def cli_errors(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator: translate avisdk/connection auth & TLS failures into teaching
    messages, then ``typer.Exit(1)``. Other exceptions propagate unchanged."""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except (typer.Exit, typer.Abort):
            raise
        except PolicyDenied as exc:
            # @guarded ran guard() before the body, matched a deny / closed
            # maintenance-window rule, and already wrote the status="denied" audit
            # row before re-raising. Name the rule that fired instead of dumping a
            # traceback. Must precede `except Exception`: PolicyDenied is one, and
            # teach_and_exit would otherwise swallow it into a bare re-raise.
            rule = f" [dim](rule: {exc.result.rule})[/]" if exc.result.rule else ""
            console.print(f"[red]Denied by policy: {exc.result.reason}[/]{rule}")
            raise typer.Exit(1) from exc
        except Exception as exc:  # noqa: BLE001 — translated by teach_and_exit
            teach_and_exit(exc)  # raises typer.Exit for auth/TLS failures
            raise

    return wrapper
