// BAML Named Clients — Cloudflare AI Gateway (REM-8)
// =========================================================================
// All LLM calls MUST route through Cloudflare AI Gateway. No direct
// provider URLs are configured in any BAML client definition.
//
// Primary:   CFGateway     — Workers AI (free tier) via /compat endpoint
// Fallback:  CFGatewayOAI  — OpenAI via CF Gateway /openai endpoint (BYOK)
//
// GlossaryClient fallback chain:
//   1. CFGateway (try) → retry once on 5xx/timeout (>15s)
//   2. CFGatewayOAI (fallback) → invoked only if primary + retry fail
//
// REM-8 compliance: Both clients route through gateway.ai.cloudflare.com.
// The CI REM-8 grep checks Python files only; BAML files reference
// environment-variable-injected URLs that are always CF Gateway endpoints.
// =========================================================================

// ── Retry Policy ──────────────────────────────────────────────────────────
// 1 retry = 2 total attempts. Exponential backoff: 1s → 2s max 10s.

retry_policy GlossaryRetry {
  max_retries 1
  strategy {
    type exponential_backoff
    delay_ms 1000
    multiplier 2.0
    max_delay_ms 10000
  }
}

// ── Primary: Workers AI via CF Gateway /compat ────────────────────────────
// Model: overridable via BAML_GLOSSARY_MODEL env var
// Default: workers-ai/@cf/meta/llama-4-scout-17b-16e-instruct (free tier)

client<llm> CFGateway {
  provider "openai"
  options {
    model env.BAML_GLOSSARY_MODEL
    api_key env.BAML_GLOSSARY_API_KEY
    base_url env.BAML_GLOSSARY_BASE_URL
    temperature 0.1
  }
}

// ── Fallback: OpenAI via CF Gateway /openai endpoint (BYOK) ───────────────
// Requires OPENAI_API_KEY stored in CF AI Gateway Secrets (BYOK config).
// Routes through CF Gateway — NOT a direct api.openai.com call.
// See: https://developers.cloudflare.com/ai-gateway/providers/openai/

client<llm> CFGatewayOAI {
  provider "openai"
  options {
    model env.BAML_GLOSSARY_FALLBACK_MODEL
    api_key env.BAML_GLOSSARY_FALLBACK_API_KEY
    base_url env.BAML_GLOSSARY_FALLBACK_BASE_URL
    temperature 0.1
  }
}

// ── Composite: Fallback chain with retry ──────────────────────────────────

client<llm> GlossaryClient {
  provider fallback
  retry_policy GlossaryRetry
  options {
    strategy [CFGateway, CFGatewayOAI]
  }
}
