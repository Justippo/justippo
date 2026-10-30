# Hindsight Local Docker Setup

This directory contains the Docker Compose configuration for running Hindsight locally, exposed via Cloudflare Tunnel for external access.

## 🚀 Quick Start

### 1. Prerequisites
- Docker installed and running
- Docker Compose v2+ installed
- Mistral API key (for LLM operations)
- At least 4GB RAM available (3GB for container + overhead)

### 2. Configuration

#### Environment Variables

Copy `.env.example` to `.env` and add your Mistral API key:

```bash
cp .env.example .env
# Edit .env and set MISTRAL_API_KEY
```

#### Required Variables
- `MISTRAL_API_KEY` - Your Mistral API key from https://console.mistral.ai/api-keys/

#### Optional Variables
You can add these to your `.env` file:
```
HINDSIGHT_API_LLM_MODEL=mistral-small-latest
HINDSIGHT_API_LLM_MAX_INPUT_TOKENS=16000
HINDSIGHT_API_LLM_MAX_OUTPUT_TOKENS=2048
HINDSIGHT_API_LLM_TEMPERATURE=0.7
```

### 3. Start Hindsight

```bash
cd deploy/hindsight-local
docker compose up -d
```

This will:
- Pull the latest Hindsight image from GitHub Container Registry
- Create and start the container
- Map port 8888 (container) to 8600 (host)
- Mount ~/.hindsight-data for persistent PostgreSQL storage

### 4. Verify Installation

#### Local Access
```bash
curl http://localhost:8600/health
# Expected: HTTP 200 OK
```

#### External Access (via Cloudflare Tunnel)
```bash
curl https://hindsight.evidenceeu.eu.mihai.codes/health
# Expected: HTTP 200 OK (once tunnel is running)
```

### 5. Stop Hindsight

```bash
cd deploy/hindsight-local
docker compose down
```

## 📊 Resource Management

The container is configured with resource limits:
- **Memory:** 3GB (adjust if you have more/less available)
- **CPU:** 2.0 cores

To change these, edit the `deploy.resources.limits` section in `docker-compose.yml`.

## 🔧 Troubleshooting

### Port Already in Use
```
Error: Address already in use
```

**Solution:** Check what's using port 8600 and stop it:
```bash
lsof -i :8600
kill <PID>
```

### Permission Issues
```
Error: Permission denied for ~/.hindsight-data
```

**Solution:** Ensure the directory is writable:
```bash
chmod 755 ~/.hindsight-data
chown -R $(whoami) ~/.hindsight-data
```

### Mistral API Key Not Found
```
Error: MISTRAL_API_KEY not set
```

**Solution:** Set the key in `.env` file:
```bash
echo "MISTRAL_API_KEY=your-key-here" > .env
```

### Container Fails to Start
```
Error: Container exited with code 1
```

**Solution:** Check logs:
```bash
docker compose logs
docker compose logs hindsight
```

## 📋 Configuration Reference

### Ports
- **Host:** 8600 (matches Cloudflare Worker expectation)
- **Container:** 8888 (Hindsight default)

### Volumes
- **Host:** ~/.hindsight-data
- **Container:** /home/hindsight/.pg0
- **Purpose:** Persistent PostgreSQL data

### Environment Variables

| Variable | Purpose | Required | Default |
|----------|---------|----------|---------|
| `HINDSIGHT_API_WORKER_ID` | Stable worker ID | Yes | `evidenceeu-local` |
| `HINDSIGHT_API_LLM_PROVIDER` | LLM provider | Yes | `mistral` |
| `MISTRAL_API_KEY` | Mistral API key | Yes | (none) |
| `HINDSIGHT_API_PORT` | Internal port | Yes | `8888` |

### Important Notes

1. **Stable Worker ID:** `HINDSIGHT_API_WORKER_ID` must be stable to prevent zombie operations on restart. Do not use random values.

2. **Port Mapping:** The host port (8600) matches the Cloudflare Worker configuration. If you change this, update the worker config too.

3. **Data Persistence:** The PostgreSQL data is stored in ~/.hindsight-data on your host machine. This persists across container restarts.

4. **Resource Limits:** The memory and CPU limits prevent the container from overwhelming your laptop. Adjust based on your available resources.

## 🔗 References

- [Hindsight Documentation](https://github.com/vectorize-io/hindsight)
- [Hindsight Docker Image](https://github.com/vectorize-io/hindsight/pkgs/container/hindsight)
- [Mistral API Documentation](https://docs.mistral.ai/)
