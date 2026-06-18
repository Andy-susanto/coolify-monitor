#!/usr/bin/env python3
"""Coolify Monitor Agent v2 — supports container detail endpoints"""
import http.server, json, subprocess, os, urllib.parse
from datetime import datetime, timezone

PORT = int(os.getenv("PORT", "9999"))

class Handler(http.server.BaseHTTPRequestHandler):
    def _j(self, code, data):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def do_GET(self):
        p = urllib.parse.urlparse(self.path).path
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)

        if p == "/health":
            return self._j(200, {"status": "ok", "version": "2.0"})

        # ── /api/container/<name>/top|inspect|logs ──
        if p.startswith("/api/container/"):
            parts = p.strip("/").split("/")
            if len(parts) == 4 and parts[1] == "container":
                cname, action = parts[2], parts[3]
                if action == "top":
                    return self._handle_top(cname)
                elif action == "inspect":
                    return self._handle_inspect(cname)
                elif action == "logs":
                    nlines = int(qs.get("lines", ["100"])[0])
                    return self._handle_logs(cname, nlines)
            return self._j(404, {"ok": False, "error": "Invalid container endpoint"})

        # ── /api/containers ──
        if p == "/api/containers":
            return self._handle_containers()

        # ── Default: full status ──
        return self._handle_all()

    def _handle_top(self, cname):
        try:
            r = subprocess.run(
                ["docker", "top", cname, "-eo", "pid,user,%cpu,%mem,vsz,rss,tty,stat,start,time,command"],
                capture_output=True, text=True, timeout=10)
            lines = r.stdout.strip().split("\n")
            procs = []
            for line in lines[1:]:
                p2 = line.split(None, 10)
                if len(p2) >= 11:
                    procs.append({"pid":p2[0],"user":p2[1],"cpu":p2[2],"mem":p2[3],
                                  "vsz":p2[4],"rss":p2[5],"tty":p2[6],"stat":p2[7],
                                  "start":p2[8],"time":p2[9],"command":p2[10]})
                elif p2:
                    procs.append({"command": line.strip()})
            return self._j(200, {"ok": True, "container": cname, "processes": procs, "count": len(procs)})
        except Exception as e:
            return self._j(500, {"ok": False, "error": str(e)})

    def _handle_inspect(self, cname):
        try:
            r = subprocess.run(["docker", "inspect", cname], capture_output=True, text=True, timeout=10)
            data = json.loads(r.stdout)
            d = data[0] if data else {}
            filtered = {
                "id": d.get("Id","")[:12],
                "name": d.get("Name","").lstrip("/"),
                "image": d.get("Config",{}).get("Image",""),
                "created": d.get("Created",""),
                "state": d.get("State",{}),
                "restart_policy": d.get("HostConfig",{}).get("RestartPolicy",{}),
                "ports": d.get("NetworkSettings",{}).get("Ports",{}),
                "env_count": len(d.get("Config",{}).get("Env",[])),
                "mounts": [{"source":m.get("Source",""),"dest":m.get("Destination",""),
                            "mode":m.get("Mode","")} for m in d.get("Mounts",[])],
                "cmd": d.get("Config",{}).get("Cmd",[]),
                "entrypoint": d.get("Config",{}).get("Entrypoint",[]),
                "labels": {k:v for k,v in d.get("Config",{}).get("Labels",{}).items()
                           if k.startswith("coolify") or k.startswith("com.docker")},
                "networks": list(d.get("NetworkSettings",{}).get("Networks",{}).keys()),
                "healthcheck": d.get("Config",{}).get("Healthcheck"),
            }
            return self._j(200, {"ok": True, "container": cname, "inspect": filtered})
        except Exception as e:
            return self._j(500, {"ok": False, "error": str(e)})

    def _handle_logs(self, cname, nlines):
        try:
            r = subprocess.run(["docker", "logs", "--tail", str(nlines), "--timestamps", cname],
                               capture_output=True, text=True, timeout=15)
            output = (r.stdout or r.stderr or "").strip()
            return self._j(200, {"ok": True, "container": cname,
                                  "logs": output.split("\n") if output else [],
                                  "count": len(output.split("\n")) if output else 0})
        except Exception as e:
            return self._j(500, {"ok": False, "error": str(e)})

    def _handle_containers(self):
        containers = []
        try:
            r = subprocess.run(["docker", "ps", "-a", "--format",
                '{"id":"{{.ID}}","name":"{{.Names}}","image":"{{.Image}}","status":"{{.Status}}","state":"{{.State}}"}'],
                capture_output=True, text=True, timeout=10)
            for line in r.stdout.strip().split("\n"):
                if line.strip():
                    try: containers.append(json.loads(line))
                    except: continue
        except: pass
        return self._j(200, {"ok": True, "containers": containers, "count": len(containers)})

    def _handle_all(self):
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
                p2 = r.stdout.strip().split("\n")[1].split()
                server["disk_total"] = int(p2[1])
                server["disk_used"] = int(p2[2])
                server["disk_free"] = int(p2[3])
        except: pass
        result["server"] = server
        stats = []
        try:
            r = subprocess.run(["docker", "stats", "--no-stream", "--format",
                '{"n":"{{.Name}}","c":"{{.CPUPerc}}","mu":"{{.MemUsage}}","mp":"{{.MemPerc}}","ni":"{{.NetIO}}","bi":"{{.BlockIO}}","p":"{{.PIDs}}"}'],
                capture_output=True, text=True, timeout=20)
            for line in r.stdout.strip().split("\n"):
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
            for line in r.stdout.strip().split("\n"):
                if line.strip():
                    try: containers.append(json.loads(line))
                    except: continue
        except: pass
        result["containers"] = containers
        self._j(200, result)

    def log_message(self, *a): pass

print(f"Monitor Agent v2.0 on :{PORT}")
http.server.HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
