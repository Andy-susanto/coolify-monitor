#!/usr/bin/env python3
"""
Coolify Tray App — menu bar controller untuk Coolify Monitor (macOS).

Menjalankan monitor & web dashboard secara IN-PROCESS (thread), sehingga bisa
berjalan baik sebagai script dev maupun di dalam bundle .app (py2app) tanpa
butuh interpreter/skrip eksternal.

Fitur dropdown:
- Status monitor (running/stopped)
- Start / Stop monitor
- Buka web dashboard (start Flask in-process bila belum jalan)
- Lihat log terakhir
- Settings: edit .env, toggle alert on recovery, ubah poll interval
- Toggle auto-start saat login (LaunchAgent)
"""

import os
import sys
import threading
import subprocess
import time
import webbrowser
from pathlib import Path

import rumps

# Pastikan modul lokal bisa diimpor saat dijalankan dari bundle.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import paths

# ─── Path & konstanta ─────────────────────────────────────────────

RES_DIR = paths.resource_dir()
ENV_FILE = paths.ensure_env()
LOG_FILE = paths.log_dir() / "coolify_monitor.log"

ICON_PATH = str(RES_DIR / "assets" / "coolify.png")
DOT_RUNNING = "🟢"
DOT_STOPPED = "🔴"

TRAY_LABEL = "com.coolify.tray"
LAUNCH_AGENTS = Path.home() / "Library" / "LaunchAgents"
TRAY_PLIST_DST = LAUNCH_AGENTS / f"{TRAY_LABEL}.plist"

# ─── Helper: .env ─────────────────────────────────────────────────

def _read_env_value(key: str, default: str = "") -> str:
    return paths.read_env_value(key, default, ENV_FILE)

def _set_env_value(key: str, value: str):
    paths.set_env_value(key, value, ENV_FILE)

# ─── Helper: log & notifikasi ─────────────────────────────────────

def _tail(path: Path, n: int) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            tail = f.readlines()[-n:]
        return "".join(tail) or "(log kosong)"
    except FileNotFoundError:
        return "(file log belum ada)"

def notify(title: str, message: str):
    try:
        subprocess.run(
            ["osascript", "-e", f'display notification "{message}" with title "{title}"'],
            capture_output=True, timeout=10,
        )
    except Exception:
        pass

# ─── Helper: auto-start (LaunchAgent) ─────────────────────────────

def _autostart_installed() -> bool:
    return TRAY_PLIST_DST.exists()

def _launch_command():
    """Perintah untuk meluncurkan app ini (bundle .app atau script dev)."""
    if paths.is_frozen():
        # Di dalam .app: <App>.app/Contents/MacOS/<exe>
        return [str(Path(sys.executable).resolve())]
    return [sys.executable, str(Path(__file__).resolve())]

def _autostart_install():
    LAUNCH_AGENTS.mkdir(parents=True, exist_ok=True)
    args = _launch_command()
    prog_args = "".join(f"        <string>{a}</string>\n" for a in args)
    plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{TRAY_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
{prog_args}    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>ProcessType</key>
    <string>Interactive</string>
</dict>
</plist>
"""
    TRAY_PLIST_DST.write_text(plist)
    subprocess.run(["launchctl", "load", str(TRAY_PLIST_DST)], capture_output=True)

def _autostart_uninstall():
    subprocess.run(["launchctl", "unload", str(TRAY_PLIST_DST)], capture_output=True)
    TRAY_PLIST_DST.unlink(missing_ok=True)

# ─── Tray App ─────────────────────────────────────────────────────

class CoolifyTrayApp(rumps.App):
    def __init__(self):
        icon = ICON_PATH if os.path.exists(ICON_PATH) else None
        super().__init__("Coolify Monitor", icon=icon, template=False, quit_button=None)

        self._monitor = None
        self._monitor_thread = None
        self._web_started = False

        self.status_item = rumps.MenuItem("Status: ...")
        self.toggle_item = rumps.MenuItem("Start Monitor", callback=self.toggle_monitor)
        self.dashboard_item = rumps.MenuItem("Buka Dashboard", callback=self.open_dashboard)

        self.log_menu = rumps.MenuItem("Log Terakhir")
        self.log_menu.add(rumps.MenuItem("Lihat 20 Baris Terakhir", callback=self.show_logs))
        self.log_menu.add(rumps.MenuItem("Buka File Log", callback=self.open_log_file))
        self.log_menu.add(rumps.MenuItem("Buka di Console.app", callback=self.open_console))

        self.alert_recovery_item = rumps.MenuItem("Alert on Recovery", callback=self.toggle_alert_recovery)
        self.poll_item = rumps.MenuItem("Poll Interval...", callback=self.set_poll_interval)
        self.settings_menu = rumps.MenuItem("Settings")
        self.settings_menu.add(rumps.MenuItem("Edit .env", callback=self.edit_env))
        self.settings_menu.add(self.alert_recovery_item)
        self.settings_menu.add(self.poll_item)

        self.autostart_item = rumps.MenuItem("Auto-start saat Login", callback=self.toggle_autostart)

        self.menu = [
            self.status_item,
            None,
            self.dashboard_item,
            self.log_menu,
            None,
            self.toggle_item,
            None,
            self.settings_menu,
            self.autostart_item,
            None,
            rumps.MenuItem("Quit", callback=self.quit_app),
        ]

        self.refresh_state()
        self._timer = rumps.Timer(self._on_tick, 5)
        self._timer.start()

        # Auto-start monitor & web saat tray diluncurkan, bila config valid.
        # Ini membuat "Hide to Tray" dari CLI benar-benar jalan di background.
        if self._config_ok():
            self.start_monitor()
            self._start_web()

    # ─── State ────────────────────────────────────

    def _monitor_running(self) -> bool:
        return self._monitor_thread is not None and self._monitor_thread.is_alive()

    def _on_tick(self, _):
        self.refresh_state()

    def refresh_state(self):
        if self._monitor_running():
            self.title = DOT_RUNNING
            self.status_item.title = "Status: Running"
            self.toggle_item.title = "Stop Monitor"
        else:
            self.title = DOT_STOPPED
            self.status_item.title = "Status: Stopped"
            self.toggle_item.title = "Start Monitor"

        alert_recovery = _read_env_value("ALERT_ON_RECOVERY", "true").lower() == "true"
        self.alert_recovery_item.state = 1 if alert_recovery else 0

        poll = _read_env_value("POLL_INTERVAL", "30")
        self.poll_item.title = f"Poll Interval ({poll}s)..."

        self.autostart_item.state = 1 if _autostart_installed() else 0

    # ─── Monitor control (in-process) ─────────────

    def _config_ok(self) -> bool:
        url = _read_env_value("COOLIFY_URL")
        key = _read_env_value("COOLIFY_API_KEY")
        return bool(url) and bool(key) and key != "your-api-key-here"

    def toggle_monitor(self, _):
        if self._monitor_running():
            self.stop_monitor()
            notify("Coolify Monitor", "Monitor dihentikan.")
        else:
            if not self._config_ok():
                rumps.alert(
                    "Konfigurasi belum lengkap",
                    "Set COOLIFY_URL & COOLIFY_API_KEY dulu lewat Settings → Edit .env.",
                )
                self.edit_env(None)
                return
            self.start_monitor()
            notify("Coolify Monitor", "Monitor dijalankan.")
        self.refresh_state()

    def start_monitor(self):
        from dotenv import load_dotenv
        load_dotenv(ENV_FILE, override=True)
        import background_monitor

        self._monitor = background_monitor.BackgroundMonitor()

        def _run():
            try:
                self._monitor.run()
            except Exception as e:
                notify("Coolify Monitor", f"Monitor error: {str(e)[:80]}")

        self._monitor_thread = threading.Thread(target=_run, daemon=True, name="coolify-monitor")
        self._monitor_thread.start()

    def stop_monitor(self):
        if self._monitor:
            self._monitor.stop()
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)
        self._monitor = None
        self._monitor_thread = None

    # ─── Dashboard (in-process Flask) ─────────────

    def _start_web(self):
        """Start web dashboard in-process (sekali). Monitor dikelola terpisah
        oleh tray, jadi run_server dipanggil dengan start_monitor=False."""
        if self._web_started:
            return
        port = _read_env_value("WEB_PORT", "5555")
        from dotenv import load_dotenv
        load_dotenv(ENV_FILE, override=True)

        def _serve():
            try:
                import importlib
                web_app = importlib.import_module("web.app")
                web_app.run_server(host="127.0.0.1", port=int(port), start_monitor=False)
            except Exception as e:
                notify("Coolify Monitor", f"Web server error: {str(e)[:80]}")

        t = threading.Thread(target=_serve, daemon=True, name="coolify-web")
        t.start()
        self._web_started = True

    def open_dashboard(self, _):
        port = _read_env_value("WEB_PORT", "5555")
        if not self._web_started:
            self._start_web()
            notify("Coolify Monitor", "Web dashboard dijalankan...")
            time.sleep(2)
        webbrowser.open(f"http://localhost:{port}")

    # ─── Log ──────────────────────────────────────

    def show_logs(self, _):
        content = _tail(LOG_FILE, 20)
        rumps.Window(
            message="20 baris log terakhir:",
            title="Coolify Monitor — Log",
            default_text=content,
            dimensions=(480, 300),
        ).run()

    def open_log_file(self, _):
        subprocess.run(["open", str(LOG_FILE)])

    def open_console(self, _):
        subprocess.run(["open", "-a", "Console", str(LOG_FILE)])

    # ─── Settings ─────────────────────────────────

    def edit_env(self, _):
        subprocess.run(["open", "-t", str(ENV_FILE)])

    def toggle_alert_recovery(self, _):
        current = _read_env_value("ALERT_ON_RECOVERY", "true").lower() == "true"
        _set_env_value("ALERT_ON_RECOVERY", "false" if current else "true")
        self.refresh_state()
        notify("Coolify Monitor", "Tersimpan. Restart monitor untuk menerapkan.")

    def set_poll_interval(self, _):
        current = _read_env_value("POLL_INTERVAL", "30")
        resp = rumps.Window(
            message="Interval polling (detik):",
            title="Poll Interval",
            default_text=current,
            ok="Simpan",
            cancel="Batal",
            dimensions=(120, 20),
        ).run()
        if not resp.clicked:
            return
        val = resp.text.strip()
        if val.isdigit() and int(val) > 0:
            _set_env_value("POLL_INTERVAL", val)
            self.refresh_state()
            notify("Coolify Monitor", "Poll interval tersimpan. Restart monitor untuk menerapkan.")
        else:
            rumps.alert("Input tidak valid", "Masukkan angka detik > 0.")

    # ─── Auto-start ───────────────────────────────

    def toggle_autostart(self, _):
        if _autostart_installed():
            _autostart_uninstall()
            notify("Coolify Monitor", "Auto-start dimatikan.")
        else:
            _autostart_install()
            notify("Coolify Monitor", "Auto-start diaktifkan.")
        self.refresh_state()

    # ─── Quit ─────────────────────────────────────

    def quit_app(self, _):
        self.stop_monitor()
        rumps.quit_application()


if __name__ == "__main__":
    CoolifyTrayApp().run()
