# Edge Report Deployment Guide

Complete instructions for deploying Edge Report on UNRAID or any Docker-capable server.

## Prerequisites

- Docker and Docker Compose installed
- Port 8000 available (or modify docker-compose.yml)
- For Cloudflare Tunnel: Cloudflare account with tunnel configured

## Quick Deploy (5 minutes)

```bash
# 1. Clone the repository
git clone https://github.com/sean-m-sweeney/nhl-edge-report.git
cd nhl-edge-report

# 2. Create environment file
cat > .env << EOF
API_REFRESH_KEY=$(openssl rand -hex 32)
TZ=America/New_York
EOF

# 3. Start the container
docker-compose up -d

# 4. Verify it's running
curl http://localhost:8000/api/health
```

The first startup takes 2-3 minutes to fetch initial data from the NHL API.

## UNRAID-Specific Setup

### Option 1: Docker Compose (Recommended)

1. **Install Docker Compose Manager**:
   - Open UNRAID web UI
   - Go to **Apps** (Community Applications must be installed)
   - Search for "Docker Compose Manager"
   - Click Install and use default settings
   - After installation, "Compose" appears under the Docker tab

2. **Create the stack**:
   - Go to Docker > Compose
   - Click "Add New Stack"
   - Name: `edge-report`
   - Paste the contents of `docker-compose.yml`
   - Add environment variables in the UI or create `.env` file

3. **Set up the appdata path** (optional, for persistence):
   ```yaml
   volumes:
     - /mnt/user/appdata/edge-report:/app/data
   ```

### Option 2: Docker Run Command

```bash
docker run -d \
  --name edge-report \
  --restart unless-stopped \
  -p 8000:8000 \
  -v /mnt/user/appdata/edge-report:/app/data \
  -e API_REFRESH_KEY=your-secret-key-here \
  -e TZ=America/New_York \
  edge-report:latest
```

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `API_REFRESH_KEY` | Yes | `dev-key-change-me` | Secret key for manual refresh API |
| `TZ` | No | `America/New_York` | Timezone for cron scheduling |
| `DATA_DIR` | No | `/app/data` | SQLite database location |

### Generating a Secure API Key

```bash
# Linux/Mac
openssl rand -hex 32

# Or use Python
python3 -c "import secrets; print(secrets.token_hex(32))"
```

## Cloudflare Tunnel Setup

To expose Caps Edge publicly without opening ports:

### 1. Create a Tunnel

```bash
# Install cloudflared (on UNRAID, use Docker)
docker run -d --name cloudflared \
  cloudflare/cloudflared:latest tunnel --no-autoupdate run \
  --token YOUR_TUNNEL_TOKEN
```

### 2. Configure the Tunnel

In Cloudflare Zero Trust dashboard:
1. Go to Access > Tunnels
2. Select your tunnel > Configure
3. Add a public hostname:
   - Subdomain: `capsedge` (or your choice)
   - Domain: `yourdomain.com`
   - Service: `http://edge-report:8000`

### 3. DNS Setup

Cloudflare automatically creates a CNAME record pointing to your tunnel.

Your app will be available at: `https://capsedge.yourdomain.com`

## Reverse Proxy Setup (Alternative to Cloudflare)

### Nginx Proxy Manager (UNRAID)

1. Add a new Proxy Host:
   - Domain: `capsedge.yourdomain.com`
   - Scheme: `http`
   - Forward Hostname: `edge-report` (container name) or IP
   - Forward Port: `8000`
   - Enable SSL (Let's Encrypt)

### Traefik Labels

Add to docker-compose.yml:

```yaml
services:
  edge-report:
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.capsedge.rule=Host(`capsedge.yourdomain.com`)"
      - "traefik.http.routers.capsedge.tls.certresolver=letsencrypt"
      - "traefik.http.services.capsedge.loadbalancer.server.port=8000"
```

## Data Refresh Schedule

Data automatically refreshes via cron once daily at:
- **6:00 AM ET**

### Manual Refresh

Trigger a refresh via API:

```bash
# Async (returns immediately, runs in background)
curl -H "X-API-Key: YOUR_API_KEY" http://localhost:8000/api/refresh

# Sync (waits for completion)
curl -H "X-API-Key: YOUR_API_KEY" http://localhost:8000/api/refresh/sync
```

### View Refresh Logs

```bash
docker logs edge-report --tail 100
# Or
docker exec edge-report cat /var/log/edge-report-refresh.log
```

## Health Monitoring

### Health Check Endpoint

```bash
curl http://localhost:8000/api/health
```

Response:
```json
{
  "status": "healthy",
  "last_updated": "2026-01-11T19:31:34.240954",
  "player_count": 23
}
```

### Docker Health Check

The container includes a built-in health check. View status:

```bash
docker inspect edge-report --format='{{.State.Health.Status}}'
```

### Uptime Monitoring (Optional)

Add to Uptime Kuma or similar:
- URL: `http://edge-report:8000/api/health`
- Expected: `"status":"healthy"`

## Backup & Restore

### Backup Database

```bash
# Stop container first for consistency
docker-compose stop
cp /mnt/user/appdata/edge-report/caps_edge.db /mnt/user/backups/caps_edge_$(date +%Y%m%d).db
docker-compose start
```

### Restore Database

```bash
docker-compose stop
cp /mnt/user/backups/caps_edge_YYYYMMDD.db /mnt/user/appdata/edge-report/caps_edge.db
docker-compose start
```

## Updating

### Pull Latest Changes

```bash
cd edge-report
git pull
docker-compose build --no-cache
docker-compose up -d
```

### Version Pinning

To pin to a specific version, use git tags:

```bash
git checkout v1.0.0
docker-compose build
docker-compose up -d
```

## Troubleshooting

### Container Won't Start

```bash
# Check logs
docker logs edge-report

# Common issues:
# - Port 8000 already in use: change port in docker-compose.yml
# - Permission issues: check volume mount permissions
```

### No Data Showing

```bash
# Check if database exists
docker exec edge-report ls -la /app/data/

# Trigger manual refresh
curl -H "X-API-Key: YOUR_KEY" http://localhost:8000/api/refresh/sync

# Check refresh logs
docker logs edge-report --tail 50
```

### API Returns 500 Errors

```bash
# Check container logs for Python errors
docker logs edge-report --tail 100 | grep -i error

# Restart container
docker-compose restart
```

### Cron Not Running

```bash
# Verify cron is running in container
docker exec edge-report service cron status

# Check crontab is installed
docker exec edge-report crontab -l
```

## Performance Tuning

### For High Traffic

Add to docker-compose.yml:

```yaml
services:
  edge-report:
    deploy:
      resources:
        limits:
          cpus: '1.0'
          memory: 512M
```

### Database Optimization

The SQLite database is small (~1MB) and doesn't require optimization for this use case.

## Security Considerations

1. **API Key**: Always use a strong, unique API key in production
2. **HTTPS**: Always use HTTPS in production (via Cloudflare or reverse proxy)
3. **Firewall**: Don't expose port 8000 directly to the internet
4. **Updates**: Keep Docker images updated for security patches

## Support

- Issues: https://github.com/sean-m-sweeney/nhl-edge-report/issues
- Ko-fi: https://ko-fi.com/edgereport
