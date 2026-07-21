"""Every CLI command that performs a write is wrapped by @guarded (HLD I-1, I-8).

A write CLI command must route through vmware_policy's guard() + audit_call() —
the same enforcement @vmware_tool gives the MCP surface — so ``vmware-avi vs
disable`` run through Bash is authorized and audited to ~/.vmware/audit.db exactly
like the ``vs_toggle`` MCP tool. Without @guarded a CLI write bypassed policy and
landed only in the legacy per-skill log (the gap HLD §2.1 documents).

The write set is DERIVED, never hand-listed (踩坑 #43): a tool annotated
``readOnlyHint=False`` is a write; the ops functions its body uses are the
state-changing ops; a CLI ``@command`` using one is a write command and must
carry @guarded.

AVI's MCP tools do not *call* their ops — each hands the op to
``_capture_output(op, ...)`` as an argument. A derivation that matched only
direct calls would resolve zero write ops and pass vacuously — the "label
promises more than content" shape. So the scan matches any *reference* to an
imported ops name (an ``ast.Name``/``ast.Attribute`` use), which catches the
argument-passing form; imports are ``ast.alias`` nodes, never miscounted as uses.
"""
from __future__ import annotations

import ast
import asyncio
import pathlib

_REPO = pathlib.Path(__file__).resolve().parents[3]
CLI_FILE = _REPO / "vmware_avi" / "cli.py"
SERVER_FILE = _REPO / "vmware_avi" / "mcp_server" / "server.py"
assert CLI_FILE.is_file(), f"CLI module not found at {CLI_FILE} — the scan would find nothing"
assert SERVER_FILE.is_file(), f"MCP server not found at {SERVER_FILE} — derivation would be empty"


def _write_tool_names() -> frozenset[str]:
    from vmware_avi.mcp_server.server import mcp

    return frozenset(
        t.name
        for t in asyncio.run(mcp.list_tools())
        if getattr(getattr(t, "annotations", None), "readOnlyHint", None) is False
    )


def _ops_refs(tree: ast.AST) -> tuple[dict[str, str], set[str]]:
    """(local name -> REAL ops function name, ops-module aliases).

    An aliased import (``from ops.mod import realname as _alias``) maps
    ``_alias -> realname`` so an aliased use resolves to the same op an
    un-aliased import names. AVI imports the real name directly; the alias
    branch is kept so this derivation stays identical to the sibling REST skills.
    """
    func_map: dict[str, str] = {}
    mods: set[str] = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.module:
            parts = n.module.split(".")
            if "ops" in parts:
                if parts[-1] == "ops":
                    mods.update(a.asname or a.name for a in n.names)
                else:
                    for a in n.names:
                        func_map[a.asname or a.name] = a.name
    return func_map, mods


def _ops_used(node: ast.AST, func_map: dict[str, str], mods: set[str]) -> set[str]:
    """Real ops names referenced in ``node`` — used as ``f``/``f()`` or ``mod.f``.

    Matches any reference, not only a direct call, because AVI passes the op to
    ``_capture_output(op, ...)`` rather than calling it. Imports are ``ast.alias``
    nodes (not ``ast.Name``), so an import line is never counted as a use.
    """
    out: set[str] = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Name) and n.id in func_map:
            out.add(func_map[n.id])
        elif (
            isinstance(n, ast.Attribute)
            and isinstance(n.value, ast.Name)
            and n.value.id in mods
        ):
            out.add(n.attr)
    return out


def _write_ops() -> frozenset[str]:
    targets = _write_tool_names()
    assert targets, "no [WRITE] tools (readOnlyHint=False) — the MCP surface derivation is vacuous"
    tree = ast.parse(SERVER_FILE.read_text(encoding="utf-8"))
    func_map, mods = _ops_refs(tree)
    ops: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in targets:
            ops |= _ops_used(node, func_map, mods)
    return frozenset(ops)


def _decorator_names(node: ast.FunctionDef) -> set[str]:
    names: set[str] = set()
    for d in node.decorator_list:
        t = d.func if isinstance(d, ast.Call) else d
        if isinstance(t, ast.Name):
            names.add(t.id)
        elif isinstance(t, ast.Attribute):
            names.add(t.attr)
    return names


def _cli_write_commands() -> tuple[list[str], list[str]]:
    """(write commands, of those the ones missing @guarded)."""
    write_ops = _write_ops()
    assert write_ops, "no write ops derived — vacuous"
    tree = ast.parse(CLI_FILE.read_text(encoding="utf-8"))
    func_map, mods = _ops_refs(tree)
    writing: list[str] = []
    unguarded: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        if not any(
            isinstance(d, ast.Call)
            and isinstance(getattr(d, "func", None), ast.Attribute)
            and d.func.attr == "command"
            for d in node.decorator_list
        ):
            continue
        if _ops_used(node, func_map, mods) & write_ops:
            writing.append(node.name)
            if "guarded" not in _decorator_names(node):
                unguarded.append(node.name)
    return writing, unguarded


def test_every_write_cli_command_is_guarded():
    writing, unguarded = _cli_write_commands()
    assert len(writing) >= 4, (
        f"only {len(writing)} write CLI commands derived ({writing}) — the "
        f"MCP→ops→CLI derivation is likely stale; a check matching almost nothing "
        f"is worse than none."
    )
    assert not unguarded, (
        f"these CLI commands use a [WRITE] ops function but are not @guarded, so "
        f"they bypass policy + audit (HLD I-1): {unguarded}"
    )


def test_named_high_blast_radius_commands_are_derived_and_guarded():
    """Pin real command names so a broad-but-wrong derivation cannot pass the floor.

    Both resolve only when the scan follows the op *reference* AVI hands to
    ``_capture_output`` — their presence proves that argument-passing path works,
    the AVI analog of AIops pinning ``deploy_ova_cmd``.
    """
    writing, _ = _cli_write_commands()
    names = set(writing)
    for must in ("vs_disable", "ako_restart"):
        assert must in names, (
            f"{must} is no longer derived as a write command — the readOnlyHint→"
            f"ops→command derivation stopped resolving it"
        )
