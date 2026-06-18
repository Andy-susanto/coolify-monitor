#!/usr/bin/env python3
"""Minimal Docker stats API — single file, no dependencies beyond stdlib + pip."""
import http.server, json, subprocess, os, urllib.parse
from datetime import datetime

PORT = int(os.getenv("PORT", "9999"))
TOKEN = os.getenv("AUTH_TOKEN", "")

class Handler(http.server.BaseHTTPRequestHandler):
    def _auth(self):
        if not TOKEN: return True
        auth = self.headers.get("Authorization", "").replace("Bearer ", "")
        return auth == TOKEN

    def _json(self, code, data):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def do_GET(self):
        if not self._auth():
            return self._json(401, {"error": "Unauthorized"})

        path = urllib.parse.urlparse(self.path).path

        if path == "/health":
            return self._json(200, {"status": "ok"})

        if path in ("/api/stats", "/api/all", "/api/server", "/api/containers"):
            result = {"ok": True, "ts": datetime.utcnow().isoformat() + "Z"}

            # Server info
            server = {}
            try:
                with open("/proc/loadavg") as f:
                    p = f.read().split()
                    server["load_1m"], server["load_5m"], server["load_15m"] = float(p[0]), float(p[1]), float(p[2])
            except: pass
            try:
                with open("/proc/meminfo") as f:
                    info = {}
                    for line in f:
                        parts = line.split(":")
                        if len(parts) == 2:
                            info[parts[0].strip()] = parts[1].strip()
                    total = int(info.get("MemTotal", "0").split()[0]) * 1024
                    avail = int(info.get("MemAvailable", "0").split()[0]) * 1024
                    server["mem_total"] = total
                    server["mem_used"] = total - avail
                    server["mem_free"] = avail
            except: pass
            try:
                r = subprocess.run(["nproc"], capture_output=True, text=True, timeout=3)
                server["cpu_cores"] = int(r.stdout.strip()) if r.returncode == 0 else 0
            except: pass
            try:
                r = subprocess.run(["df", "-B1", "/"], capture_output=True, text=True, timeout=3)
                if r.returncode == 0:
                    parts = r.stdout.strip().split("\n")[1].split()
                    server["disk_total"], server["disk_used"], server["disk_free"] = int(parts[1]), int(parts[2]), int(parts[3])
            except: pass

            result["server"] = server

            # Container stats
            if path in ("/api/stats", "/api/all"):
                stats = []
                try:
                    r = subprocess.run(
                        ["docker", "stats", "--no-stream", "--format",
                         '{"n":"{{.Name}}","c":"{{.CPUPerc}}","mu":"{{.MemUsage}}","mp":"{{.MemPerc}}","ni":"{{.NetIO}}","bi":"{{.BlockIO}}","p":"{{.PIDs}}"}'],
                        capture_output=True, text=True, timeout=20
                    )
                    for line in r.stdout.strip().split("\n"):
                        if line.strip():
                            try:
                                d = json.loads(line)
                                cpu = float(d.get("c", "0%").replace("%", ""))
                                mp = float(d.get("mp", "0%").replace("%", ""))
                                mu_parts = d.get("mu", " / ").split(" / ")
                                ni_parts = d.get("ni", " / ").split(" / ")
                                bi_parts = d.get("bi", " / ").split(" / ")
                                stats.append({
                                    "name": d["n"], "cpu_percent": cpu, "cpu": d.get("c", "0%"),
                                    "mem_percent": mp, "mem_used": mu_parts[0].strip(),
                                    "mem_limit": mu_parts[1].strip() if len(mu_parts) > 1 else "",
                                    "net_in": ni_parts[0].strip(), "net_out": ni_parts[1].strip() if len(ni_parts) > 1 else "",
                                    "block_read": bi_parts[0].strip(), "block_write": bi_parts[1].strip() if len(bi_parts) > 1 else "",
                                    "pids": d.get("p", "0")
                                })
                            except: continue
                except: pass
                result["stats"] = stats

            # Container list
            if path in ("/api/containers", "/api/all"):
                containers = []
                try:
                    r = subprocess.run(
                        ["docker", "ps", "-a", "--format",
                         '{"id":"{{.ID}}","name":"{{.Names}}","image":"{{.Image}}","status":"{{.Status}}","state":"{{.State}}"}'],
                        capture_output=True, text=True, timeout=10
                    )
                    for line in r.stdout.strip().split("\n"):
                        if line.strip():
                            try: containers.append(json.loads(line))
                            except: continue
                except: pass
                result["containers"] = containers

            return self._json(200, result)

        self._json(404, {"error": "Not found"})

    def log_message(self, format, *args):
        pass  # Suppress logs

if __name__ == "__main__":
    print(f"  Monitor Agent on :{PORT}")
    http.server.HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
