# Cloudflare Tunnel Setup for EvidenceEU

This directory contains the configuration and documentation for the Cloudflare Tunnel that exposes local Hindsight and BabelDOC services to the internet.

## 🚀 Quick Start

### 1. Install cloudflared

```bash
# macOS
brew install cloudflared

# Linux (Debian/Ubuntu)
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb -o cloudflared.deb
sudo dpkg -i cloudflared.deb

# Windows
winget install --id Cloudflare.cloudflared
```

### 2. Authenticate

```bash
cloudflared tunnel login
```

This opens a browser window. Select your Cloudflare account and domain.

### 3. Create Tunnel

```bash
cloudflared tunnel create evidenceeu
```

Note the tunnel UUID that is printed (e.g., `3b6702be-acde-41cf-8c73-c12136804106`).

### 4. Create DNS Routes

```bash
# Replace YOURDOMAIN.com with your actual domain
cloudflared tunnel route dns evidenceeu hindsight.YOURDOMAIN.com
cloudflared tunnel route dns evidenceeu babeldoc.YOURDOMAIN.com
```

### 5. Configure Tunnel

Copy the template config:

```bash
cp config.yml ~/.cloudflared/config-evidenceeu.yml
```

Edit the file and replace:
- `<TUNNEL_UUID>` with your actual tunnel UUID
- `<user>` with your username
- `YOURDOMAIN.com` with your actual domain

### 6. Test the Tunnel

```bash
cloudflared tunnel run evidenceeu
```

The tunnel will start and connect to Cloudflare's edge network. You can test the URLs:
- `https://hindsight.YOURDOMAIN.com` (will 502 until Hindsight is running)
- `https://babeldoc.YOURDOMAIN.com` (will 502 until BabelDOC is running)

### 7. Install as Service (Optional)

To keep the tunnel running after closing the terminal:

```bash
# Linux
sudo cloudflared service install
sudo systemctl start cloudflared

# macOS
sudo launchctl start com.cloudflare.cloudflared
```

## 📋 Configuration Reference

### File: `~/.cloudflared/config-evidenceeu.yml`

```yaml
tunnel: 3b6702be-acde-41cf-8c73-c12136804106  # Your tunnel UUID
credentials-file: /Users/yourname/.cloudflared/3b6702be-acde-41cf-8c73-c12136804106.json

ingress:
  - hostname: hindsight.evidenceeu.eu      # Hindsight service
    service: http://localhost:8600         # Local port 8600
  - hostname: babeldoc.evidenceeu.eu       # BabelDOC service
    service: http://localhost:8750          # Local port 8750
  - service: http_status:404                # REQUIRED catch-all rule
```

## 🔧 Troubleshooting

### Tunnel won't start
- **Error:** "No credentials found"
- **Fix:** Run `cloudflared tunnel login` first

### DNS routes not working
- **Error:** "Domain not found"
- **Fix:** Ensure the domain is added to your Cloudflare account and DNS is proxied (orange cloud)

### 502 Bad Gateway
- **Cause:** Local service not running
- **Fix:** Start Hindsight (`docker compose up -d`) and BabelDOC before testing

### Connection issues
- **Fix:** Check firewall settings, ensure ports 8600 and 8750 are not blocked

## 📊 Port Reference

| Service | Local Port | Tunnel URL |
|---------|------------|------------|
| Hindsight | 8600 | https://hindsight.YOURDOMAIN.com |
| BabelDOC | 8750 | https://babeldoc.YOURDOMAIN.com |

## 🔗 References

- [Cloudflare Tunnel Documentation](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/)
- [cloudflared CLI Reference](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/tunnel-guide/local/local-management/)
- [Ingress Rules Reference](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/configuration/ingress/)
