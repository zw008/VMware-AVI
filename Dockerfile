FROM python:3.12-slim

WORKDIR /app

# Install uv for fast dependency installation
RUN pip install --no-cache-dir uv

# Copy project files
COPY pyproject.toml README.md ./
COPY vmware_avi/ vmware_avi/
COPY examples/ examples/

# Install dependencies
RUN uv pip install --system --no-cache .

# Config directory (mount at runtime)
RUN mkdir -p /root/.vmware-avi

# MCP server uses stdio transport — no port needed
CMD ["python", "-m", "vmware_avi.mcp_server"]
