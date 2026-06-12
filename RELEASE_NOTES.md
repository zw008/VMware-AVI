## v1.5.37 (2026-06-12) — backlog: AKO sync-diff accuracy

### Fixed
- `show_sync_diff` no longer falsely flags shard-mode Ingresses as "Missing on Controller" — it now also
  matches AKO-created pool names and prints a best-effort caveat. (#13)

## v1.5.36 (2026-06-12) — AKO release-blocker fix, honest write results, error translation

### Fixed
- **All AKO Kubernetes operations were crashing** (`AttributeError`) — `K8sConnectionManager` was
  built with the wrong config type at 10 call sites; now via `from_config()`. Status/logs/restart/
  version, sync, and ingress all work again. (Class-level test mocks had hidden the break.)
- **Write operations no longer report success on a failed PUT** — avisdk doesn't raise on 4xx/5xx,
  so `vs enable/disable` and pool-member drain now check the status code and surface a teaching error.
- **MCP `ako_config_upgrade` no longer corrupts the stdio channel** — added a `confirmed=False`
  preview gate (it previously printed to real stdout and blocked on stdin).
- Null-safe analytics log fields; pool `vs_filter` ref normalization.

### Added
- Centralized `AviApiError` translation in the connection layer (404 teaching hint, GET-only
  retry-once on 502/503/504, unreachable-controller hint).
- CLI write operations are now audited.

### Changed
- Removed two duplicate MCP tools (`ako_ingress_fix_suggest`, `ako_cluster_overview`); tool count
  is now **28 (22 read / 6 write)**, reflected across SKILL.md and READMEs.

## v1.5.35 (2026-06-10) — security fix: TLS verification now actually enforced

### Fixed
- **`verify_ssl` is now passed to avisdk** (`ApiSession.get_session(verify=…)`). Previously
  the flag was dropped and avisdk silently defaulted to no verification — the documented
  "TLS on by default" behaviour was non-functional. TLS verification now works as documented.
- **Output sanitization** centralized in `_safety.sanitize` and applied consistently to
  pool / Service Engine / SSL-cert / AKO-ingress / VS names from the API.

This release aligns the whole family back to a single version (1.5.35); vmware-policy and vmware-pilot return to the shared number after sitting at 1.5.22.

## v1.5.32 (2026-06-08) — Metric/field corrections + AKO helm/AMKO discovery fixes

### Fixed
- Latency metric is `l7_client.avg_client_txn_latency` (`avg_resp_latency`
  never existed in the AVI metrics catalog).
- SE listing reads `serviceengine-inventory` (the config object has no
  `oper_status` — the Status column was always N/A).
- SE→VS mapping derives the SE UUID from the `ref` URL (VipSeAssigned has no
  `uuid` field — VS counts were always 0).
- AKO helm: upgrades pull the official OCI chart
  (`oci://projects.packages.broadcom.com/ako/helm-charts/ako`) and the release
  name is discovered dynamically (official installs use `--generate-name`;
  the previous `avi/ako` alias + hardcoded `ako` release never worked).
- AMKO detection uses the chart's real labels (`app.kubernetes.io/name=amko`).
- Controller logout via POST (was DELETE → 405, silently swallowed; sessions
  never invalidated server-side).
- Error-log filter `ge(response_code,400)` (no longer flags 2xx/3xx as errors).

### Tests & docs
- +19 shape regression tests incl. a source scan that fails if the invented
  metric ID reappears; test-infra repairs; docs synced (30 tools).

## v1.5.30 (2026-06-07) — Tool description quality (Glama TDQS)

### Improved
- Rewrote MCP tool descriptions flagged by Glama's Tool Description Quality Score review:
  per-parameter semantics (format, defaults, valid values), return-field documentation,
  sibling-tool routing guidance, and behavioral transparency (side effects, audit logging,
  async semantics). Corrected descriptions that overstated or misstated actual behavior.
- No functional changes; descriptions only.

## v1.5.29 (2026-05-29) — Version Compatibility Table + Smithery/Container Docs

### Documentation
- `references/capabilities.md`: new "Version Compatibility" section with 4 sub-tables (AVI Controller 22.1.x/30.x, VCF 9.0/9.1, Python 3.11+, MCP transport modes). Mirrors NSX capabilities.md style with ✅/⚠ markers. Closes v1.5.23 and v1.5.11 doc gaps.
- `references/setup-guide.md`: replaced hardcoded "v1.4.0" header reference with "current release" + RELEASE_NOTES pointer; added "Alternative Deployment: Container / Smithery" section covering Docker build/run, Smithery registry, and a "When to use which" comparison table.
- `SKILL.md`: 1-line "Supported versions" callout pointing to capabilities.md; extended setup-guide pointer to mention container/Smithery.

### No code changes
Documentation-only release.

## v1.5.28 (2026-05-20)

**Fix `subclass() arg 1 must be a class` in goose/old mcp environments** —
v1.5.25–1.5.27 replaced `X | None` with `Optional[X]` but kept
`from __future__ import annotations` at the top of `mcp_server/server.py`.
Under mcp 1.10–1.13 (which Goose and some sandboxes pin), `Tool.from_function`
calls `issubclass(param.annotation, Context)` without resolving forward refs,
so string annotations crash the entire server load. Removed
`from __future__ import annotations` from `mcp_server/server.py` so annotations
are real classes; verified all tools load under mcp 1.10 and 1.14.

Traceback location: `mcp/server/fastmcp/tools/base.py:67`. CLAUDE.md 踩坑 #33
updated. family_smoke.sh Check 4b now installs `mcp==1.10.0` to catch this
regression class.

## v1.5.27 (2026-05-20)

**Loosen Python requirement: now supports Python >= 3.10** — v1.5.25/26 fixed
the PEP 604 root cause in MCP tool signatures (Optional[X] instead of X | None),
but kept `requires-python = ">=3.11"` and a 3.11 hard guard in `mcp_cmd`. Both
relaxed to 3.10 so users on Python 3.10 (e.g. Goose default sandbox, Ubuntu
22.04 system python) can install and run directly without a Python upgrade.

- `pyproject.toml`: `requires-python = ">=3.10"` (was `>=3.11`; VMware-VKS
  was `>=3.12`, now also `>=3.10` for family alignment).
- `<pkg>/cli.py` `mcp_cmd()`: version guard now triggers on `< (3, 10)`.
- Behavior on Python 3.10 matches 3.11/3.12 — the Optional[X] fix from v1.5.25
  is what actually enables this; this release just stops blocking installs.

---

## v1.5.26

**Family-wide MCP server fix — Python 3.10 compatibility (踩坑 #33)** — `vmware-avi mcp`
crashed at decorator time on Python 3.10 with `subclass() arg 1 must be a class`.
Root cause: `mcp_server/server.py` used PEP 604 `X | None` in tool signatures
plus `from __future__ import annotations`; on Python 3.10 + older mcp/pydantic
combos, `typing.get_type_hints()` evaluates `"str | None"` to a
`types.UnionType` instance, which FastMCP/Pydantic then feeds to `issubclass()`.
Reported by a goose user (qwen3.6:27, Python 3.10).

- `mcp_server/server.py`: all `X | None` → `Optional[X]`; ops layer untouched.
- `<pkg>/cli.py` `mcp_cmd()`: hard guard — exits with installation fix command
  if Python < 3.11 (defense in depth, our actual lower bound).
- `pyproject.toml`: `mcp[cli]>=1.10,<2.0` (was `>=1.0`) so uv doesn't pick
  an ancient version that has the same issubclass bug.

**Tooling — family smoke gains MCP schema-build check** — `scripts/family_smoke.sh`
new Check 4b runs `asyncio.run(mcp.list_tools())` per skill, forcing FastMCP to
build Pydantic models for every declared tool. Supports both module-level `mcp`
and `build_server()` factory patterns.

**Docs — CLAUDE.md gains 踩坑 #33 (PEP 604 / Python 3.10) and #34 (CLI/MCP exposure parity).**

---

## v1.5.24 (2026-05-19)

**Family version alignment** — no code changes in this skill. Bumped together
with VMware-AIops and VMware-VKS, which received a pyVmomi 8.x `ManagedObject`
setattr fix (踩坑 #32). `family_smoke.sh` now enforces the no-setattr rule
across all 9 skills.

## v1.5.23 (2026-05-19)

**VCF 9.0 / 9.1 compatibility declared.**

- **docs:** README now lists AVI / NSX ALB on VCF 9.0 / 9.1 as ✅ Full. The avisdk dependency (`>=22.1,<31.0`) covers AVI Controller versions bundled with VCF 9.x.
- **docs:** Added `Official Broadcom References` pointer to [VCF Python SDK](https://developer.broadcom.com/sdks) and the [AVI Controller REST API docs](https://developer.broadcom.com/xapis).
- **align:** Family v1.5.23 — all 9 skills tracking VCF 9.0 / 9.1 compatibility declaration.

## v1.5.22 (2026-05-08)

**Smithery onboarding** — `vmware-avi` is now installable via Smithery.

- **feat:** Added `Dockerfile` (Python 3.12-slim + uv) for containerized stdio MCP server.
- **feat:** Added `smithery.yaml` declaring stdio transport + config schema for the Smithery registry.
- **feat:** Added `mcp_server/__main__.py` so `python -m mcp_server` works inside the container.
- **align:** Tracks v1.5.22 family bump.

## v1.5.21 (2026-05-08)

**Family alignment** — no source changes in this skill.

- **deps:** Bumped `python-multipart` 0.0.26 → 0.0.27 (transitive, fixes GHSA HIGH DoS via unbounded multipart headers).
- **align:** Tracks v1.5.21 family bump driven by vmware-monitor folder_path feature (community PR #11).

## v1.5.20 (2026-05-08)

**Family alignment** — no source changes in this skill.

- **align:** Tracks v1.5.20 family bump driven by vmware-nsx-security and vmware-aria PyPI README `mcp-name:` ownership marker fix required by MCP Registry validation. Other 7 skills already had the marker; this release re-publishes them to keep the family version aligned per CLAUDE.md policy.
- **registry:** All 9 skills now registered on registry.modelcontextprotocol.io as `isLatest=true`.

## v1.5.19 (2026-05-06)

**Family alignment** — no source changes in this skill.

- **build:** Bumped `requires-python` from `>=3.10` to `>=3.11` (regression eval uses `tomllib`).
- **smoke:** Family `scripts/family_smoke.sh` adds Check 3b — recursive `--help` on every subcommand to surface broken lazy imports (yjs review 2026-05-06; 踩坑 #27).
- **align:** Tracks v1.5.19 fixes in vmware-nsx (CRITICAL CLI imports), vmware-vks (ApiClient leak), vmware-harden (Twin indexes + LEFT JOIN), vmware-policy (approval gate + singleton lock).

## v1.5.18 (2026-05-02)

**Family alignment + tooling normalization** — no source changes in this skill.

- **dev:** Migrated `[project.optional-dependencies] dev` → `[dependency-groups] dev` (PEP 735) so `uv sync --group dev` works uniformly across the family. Canonical set: `pytest>=8.0,<10.0`, `pytest-cov`, `ruff`.
- **test:** New `tests/eval/regression/test_release_blockers.py` (5 evals) catches the v1.5.x release blockers — missing `mcp_server` in wheel, AST-detected unimported runtime names, Typer app load failure, module import errors. Run via `pytest tests/eval/regression/`.
- **align:** Family version bump to v1.5.18.

## v1.5.17 (2026-05-01)

**Family alignment** — no source changes in this skill.

This release tracks vmware-pilot v1.5.17 (new `investigate_alert` template + `review_workflow` MCP tool + `parallel_group` step type) and vmware-policy v1.5.17 (L5 pattern matcher integrated into `@vmware_tool`). Both work with the existing skill MCP surface unchanged.

- **align:** Family version bump to v1.5.17.

## v1.5.16 (2026-04-30)

**Enterprise Harness Engineering alignment** — adapted from the Linkloud × addxai framework articles ([part 1](https://mp.weixin.qq.com/s/hz4W7ILHJ1yz_pG0Z1xP-A), [part 2](https://mp.weixin.qq.com/s/F3qYbyB3S8oIqx-Y4BrWNQ)).

- **docs:** "Automation Level Reference" section in `references/capabilities.md` — every tool tagged L1-L5 per the EHE framework.
- **docs:** Common Workflows in `SKILL.md` rewritten with pre-flight judgment for pool drain (capacity check / persistence behavior / observability baseline), AKO failure-layer triage, and SSL expiry audit.
- **align:** Family version bump to v1.5.16.

## v1.5.15 (2026-04-29)

**UX improvements from real user feedback**

- **feat:** New top-level CLI subcommand `vmware-avi mcp` starts the MCP server. Single command after `uv tool install vmware-avi` — no more `uvx --from`, no PyPI re-resolve, no TLS-proxy issues.
- **feat:** Default `verify_ssl: true` on new targets (was `false`). AVI Controller with default self-signed certs requires explicit `verify_ssl: false` in `config.yaml`.
- **docs:** README, SKILL.md, setup-guide.md, and `examples/mcp-configs/*.json` switched to `command: "vmware-avi"`, `args: ["mcp"]`. uvx form moved to fallback with TLS-proxy troubleshooting note.
- **compat:** Legacy `vmware-avi-mcp` console script kept — existing user configs continue to work.

## v1.5.14 (2026-04-21)

**Bug fixes from code review by @yjs-2026 (follow-up)**

- **fix:** `ako_ingress.py` — TLS secret checks now distinguish 404 (not found) from other errors (network, auth) instead of treating all exceptions as "not found"
- **fix:** `ako_ingress.py` — backend service path now checks for None on `backend`, `service`, and `name` before accessing

## v1.5.13 (2026-04-21)

**Bug fixes from code review 2026-04-20**

- **fix:** `ako_sync.py` — sync diff now uses exact + suffix match instead of substring match, preventing false negatives (e.g. ingress "ing" no longer matches "staging")
- **fix:** `ako_config.py` / `ako_multi_cluster.py` — all 7 `subprocess.run()` calls now have explicit `timeout` (30s kubectl, 120s helm, 300s upgrade) to prevent indefinite hangs

## v1.5.12 (2026-04-17)

- Align with VMware skill family v1.5.12 (security & bug fixes from code review by @yjs-2026)

## v1.5.11 (2026-04-17)

- Fix: vs_analytics HTTP 404 — AVI 22.x requires POST for `/analytics/metrics/collection` with `metric_requests[]` array wrapping (PR #4, credit @timwangbc)
- Fix: vs_error_logs HTTP 400 "VirtualService ID required" — added `virtualservice` URL param for VS UUID (PR #5, credit @timwangbc)
- Fix: pool_list vs_filter returned 0 matches for K8S-managed VSes — switched to `/virtualservice-inventory` which exposes the real VS→pool graph including pool groups (PR #6, credit @timwangbc)
- Fix: se_health VS count always 0 on 22.x — reconstructed SE→VS mapping by inverting `vip_summary[].service_engine[]` from `/virtualservice-inventory` (PR #7, credit @timwangbc)
- Tests: added unit tests for analytics, error logs, pool discovery, and SE health (14 new test cases)
- Result: 12/12 non-AKO MCP tools now pass against AVI Controller 22.x

## v1.5.10 (2026-04-16)

- Security: bump python-multipart 0.0.22→0.0.26 (DoS via large multipart preamble/epilogue)
- Align with VMware skill family v1.5.10

## v1.5.8 (2026-04-15)

- Feat: MCP server migrated from low-level `mcp.server.Server` to `FastMCP`, matching the rest of the family. All 30 tool names and input schemas preserved.
- Fix: 4 destructive MCP tools bypassed CLI's interactive `double_confirm` in MCP mode. Added `confirmed: bool = False` parameter with preview-by-default: `vs_toggle` (when disabling), `pool_member_disable`, `ako_restart`, `ako_sync_force`. Ops-layer functions now take `skip_prompt` so MCP callers that already validated `confirmed=True` bypass the stdio-blocking prompt.
- Align with VMware skill family v1.5.8

## v1.5.7 (2026-04-15)

- Align with VMware skill family v1.5.7 (Pilot `__from_step_N__` fix + VKS SSL/timeout fix)

## v1.5.6 (2026-04-15)

- Fix: CRITICAL — `mcp_server` module missing from PyPI wheel due to missing hatch packages config. MCP server would fail with `ModuleNotFoundError: No module named 'mcp_server'`. Added `[tool.hatch.build.targets.wheel] packages = ["vmware_avi", "mcp_server"]` to pyproject.toml
- Fix: FQDN in controller host config — avisdk rejected non-IP hostnames with "Invalid Controller IP6 Address". Connection manager now resolves FQDN -> IP via socket.getaddrinfo() at connect time
- Fix: vs_analytics returned empty series — switched from per-entity endpoint to analytics/metrics/collection with entity_uuid for consistent results across Controller 22.x/30.x versions
- Fix: vs_error_logs HTTP 400 — duration field now parsed via shorthand helper (accepts '1h', '30m', '24h', '7d' or raw seconds) and sent as integer seconds to match API contract
- Feat: vs_status now returns VIP(s), Pool, PoolGroup, health (oper_status), reason, throughput, new conn/s, latency, and SE placement
- Feat: se_health VS count derived from multiple known runtime fields (se_vs_list, vs_ref) for accurate counts across Controller versions
- Feat: new pool_list MCP tool — discover pools on controller with optional vs_filter substring; solves "pool names differ from VS names" discovery gap
- Credit: Tim (Taiwan TAM) for comprehensive v1.5.4 bug report

## v1.5.5 (2026-04-15)

- Align with VMware skill family v1.5.5

## v1.5.4 (2026-04-14)

- Security: bump pytest 9.0.2→9.0.3 (CVE-2025-71176, insecure tmpdir handling)

## v1.5.0 (2026-04-12)

### Anthropic Best Practices Integration

- **[READ]/[WRITE] tool prefixes**: All MCP tool descriptions now start with [READ] or [WRITE] to clearly indicate operation type
- **Read/write split counts**: SKILL.md MCP Tools section header shows exact read vs write tool counts
- **Negative routing**: Description frontmatter includes "Do NOT use when..." clause to prevent misrouting
- **Broadcom author attestation**: README.md, README-CN.md, and pyproject.toml include VMware by Broadcom author identity (wei-wz.zhou@broadcom.com) to resolve Snyk E005 brand warnings

### AVI-specific

- **Full tool description rewrite**: All 29 tool descriptions rewritten from 2-7 words to full When/What/Gotchas format with R/W column in SKILL.md

## v1.4.9 (2026-04-11)

- Fix: narrow AKO ingress trigger — only fire for Tanzu/vSphere AKO ingress, not generic nginx-ingress
- Fix: clarify vmware-policy compatibility field (Python transitive dep, not required standalone binary)

## v1.4.8 (2026-04-09)

- Security: bump cryptography 46.0.6→46.0.7 (CVE-2026-39892, buffer overflow)
- Security: bump urllib3 2.3.0→2.6.3 (multiple CVEs) [VMware-VKS]
- Security: bump requests 2.32.5→2.33.0 (medium CVE) [VMware-VKS]

## v1.4.7 (2026-04-08)

- Fix: align openclaw metadata with actual runtime requirements
- Fix: standardize audit log path to ~/.vmware/audit.db across all docs
- Fix: update credential env var docs to correct VMWARE_<TARGET>_PASSWORD convention
- Fix: declare .env config and vmware-policy optional dependency in metadata

# Release Notes

## v1.4.5 — 2026-04-03

- **Security**: bump pygments 2.19.2 → 2.20.0 (fix ReDoS CVE in GUID matching regex)
- **Infrastructure**: add uv.lock for reproducible builds and Dependabot security tracking

## v1.4.3 (2026-04-01)

Initial release — AVI (NSX Advanced Load Balancer) management and AKO Kubernetes operations.

### Features

**Traditional Mode (AVI Controller via avisdk)**
- Virtual Service list, status, enable/disable
- Pool member list, enable/disable (graceful drain)
- SSL certificate list and expiry check
- VS analytics and error logs
- Service Engine list and health check

**AKO Mode (Kubernetes via kubectl/K8s API)**
- AKO pod status, logs, restart, version info
- AKO Helm config view, diff, upgrade
- Ingress annotation validation and diagnosis
- K8s-to-Controller sync status, diff, force resync
- Multi-cluster AKO overview and AMKO status

**Infrastructure**
- Dual authentication: AVI Controller (config.yaml + .env) + K8s (kubeconfig)
- Multi-controller profile support
- Double confirmation for destructive operations
- Audit logging via vmware-policy
- 29 MCP tools + CLI commands
- Doctor command for environment diagnostics