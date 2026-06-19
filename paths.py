#!/usr/bin/env python3
"""
Resolusi path lintas-lingkungan: jalan sebagai script dev, atau di dalam
bundle .app (py2app) / .exe (PyInstaller).

- resource_dir(): lokasi resource read-only yang dibundel (assets, web/)
- config_dir():   direktori writable untuk .env, pid, db, log
"""

import os
import sys
from pathlib import Path

APP_NAME = "CoolifyMonitor"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def resource_dir() -> Path:
    """Lokasi file resource read-only (dibundel bersama aplikasi)."""
    if is_frozen():
        # PyInstaller onefile
        if hasattr(sys, "_MEIPASS"):
            return Path(sys._MEIPASS)
        # py2app: <App>.app/Contents/Resources
        return Path(sys.executable).resolve().parent.parent / "Resources"
    return Path(__file__).resolve().parent


def config_dir() -> Path:
    """Direktori writable untuk konfigurasi & data runtime."""
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / APP_NAME
    elif os.name == "nt":
        base = Path(os.getenv("APPDATA", str(Path.home()))) / APP_NAME
    else:
        base = Path.home() / ".config" / "coolify-monitor"
    base.mkdir(parents=True, exist_ok=True)
    return base


def log_dir() -> Path:
    if sys.platform == "darwin":
        d = Path.home() / "Library" / "Logs"
    else:
        d = config_dir() / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def env_file() -> Path:
    override = os.getenv("COOLIFY_ENV_FILE")
    if override:
        return Path(override)
    return config_dir() / ".env"


def pid_file() -> Path:
    return config_dir() / "monitor.pid"


def db_file() -> Path:
    return config_dir() / "uptime.db"


def ensure_env() -> Path:
    """Pastikan .env ada di config_dir; salin dari .env.example bila belum ada."""
    target = env_file()
    if not target.exists():
        example = resource_dir() / ".env.example"
        if example.exists():
            target.write_text(example.read_text())
        else:
            target.write_text("")
    return target

def read_env_value(key: str, default: str = "", env_path=None) -> str:
    """Baca satu nilai dari file .env (tanpa load_dotenv)."""
    target = Path(env_path) if env_path else env_file()
    if not target.exists():
        return default
    for line in target.read_text().splitlines():
        line = line.strip()
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip()
    return default

def set_env_value(key: str, value: str, env_path=None):
    """Tulis/ubah satu key di .env, lalu terapkan ke proses berjalan."""
    target = Path(env_path) if env_path else env_file()
    lines = target.read_text().splitlines() if target.exists() else []
    found = False
    for i, line in enumerate(lines):
        if line.strip().startswith(f"{key}="):
            lines[i] = f"{key}={value}"
            found = True
            break
    if not found:
        lines.append(f"{key}={value}")
    target.write_text("\n".join(lines) + "\n")
    os.environ[key] = value
