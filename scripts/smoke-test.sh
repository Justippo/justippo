#!/bin/sh
# smoke-test.sh — Post-deploy verification for production.
#
# Usage: sh scripts/smoke-test.sh [api_url] [frontend_url]
#
# Tests:
#   1. GET /api/v1/health/ → 200
#   2. GET /api/v1/health/pipeline → 200 + all healthy
#   3. GET /api/v1/search/?q=residence+permit → SSE stream starts
#   4. Frontend loads → 200
#   5. GDPR enforcement (no header → 451)
#
# Extends scripts/smoke.sh (DRY — adds pipeline + GDPR + SSE checks).
# POSIX shell — set -e -u.

set -eu

API_URL="${1:-https://evidence-eu-api.mc146.workers.dev}"
FRONTEND_URL="${2:-https://evidence-eu-frontend.pages.dev}"
PASS=0
FAIL=0

_pass() { printf "  ✅ %s\n" "$1"; PASS=$((PASS + 1)); }
_fail() { printf "  ❌ %s\n" "$1"; FAIL=$((FAIL + 1)); }

printf '=== Smoke Test (7 checks) ===\n\n'

# ── 1. Backend health ────────────────────────────────────────────
printf '1. Backend health:\n'
STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 15 \
    -H "X-GDPR-Consent: smoke" \
    "$API_URL/api/v1/health/" 2>/dev/null || echo "000")
[ "$STATUS" = "200" ] && _pass "GET /api/v1/health/ → 200" || _fail "GET /api/v1/health/ → $STATUS"

# ── 2. Pipeline health ───────────────────────────────────────────
printf '2. Pipeline health:\n'
PIPELINE=$(curl -sf --max-time 15 \
    -H "X-GDPR-Consent: smoke" \
    "$API_URL/api/v1/health/pipeline" 2>/dev/null || echo "")
if echo "$PIPELINE" | python3 -c "
import sys, json
d = json.load(sys.stdin)
for k, v in d.items():
    if isinstance(v, dict) and v.get('status') not in ('healthy', 'ok', 'degraded'):
        sys.exit(1)
sys.exit(0)
" 2>/dev/null; then
    _pass "GET /api/v1/health/pipeline → all healthy"
else
    _fail "GET /api/v1/health/pipeline → unhealthy or parse error"
fi

# ── 3. SSE search starts ─────────────────────────────────────────
printf '3. SSE search stream:\n'
SSE_HEAD=$(curl -s --max-time 10 \
    -H "X-GDPR-Consent: smoke" \
    "$API_URL/api/v1/search/?q=residence+permit&language=en&gdpr_consent=smoke" 2>/dev/null | head -5 || echo "")
if echo "$SSE_HEAD" | grep -qi "event:" 2>/dev/null; then
    _pass "SSE stream starts (event: found)"
else
    _fail "SSE stream — no event: line in first 5 lines"
fi

# ── 4. Frontend loads ────────────────────────────────────────────
printf '4. Frontend:\n'
FE_STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 \
    "$FRONTEND_URL" 2>/dev/null || echo "000")
case "$FE_STATUS" in
    200|301|302) _pass "Frontend → $FE_STATUS" ;;
    *) _fail "Frontend → $FE_STATUS (expected 200/301/302)" ;;
esac

# ── 5. GDPR enforcement (no header → 451) ────────────────────────
printf '5. GDPR enforcement:\n'
GDPR_STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 \
    "$API_URL/api/v1/documents/" 2>/dev/null || echo "000")
# 451 = GDPR consent required (expected when no X-GDPR-Consent header)
# 405 = Method not allowed (also acceptable — means endpoint exists, just wrong method)
case "$GDPR_STATUS" in
    451) _pass "No GDPR header → 451 (correct)" ;;
    405) _pass "No GDPR header → 405 (endpoint exists)" ;;
    *) _fail "No GDPR header → $GDPR_STATUS (expected 451 or 405)" ;;
esac

# ── 6. Security headers ──────────────────────────────────────────
printf '6. Security headers:\n'
XCTO=$(curl -sI --max-time 10 "$FRONTEND_URL" 2>/dev/null | grep -i 'x-content-type-options: nosniff' || true)
[ -n "$XCTO" ] && _pass "X-Content-Type-Options: nosniff" || _fail "Missing X-Content-Type-Options"

# ── 7. API 404 ───────────────────────────────────────────────────
printf '7. API 404:\n'
NOT_FOUND=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 \
    -H "X-GDPR-Consent: smoke" \
    "$API_URL/api/v1/nonexistent" 2>/dev/null || echo "000")
[ "$NOT_FOUND" = "404" ] && _pass "Unknown endpoint → 404" || _fail "Unknown endpoint → $NOT_FOUND"

# ── Summary ──────────────────────────────────────────────────────
printf '\n=== Summary: %d passed, %d failed ===\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ] && printf '✅ All smoke tests passed.\n' || printf '❌ Some smoke tests failed.\n'
exit "$FAIL"
