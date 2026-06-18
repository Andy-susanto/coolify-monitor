#!/usr/bin/env python3
"""
Coolify Container Monitor Agent - SECURED
Lightweight agent that reads Docker container stats and exposes them via HTTP.

Security layers:
  1. Bearer token authentication (mandatory)
  2. IP-based rate limiting (anti brute-force)
  3. Request logging for audit trail
  4. Health endpoint is public (no auth) for uptime checks
  5. All other endpoints require valid Bearer token
"""

import json
import os
import subprocess
import re
import time
import hashlib
import hmac
from datetime import datetime, timezone
from functools import wraps
from collections import defaultdict
from flask import Flask, jsonify, request, g
from flask_cors import CORS

app = Flask(__name__)
CORS(app, origins=["http://localhost:5555"])  # Only allow dashboard origin

# ── Configuration ────────────────────────────────────────────────────────────
AUTH_TOKEN = os.getenv("AUTH_TOKEN", "")
RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", "60"))  # seconds
RATE_LIMIT_MAX = int(os.getenv("RATE_LIMIT_MAX", "30"))        # requests per window
LOG_ACCESS = os.getenv("LOG_ACCESS", "true").lower() == "true"

# ── Rate Limiter (in-memory, per IP) ─────────────────────────────────────────
class RateLimiter:
    def __init__(self, window=RATE_LIMIT_WINDOW, max_requests=RATE_LIMIT_MAX):
        self.window = window
        self.max_requests = max_requests
        self.requests = defaultdict(list)  # ip -> [timestamps]

    def is_allowed(self, ip):
        now = time.time()
        # Clean old entries
        self.requests[ip] = [t for t in self.requests[ip] if now - t < self.window]
        if len(self.requests[ip]) >= self.max_requests:
            return False
        self.requests[ip].append(now)
        return True

    def remaining(self, ip):
        now = time.time()
        active = [t for t in self.requests[ip] if now - t < self.window]
        return max(0, self.max_requests - len(active))

rate_limiter = RateLimiter()


def get_real_ip():
    """Get real client IP behind Traefik reverse proxy"""
    forwarded = request.headers.get('X-Forwarded-For', '')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.remote_addr or 'unknown'


def log_access(ip, path, status_code, reason=""):
    """Log access attempts for security audit"""
    if not LOG_ACCESS:
        return
    ts = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    user_agent = request.headers.get('User-Agent', '-')[:50]
    log_line = f"[{ts}] {ip} {request.method} {path} -> {status_code}"
    if reason:
        log_line += f" ({reason})"
    log_line += f" UA={user_agent}"
    print(log_line, flush=True)


def require_auth(f):
    """Decorator: require valid Bearer token for endpoint"""
    @wraps(f)
    def decorated(*args, **kwargs):
        ip = get_real_ip()
        path = request.path

        # Rate limit check
        if not rate_limiter.is_allowed(ip):
            log_access(ip, path, 429, "rate-limited")
            return jsonify({
                "error": "Rate limit exceeded",
                "retry_after": RATE_LIMIT_WINDOW
            }), 429

        # Auth check
        auth_header = request.headers.get('Authorization', '')
        token = ''
        if auth_header.startswith('Bearer '):
            token = auth_header[7:]
        elif request.args.get('token'):
            token = request.args.get('token')

        if not AUTH_TOKEN:
            log_access(ip, path, 500, "AUTH_TOKEN not configured")
            return jsonify({"error": "Server misconfiguration: AUTH_TOKEN not set"}), 500

        if not token or not hmac.compare_digest(token, AUTH_TOKEN):
            log_access(ip, path, 401, "invalid-token")
            # Don't reveal whether token was missing vs wrong
            return jsonify({"error": "Unauthorized"}), 401

        # Store IP for logging
        g.client_ip = ip
        log_access(ip, path, 200, "authenticated")
        return f(*args, **kwargs)
    return decorated


# ── Docker Stats Parsing ─────────────────────────────────────────────────────

def parse_docker_stats():
    """Get container stats via docker stats --no-stream"""
    try:
        result = subprocess.run(
            ["docker", "stats", "--no-stream", "--format",
             '{"name":"{{.Name}}","cpu":"{{.CPUPerc}}","mem_usage":"{{.MemUsage}}","mem_perc":"{{.MemPerc}}","net_io":"{{.NetIO}}","block_io":"{{.BlockIO}}","pids":"{{.PIDs}}"}'],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode != 0:
            return None, f"docker stats failed: {result.stderr}"

        containers = []
        for line in result.stdout.strip().split('\n'):
            if line.strip():
                try:
                    data = json.loads(line)
                    cpu_str = data.get('cpu', '0%').replace('%', '')
                    data['cpu_percent'] = float(cpu_str) if cpu_str else 0.0
                    mem_perc_str = data.get('mem_perc', '0%').replace('%', '')
                    data['mem_percent'] = float(mem_perc_str) if mem_perc_str else 0.0
                    mem_parts = data.get('mem_usage', ' / ').split(' / ')
                    data['mem_used'] = mem_parts[0].strip() if len(mem_parts) > 0 else '0'
                    data['mem_limit'] = mem_parts[1].strip() if len(mem_parts) > 1 else '0'
                    net_parts = data.get('net_io', ' / ').split(' / ')
                    data['net_in'] = net_parts[0].strip() if len(net_parts) > 0 else '0'
                    data['net_out'] = net_parts[1].strip() if len(net_parts) > 1 else '0'
                    block_parts = data.get('block_io', ' / ').split(' / ')
                    data['block_read'] = block_parts[0].strip() if len(block_parts) > 0 else '0'
                    data['block_write'] = block_parts[1].strip() if len(block_parts) > 1 else '0'
                    containers.append(data)
                except json.JSONDecodeError:
                    continue
        return containers, None
    except subprocess.TimeoutExpired:
        return None, "docker stats timed out"
    except FileNotFoundError:
        return None, "docker command not found"
    except Exception as e:
        return None, str(e)


def parse_docker_ps():
    """Get container list with status"""
    try:
        result = subprocess.run(
            ["docker", "ps", "-a", "--format",
             '{"id":"{{.ID}}","name":"{{.Names}}","image":"{{.Image}}","status":"{{.Status}}","ports":"{{.Ports}}","state":"{{.State}}"}'],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            return None, f"docker ps failed: {result.stderr}"

        containers = []
        for line in result.stdout.strip().split('\n'):
            if line.strip():
                try:
                    containers.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return containers, None
    except Exception as e:
        return None, str(e)


def parse_docker_top(container_name):
    """Get running processes inside a container via docker top"""
    try:
        result = subprocess.run(
            ["docker", "top", container_name, "-eo", "pid,user,%cpu,%mem,vsz,rss,tty,stat,start,time,command"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            return None, f"docker top failed: {result.stderr.strip()}"

        lines = result.stdout.strip().split('\n')
        if len(lines) < 2:
            return [], None

        # Parse header
        header_line = lines[0]
        processes = []
        for line in lines[1:]:
            parts = line.split(None, 10)
            if len(parts) >= 11:
                processes.append({
                    "pid": parts[0],
                    "user": parts[1],
                    "cpu": parts[2],
                    "mem": parts[3],
                    "vsz": parts[4],
                    "rss": parts[5],
                    "tty": parts[6],
                    "stat": parts[7],
                    "start": parts[8],
                    "time": parts[9],
                    "command": parts[10]
                })
            elif len(parts) >= 1:
                # Fallback: treat rest as command
                processes.append({"command": line.strip()})

        return processes, None
    except subprocess.TimeoutExpired:
        return None, "docker top timed out"
    except FileNotFoundError:
        return None, "docker command not found"
    except Exception as e:
        return None, str(e)


def parse_docker_inspect(container_name):
    """Get full container inspect details"""
    try:
        result = subprocess.run(
            ["docker", "inspect", container_name],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            return None, f"docker inspect failed: {result.stderr.strip()}"
        data = json.loads(result.stdout)
        if not data:
            return None, "no data returned"
        return data[0], None
    except json.JSONDecodeError:
        return None, "failed to parse docker inspect output"
    except subprocess.TimeoutExpired:
        return None, "docker inspect timed out"
    except Exception as e:
        return None, str(e)


def parse_docker_logs(container_name, lines=100):
    """Get container logs"""
    try:
        result = subprocess.run(
            ["docker", "logs", "--tail", str(lines), "--timestamps", container_name],
            capture_output=True, text=True, timeout=15
        )
        # docker logs outputs to stderr for some containers
        output = result.stdout or result.stderr
        if result.returncode != 0 and not output:
            return None, f"docker logs failed: {result.stderr.strip()}"
        return output.strip().split('\n') if output.strip() else [], None
    except subprocess.TimeoutExpired:
        return None, "docker logs timed out"
    except Exception as e:
        return None, str(e)


def get_server_info():
    """Get basic server resource info"""
    info = {}
    try:
        result = subprocess.run(["nproc"], capture_output=True, text=True, timeout=5)
        info['cpu_cores'] = int(result.stdout.strip()) if result.returncode == 0 else 0
    except:
        info['cpu_cores'] = 0

    try:
        result = subprocess.run(["free", "-b"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            if len(lines) >= 2:
                parts = lines[1].split()
                info['mem_total'] = int(parts[1]) if len(parts) > 1 else 0
                info['mem_used'] = int(parts[2]) if len(parts) > 2 else 0
                info['mem_free'] = int(parts[3]) if len(parts) > 3 else 0
    except:
        pass

    try:
        result = subprocess.run(["df", "-B1", "/"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            if len(lines) >= 2:
                parts = lines[1].split()
                info['disk_total'] = int(parts[1]) if len(parts) > 1 else 0
                info['disk_used'] = int(parts[2]) if len(parts) > 2 else 0
                info['disk_free'] = int(parts[3]) if len(parts) > 3 else 0
    except:
        pass

    try:
        with open('/proc/loadavg', 'r') as f:
            parts = f.read().strip().split()
            info['load_1m'] = float(parts[0])
            info['load_5m'] = float(parts[1])
            info['load_15m'] = float(parts[2])
    except:
        pass

    info['timestamp'] = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    return info


# ── API Endpoints ────────────────────────────────────────────────────────────

@app.before_request
def before_request_handler():
    """Log all incoming requests"""
    g.request_start = time.time()


@app.after_request
def after_request_handler(response):
    """Add security headers to all responses"""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    return response


@app.route('/health')
def health():
    """Public health check - no auth required"""
    return jsonify({
        "status": "ok",
        "agent": "coolify-monitor-agent",
        "version": "2.0.0-secured",
        "auth_required": bool(AUTH_TOKEN)
    })


@app.route('/api/stats')
@require_auth
def api_stats():
    """Get all container stats"""
    stats, err = parse_docker_stats()
    if err:
        return jsonify({"error": err}), 500
    return jsonify({
        "ok": True,
        "containers": stats,
        "count": len(stats),
        "timestamp": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    })


@app.route('/api/containers')
@require_auth
def api_containers():
    """Get container list"""
    containers, err = parse_docker_ps()
    if err:
        return jsonify({"error": err}), 500
    return jsonify({
        "ok": True,
        "containers": containers,
        "count": len(containers),
        "timestamp": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    })


@app.route('/api/server')
@require_auth
def api_server():
    """Get server resource info"""
    info = get_server_info()
    return jsonify({"ok": True, "server": info})


@app.route('/api/all')
@require_auth
def api_all():
    """Get everything: server info + container stats + container list"""
    stats, stats_err = parse_docker_stats()
    containers, ps_err = parse_docker_ps()
    server = get_server_info()
    return jsonify({
        "ok": True,
        "server": server,
        "containers": containers or [],
        "stats": stats or [],
        "errors": {
            "stats": stats_err,
            "containers": ps_err
        },
        "timestamp": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    })


@app.route('/api/container/<name>/top')
@require_auth
def api_container_top(name):
    """Get running processes inside a container"""
    processes, err = parse_docker_top(name)
    if err:
        return jsonify({"error": err}), 500
    return jsonify({
        "ok": True,
        "container": name,
        "processes": processes,
        "count": len(processes) if processes else 0,
        "timestamp": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    })


@app.route('/api/container/<name>/inspect')
@require_auth
def api_container_inspect(name):
    """Get full container inspect details (filtered for readability)"""
    data, err = parse_docker_inspect(name)
    if err:
        return jsonify({"error": err}), 500

    # Filter to useful fields only
    filtered = {
        "id": data.get("Id", "")[:12],
        "name": data.get("Name", "").lstrip("/"),
        "image": data.get("Config", {}).get("Image", ""),
        "created": data.get("Created", ""),
        "state": data.get("State", {}),
        "restart_policy": data.get("HostConfig", {}).get("RestartPolicy", {}),
        "ports": data.get("NetworkSettings", {}).get("Ports", {}),
        "env_count": len(data.get("Config", {}).get("Env", [])),
        "mounts": [
            {"source": m.get("Source", ""), "dest": m.get("Destination", ""), "mode": m.get("Mode", "")}
            for m in data.get("Mounts", [])
        ],
        "cmd": data.get("Config", {}).get("Cmd", []),
        "entrypoint": data.get("Config", {}).get("Entrypoint", []),
        "labels": {k: v for k, v in data.get("Config", {}).get("Labels", {}).items()
                   if k.startswith("coolify") or k.startswith("com.docker")},
        "networks": list(data.get("NetworkSettings", {}).get("Networks", {}).keys()),
        "healthcheck": data.get("Config", {}).get("Healthcheck"),
    }
    return jsonify({"ok": True, "container": name, "inspect": filtered})


@app.route('/api/container/<name>/logs')
@require_auth
def api_container_logs(name):
    """Get container logs"""
    lines_req = request.args.get('lines', 100, type=int)
    logs, err = parse_docker_logs(name, lines_req)
    if err:
        return jsonify({"error": err}), 500
    return jsonify({
        "ok": True,
        "container": name,
        "logs": logs,
        "count": len(logs) if logs else 0,
    })


@app.errorhandler(404)
def not_found(e):
    """Return JSON for 404"""
    ip = get_real_ip()
    log_access(ip, request.path, 404, "not-found")
    return jsonify({"error": "Not found"}), 404


@app.errorhandler(405)
def method_not_allowed(e):
    """Return JSON for 405"""
    return jsonify({"error": "Method not allowed"}), 405


if __name__ == '__main__':
    port = int(os.getenv("PORT", "9999"))
    print(f"\n  Coolify Monitor Agent v2.0 (Secured)")
    print(f"  Port: {port}")
    print(f"  Auth: {'ENABLED' if AUTH_TOKEN else 'DISABLED (set AUTH_TOKEN!)'}")
    print(f"  Rate limit: {RATE_LIMIT_MAX} req/{RATE_LIMIT_WINDOW}s per IP")
    print(f"  Access log: {'ON' if LOG_ACCESS else 'OFF'}\n")
    app.run(host='0.0.0.0', port=port, debug=False)
