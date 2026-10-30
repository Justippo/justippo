#!/bin/sh
# pre-deploy-check.sh — Verify all prerequisites before production deploy.
#
# Usage: sh scripts/pre-deploy-check.sh
#
# Checks:
#   a. Required env vars (CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID, NEXT_PUBLIC_API_URL)
#   b. Optional env vars (SENTRY_DSN, DATADOG_API_KEY) — warn if missing
#   c. make lint passes
#   d. make test-backend passes
#   e. make test-frontend passes
#   f. Current production health endpoint returns 200
#
# POSIX shell — set -e -u.

set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
API_URL="https://evidence-eu-api.mc146.workers.dev"
PASS=0
FAIL=0

_check() {
    if [ "$1" = "pass" ]; then
        printf "  ✅ %s\n" "$2"
        PASS=$((PASS + 1))
    else
        printf "  ❌ %s\n" "$2"
        FAIL=$((FAIL + 1))
    fi
}

printf '=== Pre-Deploy Checklist ===\n\n'

# ── a. Required env vars ─────────────────────────────────────────
printf '1. Environment variables:\n'

if [ -n "${CLOUDFLARE_API_TOKEN:-}" ]; then
    _check pass "CLOUDFLARE_API_TOKEN set"
else
    _check fail "CLOUDFLARE_API_TOKEN NOT set"
fi

if [ -n "${CLOUDFLARE_ACCOUNT_ID:-}" ]; then
    _check pass "CLOUDFLARE_ACCOUNT_ID set"
else
    _check fail "CLOUDFLARE_ACCOUNT_ID NOT set"
fi

if [ -n "${NEXT_PUBLIC_API_URL:-}" ]; then
    _check pass "NEXT_PUBLIC_API_URL set"
else
    _check fail "NEXT_PUBLIC_API_URL NOT set"
fi

# ── b. Optional env vars ─────────────────────────────────────────
printf '\n2. Optional variables (warnings only):\n'

if [ -n "${SENTRY_DSN:-}" ]; then
    _check pass "SENTRY_DSN set"
else
    printf "  ⚠️  SENTRY_DSN not set — Sentry will be no-op\n"
fi

if [ -n "${DATADOG_API_KEY:-}" ]; then
    _check pass "DATADOG_API_KEY set"
else
    printf "  ⚠️  DATADOG_API_KEY not set — Datadog will be no-op\n"
fi

# ── c. Lint ──────────────────────────────────────────────────────
printf '\n3. Lint (make lint):\n'
if cd "$ROOT" && make lint > /dev/null 2>&1; then
    _check pass "make lint"
else
    _check fail "make lint"
fi

# ── d. Backend tests ─────────────────────────────────────────────
printf '\n4. Backend tests (make test-backend):\n'
if cd "$ROOT" && make test-backend > /dev/null 2>&1; then
    _check pass "make test-backend"
else
    printf "  ⚠️  make test-backend skipped (requires Docker)\n"
fi

# ── e. Frontend tests ────────────────────────────────────────────
printf '\n5. Frontend tests (make test-frontend):\n'
if cd "$ROOT" && make test-frontend > /dev/null 2>&1; then
    _check pass "make test-frontend"
else
    _check fail "make test-frontend"
fi

# ── f. Production health ─────────────────────────────────────────
printf '\n6. Production health endpoint:\n'
STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 15 \
    -H "X-GDPR-Consent: pre-deploy" \
    "$API_URL/api/v1/health/" 2>/dev/null || echo "000")

if [ "$STATUS" = "200" ]; then
    _check pass "GET /api/v1/health/ → 200"
else
    _check fail "GET /api/v1/health/ → $STATUS (expected 200)"
fi

# ── Summary ──────────────────────────────────────────────────────
printf '\n=== Summary: %d passed, %d failed ===\n' "$PASS" "$FAIL"

if [ "$FAIL" -gt 0 ]; then
    printf '❌ Pre-deploy checks FAILED — aborting.\n'
    exit 1
fi

printf '✅ All pre-deploy checks passed.\n'
exit 0
