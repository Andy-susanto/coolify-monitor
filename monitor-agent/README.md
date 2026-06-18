# Monitor Agent

Lightweight Docker container stats agent. Deploy on the Coolify server.

## Cara Deploy di Coolify

### Option 1: Manual (via SSH ke server Coolify)

```bash
# 1. Copy folder monitor-agent ke server
scp -r monitor-agent/ root@coolify-server:/opt/monitor-agent/

# 2. SSH ke server
ssh root@coolify-server

# 3. Build & run
cd /opt/monitor-agent
docker compose up -d --build
```

### Option 2: Deploy via Coolify UI

1. Buka Coolify → New → Service → Docker Compose
2. Paste isi `docker-compose.yml`
3. Build context: upload folder `monitor-agent/`
4. Deploy

### Option 3: Deploy sebagai Application (Git)

1. Push folder `monitor-agent/` ke Git repo
2. Coolify → New → Application → pilih repo
3. Build pack: Dockerfile
4. Port: 9999
5. Mount Docker socket: `/var/run/docker.sock:/var/run/docker.sock:ro`
6. Deploy

## Environment Variables

| Variable     | Default | Description                    |
|-------------|---------|--------------------------------|
| `PORT`      | 9999    | Port untuk HTTP API            |
| `AUTH_TOKEN`| (empty) | Bearer token untuk auth (opsional) |

## API Endpoints

```
GET /health              → Health check
GET /api/stats           → Container CPU/memory/network stats
GET /api/containers      → Container list (docker ps)
GET /api/server          → Server resource info (CPU, RAM, disk, load)
GET /api/all             → Semua data sekaligus
```

## Contoh Response

```json
{
  "ok": true,
  "containers": [...],
  "stats": [
    {
      "name": "bkdlkd",
      "cpu": "0.12%",
      "cpu_percent": 0.12,
      "mem_usage": "128.5MiB / 1.5GiB",
      "mem_used": "128.5MiB",
      "mem_limit": "1.5GiB",
      "mem_perc": "8.34%",
      "mem_percent": 8.34,
      "net_io": "1.23MB / 456kB",
      "net_in": "1.23MB",
      "net_out": "456kB",
      "block_io": "12.3MB / 4.56MB",
      "block_read": "12.3MB",
      "block_write": "4.56MB",
      "pids": "42"
    }
  ],
  "server": {
    "cpu_cores": 4,
    "mem_total": 8589934592,
    "mem_used": 4294967296,
    "disk_total": 107374182400,
    "disk_used": 53687091200,
    "load_1m": 0.5,
    "load_5m": 0.3,
    "load_15m": 0.2
  }
}
```
