#!/usr/bin/env python3
"""
Coolify API Client
Handles all communication with Coolify's REST API v1.
"""

import requests
import json
import urllib3
from typing import Optional

# Suppress SSL warnings for self-signed certs
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class CoolifyClient:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.session = requests.Session()
        self.session.verify = False  # Allow self-signed certs (Coolify default)
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        })

    def _get(self, endpoint: str, params: dict = None) -> any:
        url = f"{self.base_url}/api/v1{endpoint}"
        try:
            resp = self.session.get(url, params=params, timeout=15)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.ConnectionError:
            raise ConnectionError(f"Cannot connect to Coolify at {self.base_url}. Is it running?")
        except requests.exceptions.HTTPError as e:
            if resp.status_code == 401:
                raise PermissionError("API key is invalid or expired. Check COOLIFY_API_KEY in .env")
            if resp.status_code == 404:
                raise ValueError(f"Endpoint not found: {endpoint}. Your Coolify version might not support this API.")
            raise Exception(f"HTTP {resp.status_code}: {resp.text}")
        except requests.exceptions.Timeout:
            raise TimeoutError(f"Request to {url} timed out after 15s")

    def _ensure_list(self, data):
        """Normalize response to list"""
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("data", [data])
        return []

    # ─── Health ──────────────────────────────────

    def health(self) -> dict:
        """Check if Coolify API is healthy"""
        url = f"{self.base_url}/api/v1/health"
        try:
            resp = self.session.get(url, timeout=10)
            resp.raise_for_status()
            try:
                return resp.json()
            except Exception:
                return {"status": resp.text.strip()}
        except Exception:
            raise

    # ─── Servers ─────────────────────────────────

    def get_servers(self) -> list:
        return self._ensure_list(self._get("/servers"))

    def get_server(self, server_uuid: str) -> dict:
        return self._get(f"/servers/{server_uuid}")

    # ─── Projects ────────────────────────────────

    def get_projects(self) -> list:
        return self._ensure_list(self._get("/projects"))

    def get_project(self, project_uuid: str) -> dict:
        return self._get(f"/projects/{project_uuid}")

    # ─── Applications ────────────────────────────

    def get_applications(self) -> list:
        return self._ensure_list(self._get("/applications"))

    def get_application(self, app_uuid: str) -> dict:
        return self._get(f"/applications/{app_uuid}")

    # ─── Services ────────────────────────────────

    def get_services(self) -> list:
        return self._ensure_list(self._get("/services"))

    def get_service(self, service_uuid: str) -> dict:
        return self._get(f"/services/{service_uuid}")

    # ─── Databases ───────────────────────────────

    def get_databases(self) -> list:
        return self._ensure_list(self._get("/databases"))

    def get_database(self, db_uuid: str) -> dict:
        return self._get(f"/databases/{db_uuid}")

    # ─── Logs ────────────────────────────────────

    def get_application_logs(self, app_uuid: str, lines: int = 200) -> str:
        """Get application container logs"""
        return self._get(f"/applications/{app_uuid}/logs?lines={lines}")

    # ─── Deployments ─────────────────────────────

    def get_running_deployments(self) -> list:
        """Deployment yang sedang berjalan/antri (semua aplikasi)."""
        return self._ensure_list(self._get("/deployments"))

    def get_application_deployments(self, app_uuid: str, take: int = 10) -> list:
        """Riwayat deployment untuk satu aplikasi (terbaru lebih dulu)."""
        data = self._get(f"/deployments/applications/{app_uuid}?take={take}")
        if isinstance(data, dict):
            return data.get("deployments", [])
        if isinstance(data, list):
            return data
        return []


    # ─── Container → Project Mapping ─────────────

    def get_container_project_map(self) -> dict:
        """Build a mapping from container UUID prefix → project name.

        Returns dict like:
            {"j8ckw048k0cw8kc8ockswg4w": {"name": "API SIMPEG", "project": "SIMPEG UINJAMBI", "env": "production", "type": "application"}}
        """
        uuid_map = {}

        # Step 1: Build environment_id → project name mapping
        env_to_project = {}
        try:
            projects = self.get_projects()
            for proj in projects:
                try:
                    detail = self.get_project(proj["uuid"])
                    for env in detail.get("environments", []):
                        env_id = env.get("id")
                        if env_id:
                            env_to_project[env_id] = {
                                "project_name": proj["name"],
                                "project_uuid": proj["uuid"],
                                "env_name": env.get("name", "unknown"),
                            }
                except Exception:
                    continue
        except Exception:
            pass

        # Step 2: Map applications
        try:
            for app in self.get_applications():
                uuid = app.get("uuid", "")
                env_id = app.get("environment_id")
                proj_info = env_to_project.get(env_id, {})
                uuid_map[uuid] = {
                    "name": app.get("name", ""),
                    "project": proj_info.get("project_name", ""),
                    "env": proj_info.get("env_name", ""),
                    "type": "application",
                }
        except Exception:
            pass

        # Step 3: Map services (also using environment_id)
        try:
            for svc in self.get_services():
                uuid = svc.get("uuid", "")
                env_id = svc.get("environment_id")
                proj_info = env_to_project.get(env_id, {})
                uuid_map[uuid] = {
                    "name": svc.get("name", ""),
                    "project": proj_info.get("project_name", ""),
                    "env": proj_info.get("env_name", ""),
                    "type": "service",
                }
        except Exception:
            pass

        # Step 4: Map databases (also using environment_id)
        try:
            for db in self.get_databases():
                uuid = db.get("uuid", "")
                env_id = db.get("environment_id")
                proj_info = env_to_project.get(env_id, {})
                uuid_map[uuid] = {
                    "name": db.get("name", ""),
                    "project": proj_info.get("project_name", ""),
                    "env": proj_info.get("env_name", ""),
                    "type": "database",
                }
        except Exception:
            pass

        return uuid_map

    # ─── Convenience ─────────────────────────────

    def get_all_status(self) -> dict:
        """Fetch all resource data in parallel-friendly way"""
        servers = []
        projects = []
        applications = []
        services = []
        databases = []

        try:
            servers = self.get_servers()
        except Exception:
            pass

        try:
            projects = self.get_projects()
        except Exception:
            pass

        try:
            applications = self.get_applications()
        except Exception:
            pass

        try:
            services = self.get_services()
        except Exception:
            pass

        try:
            databases = self.get_databases()
        except Exception:
            pass

        return {
            "servers": servers,
            "projects": projects,
            "applications": applications,
            "services": services,
            "databases": databases,
        }
