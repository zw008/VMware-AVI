# VMware AVI Capabilities

All 29 MCP tools exposed by `vmware-avi-mcp`, organized by category.

## Traditional Mode — AVI Controller (12 tools)

### Virtual Service (3)

| Tool | Description | Parameters | Risk | Confirm |
|------|-------------|------------|:----:|:-------:|
| `vs_list` | List all Virtual Services on the active controller | `controller` (string, optional) | Low | No |
| `vs_status` | Show detailed status of a single VS (VIP, health score, pool binding, enabled state) | `name` (string, **required**) | Low | No |
| `vs_toggle` | Enable or disable a Virtual Service | `name` (string, **required**), `enable` (boolean, **required**) | Medium | Yes (disable) |

### Pool Member (3)

| Tool | Description | Parameters | Risk | Confirm |
|------|-------------|------------|:----:|:-------:|
| `pool_members` | List all members of a pool with health status and ratio | `pool` (string, **required**) | Low | No |
| `pool_member_enable` | Enable a pool member (restore traffic after maintenance) | `pool` (string, **required**), `server` (string, **required**) | Low | No |
| `pool_member_disable` | Disable a pool member with graceful connection drain | `pool` (string, **required**), `server` (string, **required**) | Medium | Yes |

### SSL Certificate (2)

| Tool | Description | Parameters | Risk | Confirm |
|------|-------------|------------|:----:|:-------:|
| `ssl_list` | List all SSL/TLS certificates on the controller | *(none)* | Low | No |
| `ssl_expiry_check` | Check certificates expiring within N days, with VS mapping | `days` (integer, default: 30) | Low | No |

### Analytics (2)

| Tool | Description | Parameters | Risk | Confirm |
|------|-------------|------------|:----:|:-------:|
| `vs_analytics` | Show VS metrics: throughput, latency, connections, error rates | `vs_name` (string, **required**) | Low | No |
| `vs_error_logs` | Show recent request error logs for a VS | `vs_name` (string, **required**), `since` (string, default: `"1h"`) | Low | No |

### Service Engine (2)

| Tool | Description | Parameters | Risk | Confirm |
|------|-------------|------------|:----:|:-------:|
| `se_list` | List all Service Engines with status and resource info | *(none)* | Low | No |
| `se_health` | Check SE health: CPU, memory, disk, HA status | *(none)* | Low | No |

## AKO Mode — Kubernetes (17 tools)

### AKO Pod Ops (4)

| Tool | Description | Parameters | Risk | Confirm |
|------|-------------|------------|:----:|:-------:|
| `ako_status` | Check AKO pod status (phase, restart count, readiness) | `context` (string, optional) | Low | No |
| `ako_logs` | View AKO pod logs (tail mode) | `tail` (integer, default: 100), `since` (string, optional) | Low | No |
| `ako_restart` | Restart AKO pod via rolling restart of the deployment | `context` (string, optional) | High | Yes |
| `ako_version` | Show AKO container image tag and Helm chart version | `context` (string, optional) | Low | No |

### AKO Config (3)

| Tool | Description | Parameters | Risk | Confirm |
|------|-------------|------------|:----:|:-------:|
| `ako_config_show` | Show current AKO Helm values (values.yaml snapshot) | *(none)* | Low | No |
| `ako_config_diff` | Show diff between running values and local chart values | *(none)* | Low | No |
| `ako_config_upgrade` | Helm upgrade AKO with updated values (defaults to dry-run) | `dry_run` (boolean, default: `true`) | High | Yes |

### Ingress Diagnostics (4)

| Tool | Description | Parameters | Risk | Confirm |
|------|-------------|------------|:----:|:-------:|
| `ako_ingress_check` | Validate Ingress annotations against AKO expectations in a namespace | `namespace` (string, **required**) | Low | No |
| `ako_ingress_map` | Show full Ingress-to-VS mapping across all namespaces | *(none)* | Low | No |
| `ako_ingress_diagnose` | Diagnose why a specific Ingress has no corresponding VS on the Controller | `name` (string, **required**), `namespace` (string, default: `"default"`) | Low | No |
| `ako_ingress_fix_suggest` | Suggest corrective actions for Ingress issues (annotation fixes, missing secrets) | `name` (string, **required**), `namespace` (string, default: `"default"`) | Low | No |

### Sync Diagnostics (3)

| Tool | Description | Parameters | Risk | Confirm |
|------|-------------|------------|:----:|:-------:|
| `ako_sync_status` | Check overall K8s-to-Controller sync health | *(none)* | Low | No |
| `ako_sync_diff` | Show objects present in K8s but missing on Controller, and vice versa | *(none)* | Low | No |
| `ako_sync_force` | Force AKO to re-reconcile all K8s objects against the Controller | *(none)* | Medium | Yes |

### Multi-cluster (3)

| Tool | Description | Parameters | Risk | Confirm |
|------|-------------|------------|:----:|:-------:|
| `ako_clusters` | List all K8s clusters with AKO deployed | *(none)* | Low | No |
| `ako_cluster_overview` | Cross-cluster AKO status overview (version, health, sync state per cluster) | *(none)* | Low | No |
| `ako_amko_status` | Show AMKO (Avi Multi-cluster Kubernetes Operator) GSLB status | *(none)* | Low | No |

## Risk Level Definitions

| Level | Meaning | Examples |
|-------|---------|---------|
| **Low** | Read-only query, no state change | `vs_list`, `ssl_expiry_check`, `ako_logs` |
| **Medium** | State change affecting traffic flow, but recoverable | `vs_toggle` (disable), `pool_member_disable`, `ako_sync_force` |
| **High** | Disruptive operation affecting running services or deployments | `ako_restart`, `ako_config_upgrade` |

## Tool Counts by Risk Level

| Risk | Count | Tools |
|------|:-----:|-------|
| Low | 22 | All read-only tools + `vs_toggle` (enable), `pool_member_enable` |
| Medium | 4 | `vs_toggle` (disable), `pool_member_disable`, `ako_sync_force`, `pool_member_enable` contextually |
| High | 3 | `ako_restart`, `ako_config_upgrade` (when `dry_run=false`), `vs_toggle` (disable on critical VS) |

> Note: `vs_toggle` with `enable=true` is Low risk. With `enable=false` it is Medium risk and requires confirmation. Similarly, `ako_config_upgrade` with `dry_run=true` is Low risk (preview only); with `dry_run=false` it becomes High risk.

## Audit Coverage

All 29 tools are wrapped with `@vmware_tool` from vmware-policy, which provides:

- **Pre-execution**: Policy rule check against `~/.vmware/rules.yaml` (deny rules, maintenance windows)
- **Post-execution**: Audit log entry written to `~/.vmware/audit.db` (SQLite WAL mode)
- **Input sanitization**: All AVI API response text processed through `_sanitize()` (truncation + control character cleanup)

## Traditional vs AKO Mode Requirements

| Requirement | Traditional Mode | AKO Mode |
|-------------|:----------------:|:--------:|
| AVI Controller access | Required | Optional (for sync tools) |
| avisdk Python package | Required | Not required |
| kubectl in PATH | Not required | Required |
| helm in PATH | Not required | Required (for config operations) |
| kubeconfig | Not required | Required |
| kubernetes Python package | Not required | Required |
