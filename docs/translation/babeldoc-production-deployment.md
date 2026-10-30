# BabelDOC Production Deployment Runbook

**Audience:** Infrastructure owner, cloud platform team  
**Purpose:** Deploy and wire the BabelDOC sidecar for production PDF reference translation  
**Last updated:** 2026-07-22  
**Status:** Deployed (local Docker + Cloudflare Tunnel, 2026-07-21)

---

## Overview

The BabelDOC sidecar provides layout-preserving PDF translation via a single HTTP endpoint. It runs as a separate Docker container in an approved EU region and is called by the Cloudflare Python Worker backend via the adapter in `backend/app/integrations/babeldoc_adapter.py`.

**Architecture:**
```
Cloudflare Worker (Pyodide)
  └── FastAPI backend (app/worker.py)
        └── babeldoc_adapter.py (httpx async POST)
              │
              ▼ HTTPS (authenticated)
        ┌─────────────────────────────┐
        │  BabelDOC Sidecar           │
        │  (Docker, EU region)        │
        │  - Python 3.12              │
        │  - BabelDOC + dependencies  │
        │  - OpenAI-compatible wrapper│
        └─────────────────────────────┘
              │
              ▼ (internal)
        Cloudflare AI Gateway (chat-completions model, OpenAI-compatible)
```

---

## Pre-Deployment Checklist

- [ ] Approved EU-region host provisioned (AWS, Azure, GCP, or equivalent)
- [ ] Docker runtime installed and tested
- [ ] 4 GB RAM available (2 GB minimum, 4 GB recommended for >20-page docs)
- [ ] 1 GB disk space available (models + temp PDF workspace)
- [ ] Outbound HTTPS allowed to Cloudflare (for AI Gateway calls)
- [ ] Inbound HTTPS allowed from Cloudflare Worker (service-to-service)
- [ ] GitHub `BABELDOC_SIDECAR_URL` secret prepared but not yet set (will set in step 8)

---

## Deployment Steps

### 1. Clone the Repository

```bash
git clone https://github.com/chindris-mihai-alexandru/evidence-eu.git
cd evidence-eu
git checkout main
```

### 2. Prepare Environment Variables

Create a `.env.babeldoc` file with server-only configuration:

```bash
cat > .env.babeldoc << 'EOF'
# ⚠️ WRONG MODEL WARNING: m2m100-1.2b is NOT a chat model and will fail —
# BabelDOC calls /chat/completions. Use a chat-completions-capable model.
#
# RECOMMENDED (new, non-deprecated Workers AI REST endpoint — bare slug,
# no "workers-ai/" prefix). get_runtime_config() in app/runtime.py accepts
# either this host or the /compat host below.
BABELDOC_OPENAI_BASE_URL=https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/ai/v1
BABELDOC_OPENAI_API_KEY={CLOUDFLARE_AI_GATEWAY_TOKEN}
BABELDOC_OPENAI_MODEL=@cf/meta/llama-3.3-70b-instruct-fp8-fast
#
# ALTERNATIVE (deprecated but still functional — Cloudflare AI Gateway
# /compat endpoint; requires the "workers-ai/" provider prefix on the slug):
#   BABELDOC_OPENAI_BASE_URL=https://gateway.ai.cloudflare.com/v1/{ACCOUNT_ID}/{GATEWAY_ID}/compat
#   BABELDOC_OPENAI_MODEL=workers-ai/@cf/meta/llama-3.3-70b-instruct-fp8-fast

# HTTP server
BABELDOC_HOST=0.0.0.0
BABELDOC_PORT=8750

# Security (optional but recommended for production)
BABELDOC_AUTH_TOKEN={GENERATE_RANDOM_SECRET_TOKEN}
EOF
```

**Variables:**
- `BABELDOC_OPENAI_BASE_URL`: `api.cloudflare.com` (recommended REST endpoint) or `gateway.ai.cloudflare.com` (deprecated `/compat`, still functional) — both are validated by `get_runtime_config()`; any other hostname is rejected
- `BABELDOC_OPENAI_API_KEY`: API token with Workers AI scope (create in Cloudflare dashboard)
- `BABELDOC_OPENAI_MODEL`: An OpenAI-compatible **chat-completions** model. On the REST endpoint use a bare slug (`@cf/meta/llama-3.3-70b-instruct-fp8-fast`); on the deprecated `/compat` endpoint the slug needs a `workers-ai/` prefix. m2m100-1.2b is a translation-only model and does not implement `/chat/completions` on either endpoint
- `BABELDOC_AUTH_TOKEN`: **Required for production.** Bearer token enforced by the sidecar's `require_bearer_auth()` on `POST /translate`; the backend adapter sends it automatically via `_get_auth_headers()` when set on both sides

### 3. Build the Docker Image

```bash
cd sidecars/babeldoc
docker build -t evidence-eu-babeldoc:latest .
cd ../..
```

Expected output: `Successfully tagged evidence-eu-babeldoc:latest`

### 4. Run Local Test (Optional but Recommended)

Test the image locally before deploying to production:

```bash
docker run --rm -p 8750:8750 \
  --env-file .env.babeldoc \
  evidence-eu-babeldoc:latest
```

In another terminal, test the health endpoint:

```bash
curl http://localhost:8750/health
```

Expected response:
```json
{"status": "ok", "version": "1.0"}
```

If successful, stop the container: `Ctrl+C`

### 5. Deploy to Production Host

Production runs on **local Docker** via Cloudflare Tunnel — see `deploy/local/docker-compose.yml`.

```bash
# Build and start
cd deploy/local
docker compose up -d babeldoc

# Verify health
curl http://localhost:8750/health

# External access via Cloudflare Tunnel
curl https://babeldoc.evidenceeu.eu.mihai.codes/health
```

For local Docker testing (development only):

Use the manifest in `sidecars/babeldoc/k8s-deployment.yaml`:

```bash
kubectl create namespace evidence-eu
kubectl apply -f sidecars/babeldoc/k8s-deployment.yaml -n evidence-eu
kubectl get pods -n evidence-eu
```

See `sidecars/babeldoc/k8s-deployment.yaml` for resource requests, limits, and ingress configuration.

### 6. Verify Sidecar Health

From the production host (or via proxy):

```bash
curl -X GET https://{SIDECAR_HOST}/health
```

Expected response (200 OK):
```json
{"status": "ok", "version": "1.0"}
```

If health check fails, check Docker logs:

```bash
cd deploy/local
docker compose logs --follow babeldoc
```

Common issues:
- **Network timeout**: Check egress firewall rules (must reach Cloudflare API)
- **Auth error**: Verify `BABELDOC_OPENAI_API_KEY` and `BABELDOC_OPENAI_BASE_URL`
- **Model not found**: Verify the configured chat-completions model (e.g. `@cf/meta/llama-4-scout-17b-16e-instruct`) is available in your Cloudflare account

### 7. Test the Translation Endpoint

Create a test PDF (or use an existing one):

```bash
# Example: create a simple PDF for testing
echo "Test document content" | enscript -B -p - | ps2pdf - test.pdf
```

Call the translate endpoint:

```bash
curl -X POST https://{SIDECAR_HOST}/translate \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer {BABELDOC_AUTH_TOKEN}" \
  -d @- << 'EOF'
{
  "source_lang": "en",
  "target_lang": "de",
  "document_b64": "$(base64 -i test.pdf | tr -d '\n')",
  "preserve_layout": true,
  "glossary_csv_b64": null,
  "options": {}
}
EOF
```

Expected response (HTTP 200):
```json
{
  "translated_b64": "JVBERi0xLjc...",
  "detected_lang": "en",
  "processing_time_ms": 12500,
  "layout_preserved": true,
  "pages_processed": 1,
  "warnings": []
}
```

If the test passes, the sidecar is ready for production.

### 8. Set GitHub Actions Secret

In your repository settings (Settings → Secrets and variables → Actions → New repository secret):

**Name:** `BABELDOC_SIDECAR_URL`

**Value:** `https://{SIDECAR_HOST}/api` (with or without trailing slash — the adapter normalizes it)

**Example:** `https://babeldoc.eu.example.com/api`

> ⚠️ **Important:** This URL must be reachable from Cloudflare Workers. If you're using a private network or VPN, ensure the Worker has egress permissions.

### 9. Deploy Backend

The next push to `main` will:
1. Inject the URL as a Cloudflare Worker secret when it is configured.
2. Continue deploying safely with BabelDOC disabled when it is absent.
3. Require a reviewed `BABELDOC_ENABLED=true` change only after the sidecar health check passes.

The wiring is already in place. Enabling the production feature requires the reviewed
`backend/wrangler.toml` flag change after the sidecar is healthy.

### 10. Validate End-to-End in Production

Once deployed, test the full pipeline via the web app:

1. Navigate to `https://evidence-eu-frontend.pages.dev/translation`
2. Upload a test PDF (use non-sensitive synthetic content)
3. Select source and target languages
4. Click "Translate"
5. Expected result: A translated reference PDF downloads (not a "temporarily unavailable" message)

---

## Operational Concerns

### Memory and CPU

- **Minimum:** 2 GB RAM, 2 CPU cores
- **Recommended:** 4 GB RAM, 4 CPU cores
- **Peak:** During model loading and processing (first request ~15-30s cold start, subsequent requests 3-5s)

Monitor with:
```bash
docker stats evidence-eu-babeldoc
```

If memory pressure is high (>90% utilization), increase the container limit or add swap:

```bash
# docker-compose.yml
services:
  babeldoc:
    deploy:
      resources:
        limits:
          memory: 4G
        reservations:
          memory: 2G
```

### Disk Usage

- Models: ~500 MB (cached on first load)
- Temp workspace per request: ~2–3x input PDF size (cleaned up after each request)
- Ensure at least 1 GB free disk space

### Cold Start and Warm-Up

- **Cold start** (first request after container launch): 15–30 seconds (model loading)
- **Warm requests** (subsequent): 3–5 seconds per 10 pages

**Recommendation:** After deploy, make a dummy health check request to warm the model:

```bash
curl -X POST https://{SIDECAR_HOST}/translate \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer {BABELDOC_AUTH_TOKEN}" \
  -d '{"source_lang":"en","target_lang":"de","document_b64":"JVBERi0xLjcKCjEgMCBvYm=","preserve_layout":true}' \
  >/dev/null 2>&1 &
```

### Cost Estimation

- **Cloudflare AI Gateway:** Token-based pricing for the configured chat-completions model; see Cloudflare docs for per-model rates
- **Hosting:** Varies by cloud provider; budget 50–100 USD/month for a t2.medium or equivalent
- **Egress:** Plan for ~1–2 MB per request (LLM API calls + model inference)

### Logging and Debugging

Enable debug logging in the sidecar:

```bash
# Add to .env.babeldoc
BABELDOC_LOG_LEVEL=DEBUG
```

Logs are available via Docker:

```bash
cd deploy/local
docker compose logs --tail 100 babeldoc
```

Key log messages:
- `POST /translate from {client_ip}` — request received
- `Translation completed in {time}ms` — success
- `Error translating: {error}` — failure (see error code and message)

---

## Rollback and Troubleshooting

### If the Sidecar Goes Down

The backend gracefully handles sidecar unavailability:
- Returns HTTP 503 `SERVICE_UNAVAILABLE` with the error `SERVICE_UNAVAILABLE`
- Frontend shows "PDF reference translation is temporarily unavailable"
- Users can retry or re-upload

**To restore:**
1. Check sidecar logs for errors
2. Redeploy if needed: `cd deploy/local && docker compose up -d babeldoc`
3. Verify health: `curl https://{SIDECAR_HOST}/health`
4. Re-test with a small PDF

### If the Sidecar is Slow

- Check CPU and memory usage: `docker stats`
- Check network latency to Cloudflare: `curl -w "@curl-format.txt" https://api.cloudflare.com/`
- Check LLM queue on Cloudflare Workers AI
- Consider scaling horizontally (multiple sidecar instances behind a load balancer)

### If Translation Quality is Poor

- Check that a chat-completions model is configured: `BABELDOC_OPENAI_MODEL=@cf/meta/llama-4-scout-17b-16e-instruct` (NOT m2m100-1.2b — it does not support `/chat/completions`)
- Verify the source PDF is readable (not scanned or password-protected)
- Check BabelDOC version matches the pinned requirements in `sidecars/babeldoc/requirements.txt`

---

## Monitoring

### Recommended Metrics to Collect

1. **Health check response time** (should be < 100ms)
2. **Translation endpoint latency** (p50, p95, p99)
3. **Error rate** (count 4xx and 5xx responses)
4. **Model load time** (first request after container start)
5. **CPU and memory utilization**

### Integration with Observability Tools

Send logs to your preferred tool (Datadog, New Relic, CloudWatch, etc.):

```bash
# For Docker, use the logging driver
docker run \
  --log-driver awslogs \
  --log-opt awslogs-group=/ecs/evidence-eu \
  --log-opt awslogs-region=eu-west-1 \
  evidence-eu-babeldoc:latest
```

---

## References

- `docs/adr/ADR-012-babeldoc-sidecar-runtime.md` (architecture)
- `sidecars/babeldoc/README.md` (local testing)
- `backend/app/integrations/babeldoc_adapter.py` (API contract — source of truth)
- `deploy/local/docker-compose.yml` (local Docker + CF Tunnel — production path)
- `scripts/warmup-babeldoc-sidecar.sh` (post-deploy warm-up)
- `scripts/validate-babeldoc-sidecar.sh` (pre-deploy validation)
