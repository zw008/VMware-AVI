"""Safety utilities for destructive operations and output sanitization."""

from __future__ import annotations

from rich.console import Console
from vmware_policy import sanitize as _policy_sanitize

console = Console()


def sanitize(text: object, max_len: int = 500) -> str:
    """Truncate + strip control characters from AVI/K8s API text before output.

    Thin wrapper over the canonical family-wide ``vmware_policy.sanitize`` so all
    AVI ops modules share one prompt-injection defence. Non-str inputs are
    coerced to str first (API fields are occasionally None/ints).
    """
    return _policy_sanitize(text if isinstance(text, str) else str(text), max_len)


def double_confirm(action: str) -> bool:
    """Require double confirmation for destructive operations."""
    console.print(f"\n[bold red]WARNING: {action}[/bold red]")
    first = console.input("  Are you sure? (yes/no): ").strip().lower()
    if first != "yes":
        return False
    second = console.input("  Confirm again to proceed (yes/no): ").strip().lower()
    return second == "yes"
