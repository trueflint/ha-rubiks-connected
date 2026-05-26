#!/bin/bash
# Deploy the integration to Home Assistant and restart HA Core.
#
# Usage:
#   ./deploy.sh
#
# Requires:
#   - An HTTP server is started automatically on port 8000
#   - SSH access to ha.local (interactive session as root)
#   - HA CLI available on the Pi as 'ha'

set -e

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
HA_HOST="ha.local"
HA_IP="${HA_IP:-192.168.1.185}"   # override with: HA_IP=x.x.x.x ./deploy.sh
PORT=8000
TARBALL="/tmp/rubiks_connected.tar.gz"

echo "==> Packing integration ..."
tar czf "$TARBALL" -C "$REPO_DIR/custom_components" rubiks_connected

echo "==> Starting HTTP server on port $PORT ..."
python3 -m http.server "$PORT" --directory /tmp &
HTTP_PID=$!
trap "kill $HTTP_PID 2>/dev/null" EXIT

sleep 1

echo "==> Deploying to $HA_HOST ..."
echo "    (You may be prompted for your SSH password)"
ssh "$HA_HOST" "cd /config/custom_components && curl -s http://${HA_IP}:${PORT}/rubiks_connected.tar.gz | tar -xzf -"

echo ""
echo "==> Files deployed. Now restart HA Core from the HA terminal:"
echo "    ha core restart"
