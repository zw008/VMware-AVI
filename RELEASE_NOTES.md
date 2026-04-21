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