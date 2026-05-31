# Cloudflare Tunnel Setup — storyteller.techvigilant.com

## Overview

The Story Engine frontend and backend are exposed via your existing Cloudflare Tunnel
on ZimaOS (Mac Mini 2014). No port-forwarding or public IP needed.

---

## Step 1 — Add DNS Record via Wrangler CLI

Install wrangler if you haven't:
```bash
npm install -g wrangler
wrangler login   # opens browser, log in with abrarhasinpranto@gmail.com
```

Your zone ID for techvigilant.com: `c1f525bdc6a810b8bdba76c6716f6276`

Add the CNAME record pointing to your tunnel:
```bash
# First get your tunnel ID:
cloudflared tunnel list

# Add the CNAME (replace <TUNNEL_ID> with your actual tunnel ID):
wrangler dns add c1f525bdc6a810b8bdba76c6716f6276 \
  --type CNAME \
  --name storyteller \
  --content <TUNNEL_ID>.cfargotunnel.com \
  --proxied
```

Or do it via Cloudflare Dashboard:
1. Go to DNS → Add record
2. Type: CNAME
3. Name: storyteller
4. Target: <TUNNEL_ID>.cfargotunnel.com
5. Proxy: ON (orange cloud)

---

## Step 2 — Update Tunnel Ingress on ZimaOS

SSH into your ZimaOS or edit via the terminal on ZimaOS.
Your tunnel config is typically at:
`/root/.cloudflared/config.yml`

Add these ingress rules **above** the catch-all `404` rule:

```yaml
ingress:
  # ... existing rules (obsidian, immich, home assistant, etc.) ...

  - hostname: storyteller.techvigilant.com
    service: http://localhost:5173   # frontend (React dev) or nginx in prod
    originRequest:
      noTLSVerify: false

  - hostname: storyteller.techvigilant.com
    path: /api
    service: http://localhost:8000   # FastAPI backend

  # catch-all (must be last)
  - service: http_status:404
```

For production, use a single nginx container that reverse-proxies:
- `/`     → frontend:5173
- `/api`  → backend:8000

Then the ingress rule becomes:
```yaml
  - hostname: storyteller.techvigilant.com
    service: http://nginx:80
```

Restart the tunnel after editing:
```bash
# If running as Docker container on ZimaOS:
docker restart cloudflared

# If running as service:
sudo systemctl restart cloudflared
```

---

## Step 3 — Production docker-compose.prod.yml on ZimaOS

Place the repo at `/DATA/AppData/story-engine/` on ZimaOS and use:
```bash
docker compose -f docker-compose.prod.yml up -d
```

The GitHub Actions workflow (`.github/workflows/deploy.yml`) will SSH into ZimaOS
and run this automatically on every push to `main`.

---

## Required GitHub Secrets

Add these in your GitHub repo → Settings → Secrets → Actions:

| Secret | Value |
|---|---|
| `ZIMAOS_HOST` | 192.168.0.127 |
| `ZIMAOS_USER` | root (or your ZimaOS user) |
| `ZIMAOS_SSH_KEY` | Your private SSH key (generate with ssh-keygen) |
