"""Environment diagnostics for VMware AVI.

Checks: AVI Controller connectivity, kubeconfig validity, SDK availability.
"""

from __future__ import annotations

import importlib
import logging
import os
import shutil
from pathlib import Path

from rich.console import Console

from vmware_avi.config import CONFIG_DIR, CONFIG_FILE, ENV_FILE, load_config

_log = logging.getLogger("vmware-avi.doctor")
console = Console()


def _config_read_only() -> bool | None:
    """Best-effort read of ``read_only`` from the config file.

    Deliberately a copy of the helper in ``vmware_avi.mcp_server.server`` rather than an
    import of it: importing that module registers every tool and applies the
    gate as a side effect. The two must be kept in step -- including the
    ``VMWARE_AVI_CONFIG`` override, without which an operator's custom config
    file would be silently ignored here while the gate honoured it, and the
    doctor would confidently report the wrong answer.
    """
    try:
        _cfg_path = os.environ.get("VMWARE_AVI_CONFIG")
        return load_config(Path(_cfg_path) if _cfg_path else None).read_only
    except Exception:  # noqa: BLE001 — absent/unreadable config is not an error here
        return None


def _check_read_only() -> tuple[bool, str]:
    """Report the resolved read-only state and where it came from.

    Never fails -- read-only being on is a posture, not a fault. It is here
    because an operator who set the switch had no way to confirm it took: the
    only signal was a line in the MCP server's start-up log.
    """
    from vmware_policy.readonly import read_only_status

    status = read_only_status("vmware-avi", _config_read_only())
    if not status.recognised:
        return True, (
            f"{status.source}={status.raw!r} is not a recognised value. It resolves "
            f"to ON (fail-closed), so every write tool is withheld — probably not "
            f"what was intended. Use true or false."
        )
    if status.enabled:
        return True, (
            f"ON (from {status.source}) — write tools are withheld from the MCP "
            f"registry. Clear that switch and restart the server to expose them."
        )
    return True, f"off (from {status.source}) — write tools are exposed"


def _check(label: str, ok: bool, detail: str = "") -> bool:
    status = "[green]PASS[/green]" if ok else "[red]FAIL[/red]"
    msg = f"  {status}  {label}"
    if detail:
        msg += f"  [dim]({detail})[/dim]"
    console.print(msg)
    return ok


def run_doctor() -> bool:
    """Run all diagnostic checks. Returns True if all pass."""
    console.print("\n[bold]vmware-avi doctor[/bold]\n")

    if not CONFIG_FILE.exists():
        console.print(
            "[yellow]No config found.[/yellow] Run [cyan]vmware-avi init[/cyan] "
            "for guided setup (writes config.yaml + .env, grep-safe password).\n"
            f"Or create {CONFIG_FILE} and {ENV_FILE} by hand "
            "(see config.example.yaml and .env.example).\n"
        )

    results: list[bool] = []

    # 1. Config directory
    results.append(
        _check(
            "Config directory exists",
            CONFIG_DIR.exists(),
            str(CONFIG_DIR),
        )
    )

    # 2. Config file
    results.append(
        _check(
            "config.yaml exists",
            CONFIG_FILE.exists(),
            str(CONFIG_FILE),
        )
    )

    # 3. .env file
    env_exists = ENV_FILE.exists()
    results.append(_check(".env file exists", env_exists, str(ENV_FILE)))

    if env_exists:
        import stat

        mode = ENV_FILE.stat().st_mode
        secure = not (mode & (stat.S_IRWXG | stat.S_IRWXO))
        results.append(
            _check(
                ".env permissions are 600",
                secure,
                oct(stat.S_IMODE(mode)),
            )
        )

    # 4. avisdk
    try:
        avi_mod = importlib.import_module("avi.sdk.avi_api")
        results.append(_check("avisdk installed", True, getattr(avi_mod, "__version__", "ok")))
    except ImportError:
        results.append(_check("avisdk installed", False, "pip install avisdk"))

    # 5. kubernetes client
    try:
        k8s_mod = importlib.import_module("kubernetes")
        results.append(
            _check(
                "kubernetes client installed",
                True,
                getattr(k8s_mod, "__version__", "ok"),
            )
        )
    except ImportError:
        results.append(_check("kubernetes client installed", False, "pip install kubernetes"))

    # 6. kubectl binary
    kubectl = shutil.which("kubectl")
    results.append(_check("kubectl in PATH", kubectl is not None, kubectl or "not found"))

    # 7. helm binary
    helm = shutil.which("helm")
    results.append(_check("helm in PATH", helm is not None, helm or "not found"))

    # 8. kubeconfig
    if CONFIG_FILE.exists():
        try:
            cfg = load_config()
            kc_path = Path(cfg.ako.kubeconfig).expanduser()
            results.append(_check("kubeconfig exists", kc_path.exists(), str(kc_path)))
        except Exception as exc:
            results.append(_check("kubeconfig exists", False, str(exc)))

    # 9. Controller connectivity
    if CONFIG_FILE.exists():
        try:
            cfg = load_config()
            for ctrl in cfg.controllers:
                try:
                    from vmware_avi.connection import AviConnectionManager

                    mgr = AviConnectionManager(cfg)
                    mgr.connect(ctrl.name)
                    mgr.disconnect(ctrl.name)
                    results.append(
                        _check(
                            f"Controller '{ctrl.name}' reachable",
                            True,
                            ctrl.host,
                        )
                    )
                except Exception as exc:
                    results.append(
                        _check(
                            f"Controller '{ctrl.name}' reachable",
                            False,
                            str(exc)[:80],
                        )
                    )
        except Exception:
            pass

    # 10. vmware-policy
    try:
        importlib.import_module("vmware_policy")
        results.append(_check("vmware-policy installed", True))
    except ImportError:
        results.append(_check("vmware-policy installed", False, "pip install vmware-policy"))

    # 11. Read-only mode (reported, never failed — it is a posture, not a fault)
    results.append(_check("Read-only mode", *_check_read_only()))

    passed = sum(results)
    total = len(results)
    console.print(f"\n  {passed}/{total} checks passed.\n")
    if not all(results):
        console.print(
            "  Some checks failed. Run [cyan]vmware-avi init[/cyan] to (re)create "
            "config.yaml + .env, or edit them under ~/.vmware-avi/ by hand.\n"
        )
    return all(results)
