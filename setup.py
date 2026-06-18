#!/usr/bin/env python3
"""
py2app build script untuk Coolify Monitor (macOS menu bar app).

Build:
    ./venv/bin/python3 setup.py py2app

Hasil: dist/Coolify Monitor.app
"""

import sys
from setuptools import setup

APP = ["tray_app.py"]

DATA_FILES = [
    ("assets", ["assets/coolify.png"]),
    ("web/templates", ["web/templates/index.html", "web/templates/login.html"]),
    ("web/static", ["web/static/app.js", "web/static/style.css"]),
    (".", [".env.example"]),
]

OPTIONS = {
    "argv_emulation": False,
    "iconfile": "assets/coolify.icns",
    "plist": {
        "CFBundleName": "Coolify Monitor",
        "CFBundleDisplayName": "Coolify Monitor",
        "CFBundleIdentifier": "io.coolify.monitor.tray",
        "CFBundleShortVersionString": "1.0.0",
        "CFBundleVersion": "1.0.0",
        # LSUIElement=1 => agent app (hanya menu bar, tanpa ikon Dock)
        "LSUIElement": True,
        "NSHumanReadableCopyright": "Coolify Monitor",
    },
    "packages": ["rumps", "flask", "jinja2", "werkzeug", "click",
                 "markupsafe", "itsdangerous", "blinker", "dotenv",
                 "certifi", "charset_normalizer", "idna", "urllib3", "requests"],
    "includes": ["paths", "background_monitor", "uptime_tracker",
                 "coolify_client", "web", "web.app"],
}

setup(
    app=APP,
    name="Coolify Monitor",
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
