"""Environment diagnostics for VMware AVI.

Checks: AVI Controller connectivity, kubeconfig validity, SDK availability.
"""

from __future__ import annotations

import importlib
import logging
import shutil
from pathlib import Path

from rich.console import Console
from rich.table import Table

from vmware_avi.config import CONFIG_DIR, CONFIG_FILE, ENV_FILE, load_config

_log = logging.getLogger("vmware-avi.doctor")
console = Console()


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
    results: list[bool] = []

    # 1. Config directory
    results.append(_check(
        "Config directory exists",
        CONFIG_DIR.exists(),
        str(CONFIG_DIR),
    ))

    # 2. Config file
    results.append(_check(
        "config.yaml exists",
        CONFIG_FILE.exists(),
        str(CONFIG_FILE),
    ))

    # 3. .env file
    env_exists = ENV_FILE.exists()
    results.append(_check(".env file exists", env_exists, str(ENV_FILE)))

    if env_exists:
        import stat

        mode = ENV_FILE.stat().st_mode
        secure = not (mode & (stat.S_IRWXG | stat.S_IRWXO))
        results.append(_check(
            ".env permissions are 600",
            secure,
            oct(stat.S_IMODE(mode)),
        ))

    # 4. avisdk
    try:
        avi_mod = importlib.import_module("avi.sdk.avi_api")
        results.append(_check("avisdk installed", True, getattr(avi_mod, "__version__", "ok")))
    except ImportError:
        results.append(_check("avisdk installed", False, "pip install avisdk"))

    # 5. kubernetes client
    try:
        k8s_mod = importlib.import_module("kubernetes")
        results.append(_check(
            "kubernetes client installed",
            True,
            getattr(k8s_mod, "__version__", "ok"),
        ))
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
                    results.append(_check(
                        f"Controller '{ctrl.name}' reachable",
                        True,
                        ctrl.host,
                    ))
                except Exception as exc:
                    results.append(_check(
                        f"Controller '{ctrl.name}' reachable",
                        False,
                        str(exc)[:80],
                    ))
        except Exception:
            pass

    # 10. vmware-policy
    try:
        importlib.import_module("vmware_policy")
        results.append(_check("vmware-policy installed", True))
    except ImportError:
        results.append(_check("vmware-policy installed", False, "pip install vmware-policy"))

    passed = sum(results)
    total = len(results)
    console.print(f"\n  {passed}/{total} checks passed.\n")
    return all(results)
