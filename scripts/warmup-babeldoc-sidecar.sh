#!/bin/sh
# warmup-babeldoc-sidecar.sh — Post-deploy warm-up (issue #239)
# DRY: delegates validation to validate-babeldoc-sidecar.sh
set -eu
SIDECAR_URL="${1:-http://localhost:8750}"
SIDECAR_URL="${SIDECAR_URL%/}"
AUTH_TOKEN="${AUTH_TOKEN:-}"
READY_TIMEOUT_S="${READY_TIMEOUT_S:-60}"
READY_POLL_INTERVAL_S="${READY_POLL_INTERVAL_S:-5}"
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
VALIDATE_SCRIPT="$SCRIPT_DIR/validate-babeldoc-sidecar.sh"
log() { printf '%s\n' "$1"; }
log "BabelDOC Warm-Up: $SIDECAR_URL"
log "[1/3] Waiting for /ready..."
elapsed=0; ready=false
while [ "$elapsed" -lt "$READY_TIMEOUT_S" ]; do
  if [ -n "$AUTH_TOKEN" ]; then
    http_code=$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $AUTH_TOKEN" "$SIDECAR_URL/ready" 2>/dev/null || echo "000")
  else
    http_code=$(curl -s -o /dev/null -w '%{http_code}' "$SIDECAR_URL/ready" 2>/dev/null || echo "000")
  fi
  if [ "$http_code" = "200" ]; then ready=true; break; fi
  log "  /ready=$http_code retrying (${elapsed}s/${READY_TIMEOUT_S}s)"
  sleep "$READY_POLL_INTERVAL_S"
  elapsed=$((elapsed + READY_POLL_INTERVAL_S))
done
if [ "$ready" != "true" ]; then log "FAILED: /ready timeout"; exit 1; fi
log "  /ready OK after ${elapsed}s"
log "[2/3] Warm-up translation..."
PDF_B64='JVBERi0xLjQKJeLjz9MKMSAwIG9iago8PC9UeXBlL0NhdGFsb2cvUGFnZXMgMiAwIFI+PgplbmRvYmoKMiAwIG9iago8PC9UeXBlL1BhZ2VzL0tpZHNbMyAwIFJdL0NvdW50IDE+PgplbmRvYmoKMyAwIG9iago8PC9UeXBlL1BhZ2UvUGFyZW50IDIgMCBSL01lZGlhQm94WzAgMCA2MTIgNzkyXT4+CmVuZG9iagp4cmVmCjAgNAowMDAwMDAwMDAwIDY1NTM1IGYgCjAwMDAwMDAwMDkgMDAwMDAgbiAKMDAwMDAwMDA1OCAwMDAwMCBuIAowMDAwMDAwMTE1IDAwMDAwIG4gCnRyYWlsZXIKPDwvU2l6ZSA0L1Jvb3QgMSAwIFI+PgpzdGFydHhyZWYKMTkwCiUlRU9GCg=='
PAYLOAD="{"source_lang":"en","target_lang":"de","document_b64":"$PDF_B64","preserve_layout":true,"options":{}}"
if [ -n "$AUTH_TOKEN" ]; then
  t_http=$(curl -s -o /dev/null -w '%{http_code}' -X POST -H "Authorization: Bearer $AUTH_TOKEN" -H "Content-Type: application/json" -d "$PAYLOAD" "$SIDECAR_URL/translate" 2>/dev/null || echo "000")
else
  t_http=$(curl -s -o /dev/null -w '%{http_code}' -X POST -H "Content-Type: application/json" -d "$PAYLOAD" "$SIDECAR_URL/translate" 2>/dev/null || echo "000")
fi
case "$t_http" in 200|400|422|503) log "  translate=$t_http OK";; *) log "FAILED: translate=$t_http"; exit 1;; esac
log "[3/3] Full validation..."
if [ ! -f "$VALIDATE_SCRIPT" ]; then log "FAILED: validator not found"; exit 1; fi
if [ -n "$AUTH_TOKEN" ]; then
  AUTH_TOKEN="$AUTH_TOKEN" "$VALIDATE_SCRIPT" "$SIDECAR_URL" --auth-token "$AUTH_TOKEN"
else
  "$VALIDATE_SCRIPT" "$SIDECAR_URL"
fi
log "Sidecar is warm and validated."
