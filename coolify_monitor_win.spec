# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec untuk Coolify Monitor (Windows).

Build (di mesin Windows / CI):
    pyinstaller coolify_monitor_win.spec

Hasil: dist/CoolifyMonitor.exe (windowed, single-file)
"""

block_cipher = None

datas = [
    ("assets/coolify.png", "assets"),
    ("assets/coolify.ico", "assets"),
    ("web/templates/index.html", "web/templates"),
    ("web/templates/login.html", "web/templates"),
    ("web/static/app.js", "web/static"),
    ("web/static/style.css", "web/static"),
    (".env.example", "."),
]

hiddenimports = [
    "paths",
    "background_monitor",
    "uptime_tracker",
    "coolify_client",
    "web",
    "web.app",
    "flask",
    "jinja2",
    "werkzeug",
    "dotenv",
    "requests",
    "pystray._win32",
    "PIL.Image",
]

a = Analysis(
    ["tray_app_win.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["rumps", "AppKit", "Foundation", "objc"],
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="CoolifyMonitor",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    runtime_tmpdir=None,
    console=False,            # windowed app (tanpa console)
    icon="assets/coolify.ico",
)
