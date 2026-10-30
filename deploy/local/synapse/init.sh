#!/usr/bin/env bash
set -euo pipefail

SYNAPSE_CONTAINER="justippo-synapse"
# Relative to this script: the hard-coded checkout path broke when the folder was renamed,
# so homeserver.yaml was never copied and Synapse crash-looped.
BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="$BASE_DIR/data"
SERVER_NAME="evidenceeu.eu.mihai.codes"
DEMO_USER="demo_bot"
DEMO_PASS="evidence-eu-demo-2026"

# Ensure data directory exists (bind mount target)
mkdir -p "$DATA_DIR"

# Copy config files into data dir if not present (runtime bind mount at /data)
if [ ! -f "$DATA_DIR/homeserver.yaml" ]; then
  cp "$BASE_DIR/homeserver.yaml" "$DATA_DIR/homeserver.yaml"
fi

if [ ! -f "$DATA_DIR/evidenceeu.eu.mihai.codes.signing.key" ]; then
  if [ -f "$BASE_DIR/signing.key" ]; then
    cp "$BASE_DIR/signing.key" "$DATA_DIR/evidenceeu.eu.mihai.codes.signing.key"
  else
    echo "Generating signing key..."
    docker run --rm --entrypoint python matrixdotorg/synapse:latest -c "
from signedjson.key import generate_signing_key, NACL_ED25519
import os
from unpaddedbase64 import encode_base64
version = 'a_' + encode_base64(os.urandom(6)).rstrip('=')
key = generate_signing_key(version)
print(f'{NACL_ED25519}:{key.version}:{encode_base64(key.encode()).rstrip(\"=\")}')
" > "$DATA_DIR/evidenceeu.eu.mihai.codes.signing.key"
    # Convert colon-separated to space-separated (Synapse v1.120+)
    KEY_CONTENT=$(cat "$DATA_DIR/evidenceeu.eu.mihai.codes.signing.key")
    ALG=$(echo "$KEY_CONTENT" | cut -d: -f1)
    KEY_ID=$(echo "$KEY_CONTENT" | cut -d: -f2)
    KEY_B64=$(echo "$KEY_CONTENT" | cut -d: -f3-)
    echo "$ALG $KEY_ID $KEY_B64" > "$DATA_DIR/evidenceeu.eu.mihai.codes.signing.key"
  fi
fi

if ! docker ps --format '{{.Names}}' | grep -q "^$SYNAPSE_CONTAINER$"; then
  echo "Starting Synapse..."
  docker compose -f deploy/local/docker-compose.yml up -d synapse
fi

echo "Waiting for Synapse to be ready..."
for i in $(seq 1 30); do
  if curl -sf http://localhost:8008/_matrix/client/versions > /dev/null 2>&1; then
    echo "Synapse is ready!"
    break
  fi
  if [ "$i" -eq 30 ]; then
    echo "Timed out waiting for Synapse"
    exit 1
  fi
  sleep 2
done

echo "Registering demo user (idempotent)..."
docker exec "$SYNAPSE_CONTAINER" register_new_matrix_user \
  -c /data/homeserver.yaml \
  -u "$DEMO_USER" -p "$DEMO_PASS" --admin \
  http://localhost:8008 2>/dev/null || true

echo "Logging in to get access token..."
TOKEN=$(curl -s -X POST http://localhost:8008/_matrix/client/v3/login \
  -H "Content-Type: application/json" \
  -d "{\"type\":\"m.login.password\",\"user\":\"$DEMO_USER\",\"password\":\"$DEMO_PASS\"}" | \
  python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))")

if [ -n "$TOKEN" ]; then
  echo ""
  echo "=== Demo user ready ==="
  echo "MATRIX_ACCESS_TOKEN=$TOKEN"
  echo "MATRIX_HOMESERVER_URL=https://synapse.evidenceeu.eu.mihai.codes"
  echo "========================="
else
  echo "Failed to get access token"
  exit 1
fi
