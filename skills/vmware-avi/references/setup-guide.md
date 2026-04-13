# VMware AVI Setup Guide

Complete installation, configuration, and AI platform integration guide for vmware-avi v1.4.0.

## Prerequisites

| Requirement | Version | Purpose |
|-------------|---------|---------|
| Python | >= 3.10 | Runtime |
| uv | >= 0.4 | Package manager and tool runner |
| avisdk | >= 22.1 | AVI Controller API (auto-installed) |
| kubernetes (Python) | >= 28.0 | K8s API client for AKO operations (auto-installed) |
| kubectl | any recent | Required for AKO pod/ingress/sync operations |
| helm | >= 3.x | Required for AKO config show/diff/upgrade |
| vmware-policy | >= 1.0.0 | Audit and policy engine (auto-installed) |

**Optional**: `kubeconfig` file with access to clusters running AKO (only needed for AKO mode).

## Installation

### Standard Install (recommended)

```bash
uv tool install vmware-avi
```

This installs the CLI (`vmware-avi`), MCP server entry point (`vmware-avi-mcp`), and all Python dependencies in an isolated environment.

### Development Install

```bash
git clone https://github.com/zw008/VMware-AVI.git
cd VMware-AVI
uv pip install -e ".[dev]"
```

### Verify Installation

```bash
vmware-avi doctor
```

The `doctor` command checks all of the following:
- Config directory and files exist
- `.env` file permissions are 600
- avisdk and kubernetes Python packages installed
- kubectl and helm binaries in PATH
- kubeconfig file exists
- AVI Controller(s) reachable
- vmware-policy package installed

## AVI Controller Configuration

### Step 1: Generate config templates

```bash
vmware-avi init
```

This creates two files in `~/.vmware-avi/`:
- `config.yaml` -- connection targets and AKO settings
- `.env` -- passwords (auto-set to chmod 600)

### Step 2: Edit config.yaml

```yaml
# ~/.vmware-avi/config.yaml
controllers:
  - name: prod-avi
    host: avi-controller.example.com
    username: admin
    api_version: "22.1.4"
    tenant: admin
    port: 443
    verify_ssl: true

  - name: staging-avi
    host: avi-staging.example.com
    username: admin
    api_version: "22.1.4"
    tenant: admin
    verify_ssl: false    # lab/self-signed certs only

default_controller: prod-avi

ako:
  kubeconfig: ~/.kube/config
  default_context: ""        # empty = use current-context
  namespace: avi-system
```

**config.yaml fields**:

| Field | Required | Default | Description |
|-------|:--------:|---------|-------------|
| `controllers[].name` | Yes | -- | Unique identifier for this controller |
| `controllers[].host` | Yes | -- | Controller hostname or IP |
| `controllers[].username` | No | `admin` | API username |
| `controllers[].api_version` | No | `22.1.4` | AVI API version string |
| `controllers[].tenant` | No | `admin` | AVI tenant name |
| `controllers[].port` | No | `443` | Controller HTTPS port |
| `controllers[].verify_ssl` | No | `true` | TLS certificate verification |
| `default_controller` | No | first entry | Which controller to use by default |
| `ako.kubeconfig` | No | `~/.kube/config` | Path to kubeconfig file |
| `ako.default_context` | No | current-context | K8s context for AKO operations |
| `ako.namespace` | No | `avi-system` | Namespace where AKO is deployed |

### Step 3: Set passwords in .env

```bash
# ~/.vmware-avi/.env
PROD_AVI_PASSWORD=your-secure-password-here
STAGING_AVI_PASSWORD=another-password-here
```

Password environment variable naming convention: `<CONTROLLER_NAME>_PASSWORD` where the controller name is uppercased and hyphens are replaced with underscores.

| Controller Name | Environment Variable |
|-----------------|---------------------|
| `prod-avi` | `PROD_AVI_PASSWORD` |
| `staging-avi` | `STAGING_AVI_PASSWORD` |
| `my-lab` | `MY_LAB_PASSWORD` |

### Step 4: Verify connectivity

```bash
vmware-avi doctor
vmware-avi vs list          # quick smoke test
```

## AKO / Kubernetes Configuration

AKO operations require a valid kubeconfig with access to the cluster(s) where AKO is deployed.

### kubeconfig Setup

```bash
kubectl --context my-cluster get pods -n avi-system   # verify access
kubectl config get-contexts                            # list all contexts
```

If your AKO is deployed in a non-default namespace, update `ako.namespace` in config.yaml. AKO config commands (`config-show`, `config-diff`, `config-upgrade`) require Helm 3.x:

```bash
helm repo add ako https://projects.registry.vmware.com/chartrepo/ako
helm repo update
```

## Security

> **Disclaimer**: This is a community-maintained open-source project and is **not affiliated with, endorsed by, or sponsored by VMware, Inc. or Broadcom Inc.** "VMware", "NSX", and "AVI" are trademarks of Broadcom.

### Password Management

- Passwords are **never** stored in `config.yaml` -- only in `.env`
- The `.env` file must have `chmod 600` permissions (owner read/write only)
- `vmware-avi doctor` warns if `.env` permissions are too open
- Never commit `.env` files to version control

### Audit Logging

All operations (CLI and MCP) are recorded via vmware-policy:

- **Location**: `~/.vmware/audit.db` (SQLite, WAL mode)
- **Contents**: timestamp, tool name, parameters, result, user identity
- **Query**: `vmware-audit log --last 20`

### Policy Rules

Optional deny rules and maintenance windows can be configured in `~/.vmware/rules.yaml` (managed by vmware-policy). Example: block `vs_toggle` disable during business hours.

### Destructive Operation Safety

| Operation | Safety Measures |
|-----------|----------------|
| VS disable | Double confirmation prompt |
| Pool member disable | Double confirmation prompt (graceful drain) |
| AKO restart | Double confirmation prompt |
| AKO config upgrade | Defaults to `--dry-run`; double confirmation for actual apply |
| AKO sync force | Double confirmation prompt |

### Data Sanitization

All text returned from AVI Controller APIs is processed through `_sanitize()`:
- Truncated to 500 characters maximum
- C0/C1 control characters stripped
- Prevents prompt injection via API response content

### TLS Verification

- Enabled by default (`verify_ssl: true`)
- Set `verify_ssl: false` only for lab environments with self-signed certificates
- Production deployments should always use valid TLS certificates

## AI Platform Compatibility

vmware-avi supports MCP (Model Context Protocol) integration with the following platforms.

### Claude Code (Claude Desktop / CLI)

Add to `~/.claude.json` (global) or `.mcp.json` (project-level):

```json
{
  "mcpServers": {
    "vmware-avi": {
      "command": "uvx",
      "args": ["--from", "vmware-avi", "vmware-avi-mcp"],
      "env": {
        "VMWARE_AVI_CONFIG": "~/.vmware-avi/config.yaml"
      }
    }
  }
}
```

### Cursor

Add to `.cursor/mcp.json` in your project root:

```json
{
  "mcpServers": {
    "vmware-avi": {
      "command": "uvx",
      "args": ["--from", "vmware-avi", "vmware-avi-mcp"],
      "env": {
        "VMWARE_AVI_CONFIG": "~/.vmware-avi/config.yaml"
      }
    }
  }
}
```

### Windsurf / Cline / Qwen / Other MCP-compatible Agents

Use the same JSON block as above, placed in the platform-specific config file:

| Platform | Config File |
|----------|-------------|
| Windsurf | `~/.windsurf/mcp.json` |
| Cline (VS Code) | Cline MCP settings panel |
| Qwen / other | Any MCP stdio transport config |

### Ollama / Local Models

For local models with limited context windows, prefer CLI mode over MCP:

```bash
# CLI produces ~2K tokens vs ~8K for MCP JSON
vmware-avi vs list
vmware-avi ako status
```

If your Ollama setup supports MCP via a bridge (e.g., `mcp-bridge`), use the same `uvx --from` command.

## Troubleshooting

### "Config file not found" on first run

```bash
vmware-avi init    # generates ~/.vmware-avi/config.yaml and .env
```

### "Password not found" error

The environment variable name must match `<CONTROLLER_NAME>_PASSWORD` with the controller name uppercased and hyphens replaced by underscores. Check:

```bash
# If controller name is "prod-avi", the variable must be:
export PROD_AVI_PASSWORD=yourpassword

# Or set it in ~/.vmware-avi/.env:
echo 'PROD_AVI_PASSWORD=yourpassword' >> ~/.vmware-avi/.env
```

### "Controller unreachable" in doctor

1. Verify the `host` and `port` in config.yaml are correct
2. Test network connectivity: `curl -k https://avi-controller.example.com/api/cluster`
3. For self-signed certs, set `verify_ssl: false` in config.yaml
4. Check if a firewall or VPN is blocking port 443

### MCP server not starting

1. Verify the entry point exists: `which vmware-avi-mcp`
2. If using `uvx`, ensure the package is installed: `uvx --from vmware-avi vmware-avi-mcp --help`
3. Check that `~/.vmware-avi/config.yaml` exists (MCP server loads config on startup)
4. Never use `python -m mcp_server` -- always use `uvx --from` (isolated environment requires entry point)

### kubectl / helm not found

```bash
# macOS
brew install kubectl helm
```

For Linux, see https://kubernetes.io/docs/tasks/tools/ and https://helm.sh/docs/intro/install/.

### AKO namespace not found

Update `ako.namespace` in config.yaml to match your deployment (default: `avi-system`).

### Permission denied on .env file

```bash
chmod 600 ~/.vmware-avi/.env
```
