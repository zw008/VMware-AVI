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
