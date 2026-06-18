#!/usr/bin/env python3
"""
Coolify Tray App (Windows) — system tray controller berbasis pystray.

Setara dengan tray_app.py (macOS/rumps) tapi untuk Windows. Menjalankan
monitor & web dashboard secara IN-PROCESS (thread).

Fitur menu:
- Status monitor (running/stopped)
- Start / Stop monitor
- Buka web dashboard
- Buka file log
- Settings: edit .env, toggle alert on recovery, ubah poll interval
- Toggle auto-start saat login (registry HKCU Run)
"""

import os
import sys
import threading
import time
import webbrowser
import subprocess
from pathlib import Path

import pystray
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))

import paths

RES_DIR = paths.resource_dir()
ENV_FILE = paths.ensure_env()
LOG_FILE = paths.log_dir() / "coolify_monitor.log"
ICON_PATH = RES_DIR / "assets" / "coolify.png"

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "CoolifyMonitor"

# ─── .env helpers ─────────────────────────────────────────────────

def _read_env_value(key: str, default: str = "") -> str:
    if not ENV_FILE.exists():
        return default
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip()
    return default

def _set_env_value(key: str, value: str):
    lines = ENV_FILE.read_text().splitlines() if ENV_FILE.exists() else []
    found = False
    for i, line in enumerate(lines):
        if line.strip().startswith(f"{key}="):
            lines[i] = f"{key}={value}"
            found = True
            break
    if not found:
        lines.append(f"{key}={value}")
    ENV_FILE.write_text("\n".join(lines) + "\n")
    os.environ[key] = value

# ─── Auto-start (registry HKCU Run) ───────────────────────────────

def _launch_command() -> str:
    if paths.is_frozen():
        return f'"{Path(sys.executable).resolve()}"'
    return f'"{sys.executable}" "{Path(__file__).resolve()}"'

def _autostart_installed() -> bool:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, RUN_NAME)
        return True
    except Exception:
        return False

def _autostart_set(enable: bool):
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if enable:
            winreg.SetValueEx(k, RUN_NAME, 0, winreg.REG_SZ, _launch_command())
        else:
            try:
                winreg.DeleteValue(k, RUN_NAME)
            except FileNotFoundError:
                pass

# ─── Tray controller ──────────────────────────────────────────────

class CoolifyTray:
    def __init__(self):
        self._monitor = None
        self._monitor_thread = None
        self._web_started = False
        self.icon = pystray.Icon(
            "CoolifyMonitor",
            self._load_image(),
            "Coolify Monitor",
            menu=self._build_menu(),
        )

    def _load_image(self):
        if ICON_PATH.exists():
            return Image.open(ICON_PATH)
        return Image.new("RGB", (64, 64), (133, 80, 252))

    # ─── State ────────────────────────────────────

    def _monitor_running(self) -> bool:
        return self._monitor_thread is not None and self._monitor_thread.is_alive()

    def _status_text(self, _):
        return "Status: Running" if self._monitor_running() else "Status: Stopped"

    def _toggle_text(self, _):
        return "Stop Monitor" if self._monitor_running() else "Start Monitor"

    def _alert_checked(self, _):
        return _read_env_value("ALERT_ON_RECOVERY", "true").lower() == "true"

    def _autostart_checked(self, _):
        return _autostart_installed()

    def _build_menu(self):
        return pystray.Menu(
            pystray.MenuItem(self._status_text, None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Buka Dashboard", self.open_dashboard),
            pystray.MenuItem("Buka File Log", self.open_log_file),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(self._toggle_text, self.toggle_monitor),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Settings", pystray.Menu(
                pystray.MenuItem("Edit .env", self.edit_env),
                pystray.MenuItem("Alert on Recovery", self.toggle_alert_recovery,
                                 checked=self._alert_checked),
            )),
            pystray.MenuItem("Auto-start saat Login", self.toggle_autostart,
                             checked=self._autostart_checked),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self.quit_app),
        )

    def _refresh(self):
        if self.icon:
            self.icon.update_menu()

    # ─── Monitor control ──────────────────────────

    def _config_ok(self) -> bool:
        url = _read_env_value("COOLIFY_URL")
        key = _read_env_value("COOLIFY_API_KEY")
        return bool(url) and bool(key) and key != "your-api-key-here"

    def toggle_monitor(self, icon, item):
        if self._monitor_running():
            self.stop_monitor()
            icon.notify("Monitor dihentikan.", "Coolify Monitor")
        else:
            if not self._config_ok():
                self.edit_env(icon, item)
                icon.notify("Set COOLIFY_URL & COOLIFY_API_KEY di .env dulu.", "Coolify Monitor")
                return
            self.start_monitor()
            icon.notify("Monitor dijalankan.", "Coolify Monitor")
        self._refresh()

    def start_monitor(self):
        from dotenv import load_dotenv
        load_dotenv(ENV_FILE, override=True)
        import background_monitor
        self._monitor = background_monitor.BackgroundMonitor()

        def _run():
            try:
                self._monitor.run()
            except Exception as e:
                if self.icon:
                    self.icon.notify(f"Monitor error: {str(e)[:80]}", "Coolify Monitor")

        self._monitor_thread = threading.Thread(target=_run, daemon=True, name="coolify-monitor")
        self._monitor_thread.start()

    def stop_monitor(self):
        if self._monitor:
            self._monitor.stop()
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)
        self._monitor = None
        self._monitor_thread = None

    # ─── Dashboard ────────────────────────────────

    def open_dashboard(self, icon, item):
        port = _read_env_value("WEB_PORT", "5555")
        if not self._web_started:
            from dotenv import load_dotenv
            load_dotenv(ENV_FILE, override=True)

            def _serve():
                try:
                    import importlib
                    web_app = importlib.import_module("web.app")
                    web_app.run_server(host="127.0.0.1", port=int(port))
                except Exception as e:
                    if self.icon:
                        self.icon.notify(f"Web server error: {str(e)[:80]}", "Coolify Monitor")

            t = threading.Thread(target=_serve, daemon=True, name="coolify-web")
            t.start()
            self._web_started = True
            time.sleep(2)
        webbrowser.open(f"http://localhost:{port}")

    # ─── Log & settings ───────────────────────────

    def open_log_file(self, icon, item):
        try:
            os.startfile(str(LOG_FILE))  # type: ignore[attr-defined]
        except Exception:
            subprocess.run(["notepad", str(LOG_FILE)])

    def edit_env(self, icon, item):
        try:
            os.startfile(str(ENV_FILE))  # type: ignore[attr-defined]
        except Exception:
            subprocess.run(["notepad", str(ENV_FILE)])

    def toggle_alert_recovery(self, icon, item):
        current = _read_env_value("ALERT_ON_RECOVERY", "true").lower() == "true"
        _set_env_value("ALERT_ON_RECOVERY", "false" if current else "true")
        icon.notify("Tersimpan. Restart monitor untuk menerapkan.", "Coolify Monitor")
        self._refresh()

    def toggle_autostart(self, icon, item):
        enable = not _autostart_installed()
        _autostart_set(enable)
        icon.notify(
            "Auto-start diaktifkan." if enable else "Auto-start dimatikan.",
            "Coolify Monitor",
        )
        self._refresh()

    # ─── Quit ─────────────────────────────────────

    def quit_app(self, icon, item):
        self.stop_monitor()
        icon.stop()

    def run(self):
        self.icon.run()


if __name__ == "__main__":
    CoolifyTray().run()
