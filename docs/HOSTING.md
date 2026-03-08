# Hosting Options

Flow can be hosted anywhere — VPS, home server, cloud VM, etc.

## Our Setup (Cloudflare)

We use Cloudflare for hosting:
- **Cloudflare Tunnel** — exposes the local FastAPI server to the internet without opening ports
- **DNS** — point your domain to the tunnel
- **Optional:** Cloudflare Access for authentication layer

This is just one option. Flow is a standard FastAPI app that runs on any Python 3.10+ environment.

## Minimal Setup

1. Run the API: `python api.py`
2. Reverse proxy (nginx, caddy, etc.) to expose it
3. Point your OAuth redirect URI to the public URL

## Systemd Service

Use the provided template:

```bash
./scripts/install-service.sh /path/to/flow
sudo systemctl start flow
```

## Nginx Example

See `nginx.conf.example` for a minimal nginx reverse proxy config.

Replace `YOUR_DOMAIN_HERE` with your actual domain:

```bash
cp nginx.conf.example /etc/nginx/sites-available/flow
# Edit: replace YOUR_DOMAIN_HERE with your domain
sudo ln -s /etc/nginx/sites-available/flow /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

## Cloudflare Tunnel (no open ports)

```bash
# Install cloudflared
# https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/

# Create a tunnel
cloudflared tunnel create flow

# Route traffic
cloudflared tunnel route dns flow your-domain.com

# Run (or add to systemd)
cloudflared tunnel run flow
```

Flow binds to `127.0.0.1:5120` by default. Cloudflare Tunnel connects to that locally — no firewall changes needed.
