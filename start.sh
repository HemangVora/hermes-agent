#!/bin/bash
set -e

mkdir -p /data/.hermes/sessions /data/.hermes/skills /data/.hermes/workspace \
  /data/.hermes/platforms/pairing

# Install bundled skills into HERMES_HOME. Copied on every boot so updates
# reach an existing volume; user-created skills alongside them are untouched.
if [ -d /app/skills ]; then
  cp -R /app/skills/. /data/.hermes/skills/ 2>/dev/null || true
fi

exec python /app/server.py
