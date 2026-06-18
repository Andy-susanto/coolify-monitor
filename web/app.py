#!/usr/bin/env python3
"""
Coolify Monitor — Web UI Dashboard
Flask backend that proxies Coolify API and serves a monitoring dashboard.
"""

import os
import sys
import json
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import paths
from dotenv import load_dotenv
load_dotenv(paths.ensure_env())

from functools import wraps
from flask import Flask, render_template, jsonify, request, session, redirect, url_for
from coolify_client import CoolifyClient

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "change-me-in-production")

COOLIFY_URL = os.getenv("COOLIFY_URL", "http://localhost:8000")
COOLIFY_API_KEY = os.getenv("COOLIFY_API_KEY", "")
WEB_PORT = int(os.getenv("WEB_PORT", "5555"))
REFRESH_INTERVAL = int(os.getenv("REFRESH_INTERVAL", "5"))
AGENT_URL = os.getenv("MONITOR_AGENT_URL", "")
AGENT_TOKEN = os.getenv("MONITOR_AGENT_TOKEN", "")
MONITOR_PASSWORD = os.getenv("MONITOR_PASSWORD", "")

# Uptime tracking poller interval (seconds)
UPTIME_POLL_INTERVAL = int(os.getenv("UPTIME_POLL_INTERVAL", "60"))

from uptime_tracker import get_tracker

# Cache for container → project mapping (avoid hammering Coolify API)
_project_map_cache = {"map": None, "ts": 0}
PROJECT_MAP_TTL = 300  # 5 minutes


def get_client():
    return CoolifyClient(COOLIFY_URL, COOLIFY_API_KEY)


def login_required(f):
    """Decorator: redirect to login if not authenticated."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if MONITOR_PASSWORD and not session.get("authenticated"):
            if request.is_json or request.path.startswith("/api/"):
                return jsonify({"ok": False, "error": "Unauthorized"}), 401
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


# ─── Auth ─────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login():
    if not MONITOR_PASSWORD:
        return redirect(url_for("index"))
    error = None
    if request.method == "POST":
        password = request.form.get("password", "")
        if password == MONITOR_PASSWORD:
            session["authenticated"] = True
            return redirect(url_for("index"))
        error = "Password salah. Silakan coba lagi."
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ─── Pages ────────────────────────────────────────

@app.route("/")
@login_required
def index():
    return render_template("index.html", refresh_interval=REFRESH_INTERVAL)

def get_cached_project_map():
    """Get container→project mapping with 5-min cache"""
    import time
    now = time.time()
    if _project_map_cache["map"] is not None and now - _project_map_cache["ts"] < PROJECT_MAP_TTL:
        return _project_map_cache["map"]
    try:
        client = get_client()
        mapping = client.get_container_project_map()
        _project_map_cache["map"] = mapping
        _project_map_cache["ts"] = now
        return mapping
    except Exception:
        return _project_map_cache["map"] or {}


# ─── API: Status ──────────────────────────────────

@app.route("/api/status")
@login_required
def api_status():
    try:
        client = get_client()
        data = client.get_all_status()
        data["ok"] = True
        data["ts"] = datetime.now().isoformat()
        return jsonify(data)
    except ConnectionError as e:
        return jsonify({"ok": False, "error": str(e)}), 502
    except PermissionError as e:
        return jsonify({"ok": False, "error": str(e)}), 401
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ─── API: Logs ────────────────────────────────────

@app.route("/api/logs/<uuid>")
@login_required
def api_logs(uuid):
    try:
        client = get_client()
        lines = request.args.get("lines", 200, type=int)
        logs = client.get_application_logs(uuid, lines)
        if isinstance(logs, dict):
            logs = logs.get("logs", logs.get("data", json.dumps(logs, indent=2)))
        return jsonify({"ok": True, "logs": str(logs)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ─── API: Health ──────────────────────────────────

@app.route("/api/health")
@login_required
def api_health():
    try:
        client = get_client()
        result = client.health()
        return jsonify({"ok": True, "data": result})
    except ConnectionError as e:
        return jsonify({"ok": False, "error": str(e)}), 502
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ─── API: Actions ─────────────────────────────────

def _do_action(resource_type, uuid, action):
    import requests as req
    url = f"{COOLIFY_URL}/api/v1/{resource_type}/{uuid}/{action}"
    headers = {
        "Authorization": f"Bearer {COOLIFY_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    try:
        resp = req.post(url, headers=headers, timeout=15)
        data = resp.json() if resp.text else {}
        return {
            "ok": resp.status_code in (200, 201),
            "status": resp.status_code,
            "message": data.get("message", resp.text[:200] if resp.text else "No response"),
            "deployment_uuid": data.get("deployment_uuid"),
        }
    except req.exceptions.ConnectionError:
        return {"ok": False, "error": f"Cannot connect to {COOLIFY_URL}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.route("/api/app/<uuid>/start", methods=["POST"])
@login_required
def app_start(uuid):
    result = _do_action("applications", uuid, "start")
    return jsonify(result), (200 if result.get("ok") else 500)


@app.route("/api/app/<uuid>/stop", methods=["POST"])
@login_required
def app_stop(uuid):
    result = _do_action("applications", uuid, "stop")
    return jsonify(result), (200 if result.get("ok") else 500)


@app.route("/api/app/<uuid>/restart", methods=["POST"])
@login_required
def app_restart(uuid):
    result = _do_action("applications", uuid, "restart")
    return jsonify(result), (200 if result.get("ok") else 500)


@app.route("/api/service/<uuid>/start", methods=["POST"])
@login_required
def svc_start(uuid):
    result = _do_action("services", uuid, "start")
    return jsonify(result), (200 if result.get("ok") else 500)


@app.route("/api/service/<uuid>/stop", methods=["POST"])
@login_required
def svc_stop(uuid):
    result = _do_action("services", uuid, "stop")
    return jsonify(result), (200 if result.get("ok") else 500)


@app.route("/api/service/<uuid>/restart", methods=["POST"])
@login_required
def svc_restart(uuid):
    result = _do_action("services", uuid, "restart")
    return jsonify(result), (200 if result.get("ok") else 500)


@app.route("/api/db/<uuid>/start", methods=["POST"])
@login_required
def db_start(uuid):
    result = _do_action("databases", uuid, "start")
    return jsonify(result), (200 if result.get("ok") else 500)


@app.route("/api/db/<uuid>/stop", methods=["POST"])
@login_required
def db_stop(uuid):
    result = _do_action("databases", uuid, "stop")
    return jsonify(result), (200 if result.get("ok") else 500)


@app.route("/api/db/<uuid>/restart", methods=["POST"])
@login_required
def db_restart(uuid):
    result = _do_action("databases", uuid, "restart")
    return jsonify(result), (200 if result.get("ok") else 500)


# ─── API: Container Detail (via agent) ───────────

def _agent_request(path, params=None):
    """Proxy a request to the monitor agent"""
    if not AGENT_URL:
        return {"ok": False, "error": "MONITOR_AGENT_URL not configured"}, 503
    import requests as req
    try:
        headers = {}
        if AGENT_TOKEN:
            headers["Authorization"] = f"Bearer {AGENT_TOKEN}"
        resp = req.get(f"{AGENT_URL}{path}", headers=headers, params=params, timeout=15)
        data = resp.json()
        return data, resp.status_code
    except req.exceptions.ConnectionError:
        return {"ok": False, "error": f"Cannot connect to agent at {AGENT_URL}"}, 502
    except Exception as e:
        return {"ok": False, "error": str(e)}, 500


def _resolve_container_name(uuid):
    """Resolve a Coolify UUID to the actual Docker container name via agent"""
    data, status = _agent_request("/api/containers")
    if not data.get("ok"):
        return None
    for c in data.get("containers", []):
        cname = c.get("name", "")
        if uuid in cname:
            return cname  # Return the FULL container name (e.g. "uuid-073447624806")
    return None


@app.route("/api/container/<uuid>/detail")
@login_required
def api_container_detail(uuid):
    """Get full container detail: config from Coolify API + processes from agent + logs from Coolify API"""
    result = {
        "ok": True,
        "uuid": uuid,
        "container_name": "",
        "processes": [],
        "processes_error": None,
        "inspect": {},
        "inspect_error": None,
        "logs": [],
        "logs_error": None,
    }

    # 1. Get application/service details from Coolify API
    client = get_client()
    app_data = None
    resource_type = None

    for endpoint in ["applications", "services", "databases"]:
        try:
            items = client._ensure_list(client._get(f"/{endpoint}"))
            for item in items:
                if item.get("uuid") == uuid:
                    try:
                        app_data = client._get(f"/{endpoint}/{uuid}")
                        resource_type = endpoint.rstrip("s")
                        break
                    except Exception:
                        app_data = item
                        resource_type = endpoint.rstrip("s")
                    break
            if app_data:
                break
        except Exception:
            continue

    if app_data:
        result["container_name"] = app_data.get("name", "")
        result["inspect"] = {
            "name": app_data.get("name", ""),
            "image": app_data.get("image", app_data.get("docker_image", "")),
            "created": app_data.get("created_at", ""),
            "resource_type": resource_type,
            "status": app_data.get("status", ""),
            "fqdn": app_data.get("fqdn", ""),
            "git_repository": app_data.get("git_repository", ""),
            "git_branch": app_data.get("git_branch", ""),
            "build_pack": app_data.get("build_pack", ""),
            "ports": app_data.get("ports_mappings", []),
            "env_count": len(app_data.get("environment_variables", [])),
            "limits": {
                "memory": app_data.get("limits_memory", ""),
                "memory_swap": app_data.get("limits_memory_swap", ""),
                "memory_swappiness": app_data.get("limits_memory_swappiness", ""),
                "cpu": app_data.get("limits_cpu", ""),
                "cpus": app_data.get("limits_cpus", ""),
            },
            "healthcheck": app_data.get("health_check", {}),
            "restart_policy": app_data.get("restart_policy", ""),
            "custom_labels": app_data.get("custom_labels", ""),
            "networks": app_data.get("networks", []),
        }

    # 2. Get logs from Coolify API
    try:
        logs = client.get_application_logs(uuid, 200)
        if isinstance(logs, dict):
            logs = logs.get("logs", logs.get("data", ""))
        if isinstance(logs, str):
            result["logs"] = logs.strip().split("\n") if logs.strip() else []
        elif isinstance(logs, list):
            result["logs"] = logs
    except Exception as e:
        result["logs_error"] = str(e)

    # 3. Try to get process info from monitor agent (container resolution)
    if AGENT_URL:
        try:
            import requests as req
            headers = {}
            if AGENT_TOKEN:
                headers["Authorization"] = f"Bearer {AGENT_TOKEN}"
            # Get container list from agent to find Docker name
            resp = req.get(f"{AGENT_URL}/api/containers", headers=headers, timeout=10)
            if resp.status_code == 200:
                containers = resp.json().get("containers", [])
                for c in containers:
                    cname = c.get("name", "")
                    if uuid in cname:
                        result["container_name"] = cname
                        # Get process list
                        try:
                            top_resp = req.get(f"{AGENT_URL}/api/container/{cname}/top", headers=headers, timeout=10)
                            if top_resp.status_code == 200:
                                top_data = top_resp.json()
                                result["processes"] = top_data.get("processes", [])
                        except Exception:
                            pass
                        break
        except Exception:
            pass

    return jsonify(result)


@app.route("/api/container/<name>/top")
def api_container_top(name):
    """Proxy: get container processes from agent"""
    data, status = _agent_request(f"/api/container/{name}/top")
    return jsonify(data), status


@app.route("/api/container/<name>/inspect")
@login_required
def api_container_inspect(name):
    """Proxy: get container inspect from agent"""
    data, status = _agent_request(f"/api/container/{name}/inspect")
    return jsonify(data), status


@app.route("/api/container/<name>/logs")
def api_container_logs(name):
    """Proxy: get container logs from agent"""
    lines = request.args.get("lines", 100, type=int)
    data, status = _agent_request(f"/api/container/{name}/logs", {"lines": lines})
    return jsonify(data), status


# ─── API: Resources (existing) ───────────────────

@app.route("/api/resources")
@login_required
def api_resources():
    """Fetch container resource stats from the monitoring agent, enriched with project labels."""
    if not AGENT_URL:
        return jsonify({"ok": False, "error": "MONITOR_AGENT_URL not configured. Deploy monitor-agent first."}), 503

    import requests as req
    try:
        headers = {}
        if AGENT_TOKEN:
            headers["Authorization"] = f"Bearer {AGENT_TOKEN}"
        resp = req.get(f"{AGENT_URL}/api/all", headers=headers, timeout=10)
        data = resp.json()

        # Build container name → project label mapping from Coolify (cached)
        try:
            uuid_map = get_cached_project_map()

            # Enrich each container in stats with project info
            for container in data.get("stats", []):
                cname = container.get("name", "")
                matched = False
                for uuid, info in uuid_map.items():
                    if uuid in cname:
                        container["label"] = info["name"]
                        container["project"] = info["project"]
                        container["env"] = info["env"]
                        container["resource_type"] = info["type"]
                        matched = True
                        break
                if not matched:
                    # System containers (coolify, proxy, etc.)
                    container["label"] = cname
                    container["project"] = ""
                    container["env"] = ""
                    container["resource_type"] = "system"
        except Exception:
            # If mapping fails, still return the data without labels
            for container in data.get("stats", []):
                container.setdefault("label", container.get("name", ""))
                container.setdefault("project", "")
                container.setdefault("env", "")
                container.setdefault("resource_type", "unknown")

        return jsonify(data)
    except req.exceptions.ConnectionError:
        return jsonify({"ok": False, "error": f"Cannot connect to agent at {AGENT_URL}"}), 502
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ─── API: Uptime Tracking ────────────────────────

def _collect_status_snapshot():
    """Fetch current status of all resources for uptime recording."""
    client = get_client()
    snapshot = []
    try:
        for app_item in client.get_applications():
            snapshot.append({
                "uuid": app_item.get("uuid"),
                "name": app_item.get("name", ""),
                "type": "application",
                "status": app_item.get("status", ""),
            })
    except Exception:
        pass
    try:
        for svc in client.get_services():
            snapshot.append({
                "uuid": svc.get("uuid"),
                "name": svc.get("name", ""),
                "type": "service",
                "status": svc.get("status", ""),
            })
    except Exception:
        pass
    try:
        for db in client.get_databases():
            snapshot.append({
                "uuid": db.get("uuid"),
                "name": db.get("name", ""),
                "type": "database",
                "status": db.get("status", ""),
            })
    except Exception:
        pass
    return snapshot


def _uptime_poller():
    """Background thread: record status snapshots at a fixed interval."""
    import time as _time
    tracker = get_tracker()
    prune_counter = 0
    while True:
        try:
            snapshot = _collect_status_snapshot()
            if snapshot:
                tracker.record_snapshot(snapshot)
            prune_counter += 1
            # Prune old events roughly once per day
            if prune_counter * UPTIME_POLL_INTERVAL >= 86400:
                tracker.prune(keep_days=90)
                prune_counter = 0
        except Exception as e:
            print(f"[uptime] poll error: {e}", flush=True)
        _time.sleep(UPTIME_POLL_INTERVAL)


def _start_uptime_poller():
    import threading
    t = threading.Thread(target=_uptime_poller, daemon=True, name="uptime-poller")
    t.start()
    return t


@app.route("/api/uptime")
@login_required
def api_uptime():
    """Return uptime stats for all resources over a window (hours param)."""
    hours = request.args.get("hours", 24, type=float)
    try:
        tracker = get_tracker()
        data = tracker.get_uptime(window_hours=hours)
        return jsonify({"ok": True, "window_hours": hours, "resources": data,
                        "ts": datetime.now().isoformat()})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/uptime/<uuid>/events")
@login_required
def api_uptime_events(uuid):
    """Return recent up/down transition events for one resource."""
    limit = request.args.get("limit", 50, type=int)
    try:
        tracker = get_tracker()
        events = tracker.get_events(uuid, limit=limit)
        return jsonify({"ok": True, "uuid": uuid, "events": events})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


def run_server(host="127.0.0.1", port=None):
    """Jalankan web server (dipakai standalone & in-process oleh tray app)."""
    _start_uptime_poller()
    app.run(host=host, port=port or WEB_PORT, debug=False, use_reloader=False, threaded=True)


if __name__ == "__main__":
    print(f"\n  Coolify Monitor Web UI")
    print(f"  ──────────────────────────")
    print(f"  Coolify  : {COOLIFY_URL}")
    print(f"  Dashboard: http://localhost:{WEB_PORT}")
    print(f"  Agent    : {AGENT_URL or 'not configured'}")
    print(f"  Refresh  : {REFRESH_INTERVAL}s")
    print(f"  Uptime   : polling every {UPTIME_POLL_INTERVAL}s\n")
    run_server(host="0.0.0.0")
