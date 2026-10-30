#!/bin/bash
# Post-deploy smoke test — 6 checks run in parallel.
# Parallel execution keeps total time bounded by the slowest single check.
# Usage: scripts/smoke.sh <api_url> <frontend_url>

set -uo pipefail  # -e intentionally omitted — individual check failures are handled below

API_URL="${1:?Usage: $0 <api_url> <frontend_url>}"
FRONTEND_URL="${2:?Usage: $0 <api_url> <frontend_url>}"

# ── Retry helper (shared by all checks — DRY) ────────────────────────────────
# Usage: _with_retry <name> <max_attempts> <delay_s> <cmd...>
# Runs <cmd...> up to max_attempts times with delay_s between retries.
# Cmd must print its result to stdout on success; last stdout is captured.
# Returns 0 on success, 1 after all attempts exhausted.
_with_retry() {
  local name="$1" max="$2" delay="$3"; shift 3
  local attempts=0 result=""
  while [ $attempts -lt $max ]; do
    result="$("$@" 2>/dev/null)" && { echo "$result"; return 0; }
    attempts=$((attempts + 1))
    [ $attempts -lt $max ] && sleep "$delay"
  done
  echo "$result"
  return 1
}

echo "=== Smoke Test (6 checks in parallel) ==="

# ── Phase 1: Warm proxy isolate (no backend dependency) ────────────────────────
# Hit /__warm 5 times with 1s delay to ensure the proxy Worker's edge isolate
# is hot before we start sending concurrent requests. This prevents TLS
# connection resets (curl 000) from Cloudflare edge routing to a cold isolate.
echo "  Warming proxy isolate..."
warmed=false
for _ in 1 2 3 4 5; do
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "$API_URL/__warm" 2>/dev/null || echo "000")
  if [ "$STATUS" = "200" ]; then
    warmed=true
  fi
  sleep 1
done
if [ "$warmed" != "true" ]; then
  echo "  [✗] Proxy /__warm failed — cannot reach $API_URL"
  exit 1
fi
echo "  ✓ Proxy isolate warmed"

# ── Phase 2: Warm backend (health endpoint activates FastAPI + D1) ────────────
# After the proxy is warm, hit the health endpoint 3 times to ensure the
# backend Worker (FastAPI cold-start ~2-3s) is ready before parallel checks.
echo "  Warming backend..."
for _ in 1 2 3; do
  HEALTH=$(curl -sf --max-time 15 -H "X-GDPR-Consent: smoke-test" "$API_URL/api/v1/health/" 2>/dev/null || true)
  if echo "$HEALTH" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d.get('status')=='ok'" 2>/dev/null; then
    echo "  ✓ Backend warmed"
    break
  fi
  # Sleep 2 between retries even after last iteration (2s waste is negligible)
  sleep 2
done

# ── Checks (each runs as a background subshell; exit 1 = failure) ────────────

_check_backend_health() {
  local out
  out="$(_with_retry "health" 5 3 \
    sh -c 'curl -sf --max-time 15 -H "X-GDPR-Consent: smoke-test" "$1/api/v1/health/" 2>/dev/null' _ "$API_URL")" || {
    echo "  [✗] Backend /api/v1/health/ — empty response after 5 attempts (cold-start timeout)"
    exit 1
  }
  if echo "$out" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d.get('status')=='ok'" 2>/dev/null; then
    echo "  [✓] Backend /api/v1/health/ returns ok"
  else
    echo "  [✗] Backend /api/v1/health/ — unexpected payload: $(echo "$out" | head -c 200)"
    exit 1
  fi
}

_check_frontend() {
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "$FRONTEND_URL" 2>/dev/null || echo "000")
  if [[ "$STATUS" =~ ^(200|301|302)$ ]]; then
    echo "  [✓] Frontend responds $STATUS"
  else
    echo "  [✗] Frontend status: $STATUS (expected 200/301/302)"
    exit 1
  fi
}

_check_api_404() {
  # Wrapper: always prints the HTTP code (or "000" on connection failure),
  # exits 0 only on 404. This lets _with_retry retry on anything but 404.
  _fetch_404_code() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 \
      -H "X-GDPR-Consent: smoke-test" "$1/api/v1/nonexistent" 2>/dev/null)
    echo "${code:-000}"
    [ "$code" = "404" ]
  }
  local out
  out="$(_with_retry "404" 5 3 _fetch_404_code "$API_URL")"
  case "$out" in
    404) echo "  [✓] API 404 returns 404"; return 0;;
    000) echo "  [✗] API 404 expected 404, got 000 (connection reset after 5 attempts)"; exit 1;;
    "")  echo "  [✗] API 404 expected 404, got empty (connection lost)"; exit 1;;
    *)   echo "  [✗] API 404 expected 404, got $out"; exit 1;;
  esac
}

_check_readiness() {
  local out
  out="$(_with_retry "readiness" 5 3 \
    sh -c 'curl -sf --max-time 15 -H "X-GDPR-Consent: smoke-test" "$1/api/v1/health/ready" 2>/dev/null' _ "$API_URL")" || {
    echo "  [✗] Readiness probe — empty response after 5 attempts (cold-start timeout)"
    exit 1
  }
  if echo "$out" | python3 -c "import sys,json; d=json.load(sys.stdin); assert 'dependencies' in d" 2>/dev/null; then
    echo "  [✓] Readiness probe returns dependencies"
  else
    echo "  [✗] Readiness probe — unexpected payload: $(echo "$out" | head -c 200)"
    exit 1
  fi
}

_check_security_headers() {
  XCTO=$(curl -sI --max-time 10 "$FRONTEND_URL" 2>/dev/null | grep -i 'x-content-type-options: nosniff' || true)
  if [ -n "$XCTO" ]; then
    echo "  [✓] Frontend sets X-Content-Type-Options: nosniff"
  else
    echo "  [✗] Frontend missing X-Content-Type-Options: nosniff"
    exit 1
  fi
}

_check_chat_stream() {
  # Validate the production chat transport contract without retaining or
  # printing response content. A complete stream must return 200, advertise
  # SSE, and finish with the terminal `done` event.
  _probe_chat_stream() {
    local body_file headers_file status content_type
    body_file=$(mktemp "${TMPDIR:-/tmp}/evidence-eu-chat-body.XXXXXX") || return 1
    headers_file=$(mktemp "${TMPDIR:-/tmp}/evidence-eu-chat-headers.XXXXXX") || {
      rm -f "$body_file"
      return 1
    }

    status=$(curl -sS --max-time 100 \
      -D "$headers_file" \
      -o "$body_file" \
      -w "%{http_code}" \
      -X POST \
      -H "Accept: text/event-stream" \
      -H "Content-Type: application/json" \
      -H "X-GDPR-Consent: smoke-test" \
      --data '{"message":"Welche EU-Regeln gelten für einen Umzug nach Spanien?","history":[],"language":"de"}' \
      "$1/api/v1/chat/" 2>/dev/null) || {
      rm -f "$body_file" "$headers_file"
      return 1
    }

    content_type=$(grep -i '^content-type:' "$headers_file" | tail -1 | tr -d '\r')
    if [ "$status" = "200" ] && \
       echo "$content_type" | grep -qi 'text/event-stream' && \
       grep -q '^event: done\r\{0,1\}$' "$body_file"; then
      rm -f "$body_file" "$headers_file"
      echo "complete"
      return 0
    fi

    rm -f "$body_file" "$headers_file"
    return 1
  }

  if _with_retry "chat" 3 3 _probe_chat_stream "$API_URL" >/dev/null; then
    echo "  [✓] Chat stream returns 200 SSE with terminal done event"
  else
    echo "  [✗] Chat stream did not complete after 3 attempts"
    exit 1
  fi
}

# ── Run all checks concurrently (staggered 200ms) ────────────────────────────
# Stagger prevents TLS thundering herd: simultaneous connections to a freshly
# deployed Worker can trigger Cloudflare edge connection resets (curl 000).
# 200ms between each launch spreads the TLS handshakes across edge servers
# without adding meaningful latency (~800ms total stagger).
_check_backend_health   & P1=$!; sleep 0.2
_check_frontend         & P2=$!; sleep 0.2
_check_api_404          & P3=$!; sleep 0.2
_check_readiness        & P4=$!; sleep 0.2
_check_security_headers & P5=$!; sleep 0.2
_check_chat_stream      & P6=$!

# Collect results — wait for each PID so we get correct exit codes
FAIL=0
wait $P1 || FAIL=1
wait $P2 || FAIL=1
wait $P3 || FAIL=1
wait $P4 || FAIL=1
wait $P5 || FAIL=1
wait $P6 || FAIL=1

echo ""
if [ $FAIL -ne 0 ]; then
  echo "=== Some smoke checks failed — see [✗] lines above ==="
  exit 1
fi
echo "=== All checks passed ==="
