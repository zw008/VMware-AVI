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


def print_external(target: Console, text: object, max_len: int = 500) -> None:
    """Print text that came from outside AVI as inert, literal output.

    Ops functions do not return data — the MCP server swaps their module
    ``console`` for a capturing one, so whatever they print becomes the tool
    result an agent reads. That makes every print of external text an output
    boundary, and it needs both defences:

    * ``sanitize`` strips control characters (Rich passes ESC straight
      through) and caps length.
    * ``markup=False`` stops Rich reading ``[...]`` as styling. Without it
      ``[bold]`` is swallowed instead of shown, and a bare ``[/]`` raises
      ``MarkupError`` and kills the command. Order matters: stripping ESC out
      of ``\\x1b[31m`` leaves ``[31m``, so the markup lever has to hold after
      sanitize has run.

    Each line is capped independently, so one very long line cannot push the
    rest past the cut-off. The caller's own line budget (e.g. ``tail``) still
    bounds how many lines arrive.

    Args:
        target: The console to write to. Passed explicitly rather than taken
            from this module, because the caller's module-level ``console`` is
            what the MCP server rebinds when capturing.
        text: Untrusted text from the Controller, Kubernetes, or a client
            request. Non-str input is coerced.
        max_len: Per-line cap handed to ``sanitize``.
    """
    body = text if isinstance(text, str) else str(text)
    target.print(
        "\n".join(sanitize(line, max_len) for line in body.split("\n")),
        markup=False,
    )


def double_confirm(action: str) -> bool:
    """Require double confirmation for destructive operations."""
    console.print(f"\n[bold red]WARNING: {action}[/bold red]")
    first = console.input("  Are you sure? (yes/no): ").strip().lower()
    if first != "yes":
        return False
    second = console.input("  Confirm again to proceed (yes/no): ").strip().lower()
    return second == "yes"


#: Value keys whose contents are credentials, in any nesting, case-insensitive.
#: `helm get values` returns the *user-supplied* values of a release, so an AKO
#: installed with `--set avicredentials.password=...` has that password sitting
#: in its output — and this family prints that output to an agent.
_SECRET_KEY_HINTS = ("password", "passwd", "secret", "token", "apikey", "api_key",
                     "credential", "privatekey", "private_key")


def redact_yaml(text: str) -> str:
    """Blank credential-shaped values in a YAML document, structurally.

    Parsed and re-emitted with the YAML parser rather than regex-substituted:
    a hand-written pattern and the parser that actually reads the file disagree
    about quoting, folded scalars and indentation, and this family has already
    been bitten by that (踩坑 #38). If the text does not parse — a partial dump,
    a helm error page — nothing is returned rather than guessing, because a
    half-redacted secret is not a redacted secret.
    """
    import yaml

    def walk(node):
        if isinstance(node, dict):
            return {
                k: ("<redacted>"
                    if isinstance(k, str)
                    and any(h in k.lower() for h in _SECRET_KEY_HINTS)
                    and not isinstance(v, (dict, list))
                    else walk(v))
                for k, v in node.items()
            }
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node

    try:
        loaded = yaml.safe_load(text)
    except yaml.YAMLError:
        return ""
    if loaded is None:
        return ""
    return yaml.safe_dump(walk(loaded), default_flow_style=False, sort_keys=False)
