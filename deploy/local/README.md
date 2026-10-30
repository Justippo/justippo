# Local Services Docker Compose

This directory contains the Docker Compose configuration for running both Hindsight and BabelDOC locally, exposed via Cloudflare Tunnel for external access.

## 🚀 Quick Start

### 1. Prerequisites
- Docker installed and running
- Docker Compose v2+ installed
- Mistral API key (for Hindsight)
- Cloudflare AI Gateway token (for BabelDOC)
- At least 12GB RAM available (3GB for Hindsight + 7GB for BabelDOC + overhead)

### 2. Configuration

Copy `.env.example` to `.env` and fill in your API keys:

```bash
cp .env.example .env
# Edit .env and set all required keys
```

#### Required Environment Variables

| Variable | Purpose | Source |
|----------|---------|--------|
| `MISTRAL_API_KEY` | Mistral API key for Hindsight LLM | https://console.mistral.ai/api-keys/ |
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare account ID | Cloudflare Dashboard |
| `CLOUDFLARE_AI_GATEWAY_TOKEN` | Cloudflare AI Gateway token | Cloudflare AI Gateway |
| `BABELDOC_AUTH_TOKEN` | BabelDOC API authentication | Generate random secret |

### 3. Start Services

```bash
cd deploy/local
docker compose up -d
```

This will:
- Build the BabelDOC image from the local sidecar code
- Pull the Hindsight image from GitHub Container Registry
- Start both containers
- Map ports: 8600 (Hindsight), 8750 (BabelDOC)

### 4. Verify Services

#### Hindsight
```bash
curl http://localhost:8600/health
# Expected: HTTP 200 OK
```

#### BabelDOC
```bash
curl http://localhost:8750/health
# Expected: HTTP 200 OK
```

### 5. External Access (via Cloudflare Tunnel)

With the Cloudflare Tunnel running:

```bash
# Hindsight
curl https://hindsight.evidenceeu.eu.mihai.codes/health

# BabelDOC
curl https://babeldoc.evidenceeu.eu.mihai.codes/health
```

Both should return HTTP 200 OK.

### 6. Stop Services

```bash
cd deploy/local
docker compose down
```

## 📊 Service Configuration

### Hindsight
- **Image:** ghcr.io/vectorize-io/hindsight:latest
- **Container:** justippo-hindsight
- **Port:** 127.0.0.1:8600:8600
- **Memory:** 3GB
- **CPU:** 2.0 cores
- **Data:** ~/.hindsight-data (persistent PostgreSQL)

### BabelDOC
- **Build:** Local sidecar (sidecars/babeldoc/)
- **Container:** justippo-babeldoc
- **Port:** 127.0.0.1:8750:8750
- **Memory:** 7GB
- **CPU:** 2.0 cores
- **LLM:** Cloudflare AI Gateway (@cf/meta/llama-3.3-70b-instruct-fp8-fast)

## 🔧 Troubleshooting

### Port Already in Use
```
Error: Address already in use
```

**Solution:** Check what's using the ports and stop it:
```bash
lsof -i :8600
lsof -i :8750
kill <PID>
```

### Permission Issues
```
Error: Permission denied
```

**Solution:** Ensure directories are writable:
```bash
chmod 755 ~/.hindsight-data
```

### BabelDOC Build Failure
```
Error: Build failed
```

**Solution:** Check build logs and ensure all dependencies are available:
```bash
docker compose build --no-cache
docker compose logs --follow
```

### Memory Issues
```
Error: Container killed (OOM)
```

**Solution:** Increase Docker memory allocation or reduce service memory limits.

## 📋 Individual Service Management

### Start Only Hindsight
```bash
docker compose up -d hindsight
```

### Start Only BabelDOC
```bash
docker compose up -d babeldoc
```

### View Logs
```bash
# All services
docker compose logs --follow

# Specific service
docker compose logs --follow hindsight
docker compose logs --follow babeldoc
```

## 🔗 References

- [Hindsight Documentation](https://github.com/vectorize-io/hindsight)
- [BabelDOC GitHub](https://github.com/babeldoc/babeldoc)
- [Cloudflare AI Gateway](https://developers.cloudflare.com/ai-gateway/)
- [Mistral API Documentation](https://docs.mistral.ai/)
