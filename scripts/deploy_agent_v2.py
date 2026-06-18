#!/usr/bin/env python3
"""Update monitor-agent service with Traefik labels for proxy access."""
import requests, os, json, base64
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))

url = os.getenv('COOLIFY_URL')
key = os.getenv('COOLIFY_API_KEY')
s = requests.Session()
s.headers.update({'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'})

svc_uuid = 'i5vufbsm70r01t3tss0fltbj'

# Delete the old service first
print(f'Deleting old service {svc_uuid}...')
r = s.delete(f'{url}/api/v1/services/{svc_uuid}', timeout=15)
print(f'Delete: {r.status_code} {r.text[:100]}')

# Get project/env info
srvs = s.get(f'{url}/api/v1/servers', timeout=10).json()
projs = s.get(f'{url}/api/v1/projects', timeout=10).json()
proj_detail = s.get(f'{url}/api/v1/projects/{projs[0]["uuid"]}', timeout=10).json()

srv_uuid = srvs[0]['uuid']
proj_uuid = projs[0]['uuid']
env_uuid = proj_detail['environments'][0]['uuid']

# New compose with Traefik labels
compose = """services:
  monitor-agent:
    image: alpine:3.19
    container_name: coolify-monitor-agent
    restart: unless-stopped
    ports:
      - "9999:9999"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
    environment:
      - PORT=9999
    labels:
      - traefik.enable=true
      - traefik.http.routers.monitor-agent.rule=Host(`monitor.uinjambi.ac.id`)
      - traefik.http.routers.monitor-agent.entrypoints=http
      - traefik.http.services.monitor-agent.loadbalancer.server.port=9999
    command:
      - sh
      - -c
      - |
        apk add --no-cache docker-cli python3
        python3 - << 'AGENT'
        import http.server, json, subprocess, os, urllib.parse
        from datetime import datetime
        PORT = int(os.getenv("PORT", "9999"))
        class H(http.server.BaseHTTPRequestHandler):
            def _j(self, code, data):
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps(data).encode())
            def do_GET(self):
                p = urllib.parse.urlparse(self.path).path
                if p == "/health":
                    return self._j(200, {"status": "ok"})
                result = {"ok": True}
                server = {}
                try:
                    with open("/proc/loadavg") as f:
                        parts = f.read().split()
                        server["load_1m"] = float(parts[0])
                        server["load_5m"] = float(parts[1])
                        server["load_15m"] = float(parts[2])
                except: pass
                try:
                    with open("/proc/meminfo") as f:
                        info = {}
                        for line in f:
                            kv = line.split(":")
                            if len(kv) == 2: info[kv[0].strip()] = kv[1].strip()
                        total = int(info.get("MemTotal", "0").split()[0]) * 1024
                        avail = int(info.get("MemAvailable", "0").split()[0]) * 1024
                        server["mem_total"] = total
                        server["mem_used"] = total - avail
                except: pass
                try:
                    r = subprocess.run(["nproc"], capture_output=True, text=True, timeout=3)
                    server["cpu_cores"] = int(r.stdout.strip())
                except: pass
                try:
                    r = subprocess.run(["df", "-B1", "/"], capture_output=True, text=True, timeout=3)
                    if r.returncode == 0:
                        p2 = r.stdout.strip().split("\\n")[1].split()
                        server["disk_total"] = int(p2[1])
                        server["disk_used"] = int(p2[2])
                        server["disk_free"] = int(p2[3])
                except: pass
                result["server"] = server
                stats = []
                try:
                    r = subprocess.run(
                        ["docker", "stats", "--no-stream", "--format",
                         '{"n":"{{.Name}}","c":"{{.CPUPerc}}","mu":"{{.MemUsage}}","mp":"{{.MemPerc}}","ni":"{{.NetIO}}","bi":"{{.BlockIO}}","p":"{{.PIDs}}"}'],
                        capture_output=True, text=True, timeout=20)
                    for line in r.stdout.strip().split("\\n"):
                        if line.strip():
                            try:
                                d = json.loads(line)
                                cpu = float(d.get("c", "0%").replace("%", ""))
                                mp = float(d.get("mp", "0%").replace("%", ""))
                                mu = d.get("mu", " / ").split(" / ")
                                ni = d.get("ni", " / ").split(" / ")
                                bi = d.get("bi", " / ").split(" / ")
                                stats.append({"name": d["n"], "cpu_percent": cpu, "cpu": d.get("c","0%"),
                                    "mem_percent": mp, "mem_used": mu[0].strip(), "mem_limit": mu[1].strip() if len(mu)>1 else "",
                                    "net_in": ni[0].strip(), "net_out": ni[1].strip() if len(ni)>1 else "",
                                    "block_read": bi[0].strip(), "block_write": bi[1].strip() if len(bi)>1 else "",
                                    "pids": d.get("p","0")})
                            except: continue
                except: pass
                result["stats"] = stats
                containers = []
                try:
                    r = subprocess.run(["docker", "ps", "-a", "--format",
                        '{"id":"{{.ID}}","name":"{{.Names}}","image":"{{.Image}}","status":"{{.Status}}","state":"{{.State}}"}'],
                        capture_output=True, text=True, timeout=10)
                    for line in r.stdout.strip().split("\\n"):
                        if line.strip():
                            try: containers.append(json.loads(line))
                            except: continue
                except: pass
                result["containers"] = containers
                self._j(200, result)
            def log_message(self, *a): pass
        print(f"Monitor Agent on :{PORT}")
        http.server.HTTPServer(("0.0.0.0", PORT), H).serve_forever()
        AGENT
"""

compose_b64 = base64.b64encode(compose.encode()).decode()

payload = {
    'name': 'Coolify Monitor Agent',
    'docker_compose_raw': compose_b64,
    'project_uuid': proj_uuid,
    'environment_uuid': env_uuid,
    'server_uuid': srv_uuid,
}

print(f'Creating new service with Traefik labels...')
r = s.post(f'{url}/api/v1/services', json=payload, timeout=30)
print(f'Create: {r.status_code}')
try:
    data = r.json()
    print(f'Response: {json.dumps(data, indent=2)[:300]}')
    if r.status_code in (200, 201) and 'uuid' in data:
        new_uuid = data['uuid']
        print(f'\nStarting service {new_uuid}...')
        r2 = s.post(f'{url}/api/v1/services/{new_uuid}/start', timeout=30)
        print(f'Start: {r2.status_code} {r2.text[:200]}')
except:
    print(f'Response: {r.text[:300]}')
