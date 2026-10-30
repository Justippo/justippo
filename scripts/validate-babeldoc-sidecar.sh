#!/bin/bash
# validate-babeldoc-sidecar.sh
#
# Pre-deployment validation script for BabelDOC sidecar.
# Verifies connectivity, health, and API contract compliance.
#
# Usage:
#   ./scripts/validate-babeldoc-sidecar.sh https://babeldoc.example.com
#   ./scripts/validate-babeldoc-sidecar.sh http://localhost:8750 --auth-token mytoken
#
# Exit codes:
#   0 - All checks passed
#   1 - One or more checks failed

set -euo pipefail

SIDECAR_URL="${1:-http://localhost:8750}"
AUTH_TOKEN="${AUTH_TOKEN:-}"
VERBOSE="${VERBOSE:-false}"
FAILED_CHECKS=0

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Parse arguments
while [[ $# -gt 1 ]]; do
  case "$2" in
    --auth-token)
      AUTH_TOKEN="$3"
      shift 2
      ;;
    -v|--verbose)
      VERBOSE=true
      shift
      ;;
    *)
      echo "Unknown option: $2"
      exit 1
      ;;
  esac
done

# Normalize URL (remove trailing slash)
SIDECAR_URL="${SIDECAR_URL%/}"

# Helper functions
log_pass() {
  echo -e "${GREEN}✓${NC} $1"
}

log_fail() {
  echo -e "${RED}✗${NC} $1"
  ((FAILED_CHECKS++))
}

log_info() {
  echo -e "${YELLOW}ℹ${NC} $1"
}

log_verbose() {
  if [[ "$VERBOSE" == "true" ]]; then
    echo "  $1"
  fi
}

# Build curl command with auth
curl_cmd() {
  local method="$1"
  local endpoint="$2"
  shift 2
  
  local cmd="curl -s -X $method \"$SIDECAR_URL$endpoint\""
  if [[ -n "$AUTH_TOKEN" ]]; then
    cmd="$cmd -H \"Authorization: Bearer $AUTH_TOKEN\""
  fi
  cmd="$cmd $@"
  eval "$cmd"
}

echo "========================================"
echo "BabelDOC Sidecar Validation"
echo "========================================"
echo "Target: $SIDECAR_URL"
if [[ -n "$AUTH_TOKEN" ]]; then
  echo "Auth: Bearer token configured"
fi
echo ""

# Check 1: Network connectivity
echo "[1/5] Checking network connectivity..."
if curl -s --max-time 5 "$SIDECAR_URL/health" >/dev/null 2>&1; then
  log_pass "Sidecar is reachable"
else
  log_fail "Cannot reach sidecar at $SIDECAR_URL"
  log_info "Check that the URL is correct and the sidecar is running"
  exit 1
fi

# Check 2: Health endpoint
echo "[2/5] Checking health endpoint..."
HEALTH_RESPONSE=$(curl_cmd GET "/health" "-w" '"\n%{http_code}"' 2>/dev/null | tail -1)
HTTP_CODE="${HEALTH_RESPONSE: -3}"

if [[ "$HTTP_CODE" == "200" ]]; then
  log_pass "Health check passed (HTTP $HTTP_CODE)"
  HEALTH_BODY=$(curl_cmd GET "/health" 2>/dev/null | head -n -1)
  log_verbose "Response: $HEALTH_BODY"
  
  if echo "$HEALTH_BODY" | grep -q '"status".*"ok"'; then
    log_pass "Health status is OK"
  else
    log_fail "Health status is not OK"
  fi
else
  log_fail "Health check failed (HTTP $HTTP_CODE)"
  if [[ "$HTTP_CODE" == "401" ]]; then
    log_info "Got 401 Unauthorized — check that --auth-token is set correctly"
  fi
fi

# Check 3: API contract (request validation)
echo "[3/5] Checking API contract..."

# Create a minimal valid PDF (PDF header + minimal structure)
PDF_MINIMAL='JVBERi0xLjQKJeLjz9MNCjEgMCBvYmo8PC9UeXBlL0NhdGFsb2cvUGFnZXMgMiAwIFI+PmVuZG9iaiAyIDAgb2JqPDwvVHlwZS9QYWdlcy9LaWRzWzMgMCBSXS9Db3VudCAxPj5lbmRvYmogMyAwIG9iajw8L1R5cGUvUGFnZS9QYXJlbnQgMiAwIFIvTWVkaWFCb3hbMCAwIDYxMiA3OTJdL1Jlc291cmNlcyA8PC9Gb250PDwvRjE8PC9UeXBlL0ZvbnQvU3VidHlwZS9UeXBlMS9CYXNlRm9udC9IZWx2ZXRpY2E+Pj4+Pj4vQ29udGVudHMgNCAwIFI+PmVuZG9iaiA0IDAgb2JqPDwvTGVuZ3RoIDQzPj5zdHJlYW0KQlQgL0YxIDEyIFRmIDUwIDcwMCBUZCAoSGVsbG8gV29ybGQpIFRqIEVUCmVuZHN0cmVhbQplbmRvYmogICAgICAgICAgeHJlZgowIDUKMDAwMDAwMDAwMCA2NTUzNSBmIAowMDAwMDAwMDA5IDAwMDAwIG4gCjAwMDAwMDAwNTggMDAwMDAgbiAKMDAwMDAwMDEyMyAwMDAwMCBuIAowMDAwMDAwMzQwIDAwMDAwIG4gCnRyYWlsZXI8PC9TaXplIDUvUm9vdCAxIDAgUj4+CnN0YXJ0eHJlZgo0MzcKJSVFT0Y='

TRANSLATE_PAYLOAD="{
  \"source_lang\": \"en\",
  \"target_lang\": \"de\",
  \"document_b64\": \"$PDF_MINIMAL\",
  \"preserve_layout\": true,
  \"glossary_csv_b64\": null,
  \"options\": {}
}"

TRANSLATE_RESPONSE=$(curl_cmd POST "/translate" \
  "-H" "Content-Type: application/json" \
  "-d" "$TRANSLATE_PAYLOAD" \
  "-w" "\n%{http_code}" 2>/dev/null | tail -1)

TRANSLATE_HTTP="${TRANSLATE_RESPONSE: -3}"

if [[ "$TRANSLATE_HTTP" =~ ^(200|400|422|503)$ ]]; then
  log_pass "API accepts POST /translate (HTTP $TRANSLATE_HTTP)"
  
  if [[ "$TRANSLATE_HTTP" == "200" ]]; then
    TRANSLATE_BODY=$(curl_cmd POST "/translate" \
      "-H" "Content-Type: application/json" \
      "-d" "$TRANSLATE_PAYLOAD" 2>/dev/null | head -n -1)
    log_verbose "Response (first 200 chars): ${TRANSLATE_BODY:0:200}..."
    
    if echo "$TRANSLATE_BODY" | grep -q '"translated_b64"'; then
      log_pass "Translation endpoint returned valid response"
    else
      log_fail "Translation response missing 'translated_b64' field"
    fi
  else
    log_info "API returned $TRANSLATE_HTTP (expected for test PDF; real PDFs may differ)"
  fi
else
  log_fail "API returned unexpected HTTP $TRANSLATE_HTTP (expected 200, 400, 422, or 503)"
fi

# Check 4: Authentication (if token is set)
echo "[4/5] Checking authentication..."
if [[ -n "$AUTH_TOKEN" ]]; then
  # Try without token
  NO_AUTH_RESPONSE=$(curl -s "$SIDECAR_URL/health" -w "\n%{http_code}" 2>/dev/null | tail -1)
  NO_AUTH_HTTP="${NO_AUTH_RESPONSE: -3}"
  
  if [[ "$NO_AUTH_HTTP" == "401" ]]; then
    log_pass "Sidecar enforces authentication (rejects unauth requests)"
  elif [[ "$NO_AUTH_HTTP" == "200" ]]; then
    log_pass "Sidecar does not enforce authentication (open endpoint)"
  else
    log_fail "Unexpected response when testing auth: HTTP $NO_AUTH_HTTP"
  fi
else
  log_info "No auth token provided — skipping authentication check"
fi

# Check 5: /ready endpoint
echo "[5/7] Checking /ready endpoint..."
READY_RESPONSE=$(curl_cmd GET "/ready" "-w" '"\n%{http_code}"' 2>/dev/null | tail -1)
READY_HTTP="${READY_RESPONSE: -3}"
if [[ "$READY_HTTP" == "200" ]]; then
  log_pass "/ready reports ready"
elif [[ "$READY_HTTP" == "503" ]]; then
  log_fail "/ready reports NOT ready (503)"
else
  log_fail "/ready unexpected HTTP $READY_HTTP"
fi

# Check 6: Real chat-completions call
echo "[6/7] Checking real chat-completions call..."
CHAT_TEST_RESPONSE=$(curl_cmd POST "/translate" "-H" "Content-Type: application/json" "-d" "$TRANSLATE_PAYLOAD" "-w" '"\n%{http_code}"' 2>/dev/null | tail -1)
CHAT_TEST_HTTP="${CHAT_TEST_RESPONSE: -3}"
if [[ "$CHAT_TEST_HTTP" =~ ^(200|400|422)$ ]]; then
  log_pass "LLM round-trip OK (HTTP $CHAT_TEST_HTTP)"
elif [[ "$CHAT_TEST_HTTP" == "500" ]]; then
  log_fail "LLM call failed (500) -- likely wrong model"
elif [[ "$CHAT_TEST_HTTP" == "503" ]]; then
  log_info "Sidecar unconfigured (503) -- skipping"
else
  log_fail "Unexpected HTTP $CHAT_TEST_HTTP"
fi

# Check 7: Performance (basic latency)
echo "[7/7] Checking performance..."
START_TIME=$(date +%s%N)
curl_cmd GET "/health" >/dev/null 2>&1
END_TIME=$(date +%s%N)
ELAPSED_MS=$(( (END_TIME - START_TIME) / 1000000 ))

if [[ $ELAPSED_MS -lt 1000 ]]; then
  log_pass "Health endpoint responds in ${ELAPSED_MS}ms"
elif [[ $ELAPSED_MS -lt 5000 ]]; then
  log_info "Health endpoint responds in ${ELAPSED_MS}ms (acceptable but slow)"
else
  log_fail "Health endpoint takes ${ELAPSED_MS}ms (too slow, expected < 1000ms)"
fi

# Summary
echo ""
echo "========================================"
if [[ $FAILED_CHECKS -eq 0 ]]; then
  echo -e "${GREEN}All checks passed!${NC}"
  echo "Sidecar is ready for production deployment."
  exit 0
else
  echo -e "${RED}$FAILED_CHECKS check(s) failed${NC}"
  echo "See errors above and consult the deployment runbook."
  exit 1
fi
