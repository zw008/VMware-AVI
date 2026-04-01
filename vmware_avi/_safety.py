"""Safety utilities for destructive operations."""

from __future__ import annotations

from rich.console import Console

console = Console()


def double_confirm(action: str) -> bool:
    """Require double confirmation for destructive operations."""
    console.print(f"\n[bold red]WARNING: {action}[/bold red]")
    first = console.input("  Are you sure? (yes/no): ").strip().lower()
    if first != "yes":
        return False
    second = console.input("  Confirm again to proceed (yes/no): ").strip().lower()
    return second == "yes"
