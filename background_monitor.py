#!/usr/bin/env python3
"""
Coolify Background Monitor — berjalan sebagai LaunchAgent di macOS.

Fitur:
- Memantau status semua resource (applications, services, databases) secara periodik
- Mengirim notifikasi macOS native saat status berubah (down/up/degraded)
- Menulis log ke ~/Library/Logs/coolify_monitor.log
- Menggunakan uptime_tracker untuk mencatat history status

Konfigurasi di .env:
  POLL_INTERVAL=30         # detik antara polling (default 30)
  ALERT_ON_RECOVERY=true   # kirim notifikasi juga saat resource pulih
"""

import os
import sys
import time
import signal
import logging
import subprocess
import json
import threading
from datetime import datetime
from pathlib import Path

# ─── Setup ────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

import paths

from dotenv import load_dotenv
load_dotenv(paths.ensure_env())

from coolify_client import CoolifyClient
from uptime_tracker import get_tracker

# ─── Logging ──────────────────────────────────────────────────────

LOG_DIR = paths.log_dir()
LOG_FILE = LOG_DIR / "coolify_monitor.log"

logger = logging.getLogger("coolify_monitor")
logger.setLevel(logging.INFO)

fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logger.addHandler(fh)

sh = logging.StreamHandler()
sh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logger.addHandler(sh)

# ─── Config ───────────────────────────────────────────────────────

COOLIFY_URL = os.getenv("COOLIFY_URL", "")
COOLIFY_API_KEY = os.getenv("COOLIFY_API_KEY", "")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "30"))
ALERT_ON_RECOVERY = os.getenv("ALERT_ON_RECOVERY", "true").lower() == "true"
PID_FILE = Path(os.getenv("COOLIFY_PID_FILE", str(paths.pid_file())))

# State yang dianggap "down"
DOWN_STATES = {"stopped", "exited", "dead", "failed", "unhealthy", "degraded"}
# State yang dianggap "up"
UP_STATES = {"running", "started", "healthy"}


def normalize_status(status: str) -> str:
    """Ambil status utama sebelum ':'."""
    if not status:
        return "unknown"
    return status.lower().strip().split(":")[0]


def send_notification(title: str, message: str, subtitle: str = ""):
    """Kirim notifikasi native macOS via osascript."""
    script_parts = [f'display notification "{message}" with title "{title}"']
    if subtitle:
        script_parts.append(f'subtitle "{subtitle}"')
    script_parts.append("sound name \"Submarine\"")
    script = " ".join(script_parts)
    try:
        subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, timeout=10
        )
        logger.info(f"Notifikasi terkirim: {title} — {message}")
    except Exception as e:
        logger.error(f"Gagal mengirim notifikasi: {e}")


def send_alert_dialog(title: str, message: str):
    """Kirim alert dialog yang lebih mencolok (muncul di depan user)."""
    script = f'display alert "{title}" message "{message}" as critical'
    try:
        subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, timeout=15
        )
    except Exception:
        pass


class BackgroundMonitor:
    def __init__(self):
        # Baca config per-instance agar restart in-process memuat setting terbaru.
        self.url = os.getenv("COOLIFY_URL", COOLIFY_URL)
        self.api_key = os.getenv("COOLIFY_API_KEY", COOLIFY_API_KEY)
        self.poll_interval = int(os.getenv("POLL_INTERVAL", str(POLL_INTERVAL)))
        self.alert_on_recovery = os.getenv("ALERT_ON_RECOVERY", "true").lower() == "true"
        self.client = CoolifyClient(self.url, self.api_key)
        self.tracker = get_tracker()
        self.running = True
        self.last_known_state = {}  # uuid -> {"status": str, "name": str, "type": str}

        # Signal handler hanya bisa diregistrasi di main thread (mode CLI/standalone).
        # Saat dijalankan in-process sebagai thread (tray app), lewati.
        if threading.current_thread() is threading.main_thread():
            signal.signal(signal.SIGTERM, self._handle_signal)
            signal.signal(signal.SIGINT, self._handle_signal)

    def stop(self):
        """Hentikan loop dari thread lain (dipakai tray app in-process)."""
        self.running = False

    def _handle_signal(self, sig, frame):
        logger.info(f"Menerima sinyal {sig}, berhenti...")
        self.running = False

    def _write_pid(self):
        """Tulis PID file agar bisa dicek statusnya."""
        PID_FILE.write_text(str(os.getpid()))

    def _remove_pid(self):
        """Hapus PID file saat berhenti."""
        try:
            PID_FILE.unlink()
        except FileNotFoundError:
            pass

    def _fetch_all_resources(self) -> list:
        """Ambil semua resource dan normalisasi ke format standar."""
        resources = []

        for fetcher, rtype in [
            (self.client.get_applications, "application"),
            (self.client.get_services, "service"),
            (self.client.get_databases, "database"),
        ]:
            try:
                items = fetcher()
                for item in items:
                    resources.append({
                        "uuid": item.get("uuid", ""),
                        "name": item.get("name", "unknown"),
                        "type": rtype,
                        "status": item.get("status", "unknown"),
                    })
            except Exception as e:
                logger.error(f"Gagal mengambil {rtype}s: {e}")

        return resources

    def _check_and_alert(self, resources: list):
        """Bandingkan status terbaru dengan state terakhir, kirim notifikasi jika berubah."""
        current_state = {}

        for r in resources:
            uuid = r["uuid"]
            if not uuid:
                continue

            status = r["status"]
            name = r["name"]
            rtype = r["type"]
            current = normalize_status(status)

            current_state[uuid] = {"status": status, "name": name, "type": rtype}

            prev = self.last_known_state.get(uuid)
            if prev is None:
                # Pertama kali melihat resource ini, catat saja
                continue

            prev_status = normalize_status(prev["status"])

            if current == prev_status:
                continue

            # Status berubah! Kirim notifikasi
            type_label = {"application": "App", "service": "Service", "database": "DB"}.get(rtype, rtype)

            if current in DOWN_STATES:
                send_notification(
                    title=f"Resource Down: {name}",
                    message=f"{type_label} [{name}] status: {status}",
                    subtitle="Coolify Monitor Alert",
                )
                logger.warning(f"DOWN: {rtype}/{name} ({uuid[:8]}) -> {status}")

            elif current in UP_STATES:
                if self.alert_on_recovery:
                    send_notification(
                        title=f"Resource Recovered: {name}",
                        message=f"{type_label} [{name}] kembali running",
                        subtitle="Coolify Monitor",
                    )
                logger.info(f"RECOVERED: {rtype}/{name} ({uuid[:8]}) -> {status}")

            else:
                # Status tidak dikenal atau transisi lain
                send_notification(
                    title=f"Status Changed: {name}",
                    message=f"{type_label} [{name}]: {prev_status} -> {status}",
                    subtitle="Coolify Monitor",
                )
                logger.info(f"CHANGED: {rtype}/{name} ({uuid[:8]}): {prev_status} -> {status}")

        # Update state terakhir
        self.last_known_state = current_state

    def run(self):
        """Loop utama monitoring."""
        self._write_pid()
        logger.info("=" * 60)
        logger.info(f"Coolify Background Monitor dimulai (PID {os.getpid()})")
        logger.info(f"URL: {self.url}")
        logger.info(f"Poll interval: {self.poll_interval}s")
        logger.info(f"Alert on recovery: {self.alert_on_recovery}")
        logger.info(f"Log file: {LOG_FILE}")
        logger.info("=" * 60)

        # Kirim notifikasi bahwa monitor aktif
        send_notification(
            title="Coolify Monitor",
            message="Monitoring dimulai. Alert aktif.",
            subtitle="Background Service",
        )

        consecutive_errors = 0
        max_errors_before_alert = 3

        while self.running:
            try:
                resources = self._fetch_all_resources()
                self._check_and_alert(resources)

                # Record ke uptime tracker
                self.tracker.record_snapshot(resources)

                consecutive_errors = 0
                logger.debug(f"Polling berhasil: {len(resources)} resource")

            except Exception as e:
                consecutive_errors += 1
                logger.error(f"Polling error ({consecutive_errors}): {e}")

                # Setelah beberapa kali gagal berturut-turut, kirim alert
                if consecutive_errors == max_errors_before_alert:
                    send_notification(
                        title="Coolify Monitor: Connection Error",
                        message=f"Gagal menghubungi Coolify ({consecutive_errors}x): {str(e)[:80]}",
                        subtitle="Coolify Monitor Alert",
                    )

            # Tunggu interval berikutnya
            for _ in range(self.poll_interval):
                if not self.running:
                    break
                time.sleep(1)

        self._remove_pid()
        logger.info("Background Monitor berhenti.")


def check_already_running():
    """Cek apakah monitor sudah berjalan via PID file."""
    if not PID_FILE.exists():
        return False
    try:
        pid = int(PID_FILE.read_text().strip())
        # Cek apakah proses masih hidup
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, ValueError):
        # PID tidak valid, hapus file
        PID_FILE.unlink(missing_ok=True)
        return False


def main():
    # Validasi konfigurasi
    if not COOLIFY_URL or not COOLIFY_API_KEY:
        logger.error("COOLIFY_URL atau COOLIFY_API_KEY belum dikonfigurasi di .env")
        sys.exit(1)

    # Cek apakah sudah berjalan
    if check_already_running():
        pid = PID_FILE.read_text().strip()
        logger.warning(f"Monitor sudah berjalan (PID {pid}). Hentikan dulu sebelum menjalankan ulang.")
        print(f"Monitor sudah berjalan (PID {pid}).")
        print(f"Jalankan: python background_monitor.py stop")
        sys.exit(0)

    if len(sys.argv) > 1 and sys.argv[1] == "stop":
        if PID_FILE.exists():
            try:
                pid = int(PID_FILE.read_text().strip())
                os.kill(pid, signal.SIGTERM)
                print(f"Menghentikan monitor (PID {pid})...")
                # Tunggu sebentar
                for _ in range(10):
                    try:
                        os.kill(pid, 0)
                        time.sleep(0.5)
                    except ProcessLookupError:
                        break
                PID_FILE.unlink(missing_ok=True)
                print("Monitor dihentikan.")
            except (ProcessLookupError, ValueError):
                PID_FILE.unlink(missing_ok=True)
                print("Monitor sudah tidak berjalan.")
        else:
            print("Tidak ada monitor yang berjalan.")
        return

    if len(sys.argv) > 1 and sys.argv[1] == "status":
        if check_already_running():
            pid = PID_FILE.read_text().strip()
            print(f"Monitor berjalan (PID {pid})")
        else:
            print("Monitor tidak berjalan.")
        return

    # Jalankan monitor
    monitor = BackgroundMonitor()
    monitor.run()


if __name__ == "__main__":
    main()
