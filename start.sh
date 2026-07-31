#!/bin/bash
set -e

mkdir -p /data/.hermes/sessions /data/.hermes/skills /data/.hermes/workspace \
  /data/.hermes/platforms/pairing

# Install bundled skills into HERMES_HOME. Copied on every boot so updates
# reach an existing volume; user-created skills alongside them are untouched.
if [ -d /app/skills ]; then
  cp -R /app/skills/. /data/.hermes/skills/ 2>/dev/null || true
fi

# Register Forge as an MCP server. Tools are selected far more reliably than
# skills: a skill is prose competing with 66 others for the model's attention,
# an MCP tool is a named function with a schema. Idempotent — re-registered on
# every boot so an image update reaches an existing volume.
if [ -n "$FORGE_API_URL" ] && [ -n "$FORGE_TOKEN" ]; then
  hermes mcp remove forge >/dev/null 2>&1 || true
  hermes mcp add --transport stdio forge -- python3 /app/forge_mcp.py >/dev/null 2>&1 \
    && echo "[forge] MCP server registered" \
    || echo "[forge] MCP registration failed — check 'hermes mcp list'"
else
  echo "[forge] FORGE_API_URL / FORGE_TOKEN not set; MCP server not registered"
fi

exec python /app/server.py
