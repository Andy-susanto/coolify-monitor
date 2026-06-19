# Coolify Monitor

Monitoring real-time untuk server Coolify: web dashboard, notifikasi native saat resource down/recovery, tracking uptime, dan tray icon. Lintas platform — **macOS, Windows, Linux**.

## Quick Start

```bash
npm install -g github:Andy-susanto/coolify-monitor
coolify-monitor
```

Ketik `coolify-monitor` → monitor + web server jalan, browser otomatis terbuka, lalu muncul menu interaktif:

```
  ● Coolify Monitor aktif  http://localhost:5555

  1) Buka Dashboard       (http://localhost:5555)
  2) Hide to Tray         (jalan di background)
  3) Exit                 (hentikan monitor)
```

- **Buka Dashboard** — buka dashboard di browser
- **Hide to Tray** — pindah ke tray/menu bar, monitor tetap jalan di background
- **Exit** — hentikan monitor

Kalau konfigurasi belum lengkap, browser langsung diarahkan ke halaman **Settings** untuk mengisi Coolify URL & API Key.

> Syarat: **Python 3.9+** terpasang di mesin. Saat pertama dijalankan, dependency Python disiapkan otomatis di direktori konfigurasi (sekali saja, tidak mengotori folder project).

Dapatkan API key dari Coolify UI → **Settings → API**.

## Cara Pakai

```bash
coolify-monitor            # menu interaktif: dashboard / hide to tray / exit
coolify-monitor start      # sama dengan di atas
coolify-monitor dashboard  # sama dengan di atas
coolify-monitor tray       # langsung ke tray icon (tanpa menu)
coolify-monitor monitor    # monitor di foreground (tanpa web)
coolify-monitor menu       # menu lengkap di terminal
coolify-monitor setup      # konfigurasi via wizard terminal
coolify-monitor config     # tampilkan konfigurasi saat ini
coolify-monitor autostart on|off   # auto-start saat login
coolify-monitor doctor     # cek environment Python & dependency
coolify-monitor smoke      # smoke test lintas-OS
coolify-monitor help
```

## Konfigurasi

Semua setting bisa diatur dari **halaman Settings di web dashboard** (`/settings`) — tanpa menyentuh terminal:

| Setting | Keterangan |
|---|---|
| `COOLIFY_URL` | URL Coolify kamu |
| `COOLIFY_API_KEY` | API key dari Coolify UI → Settings → API |
| `POLL_INTERVAL` | Interval polling status (detik), default `30` |
| `ALERT_ON_RECOVERY` | Kirim notifikasi juga saat resource pulih |
| `WEB_PORT` | Port dashboard, default `5555` |
| `REFRESH_INTERVAL` | Interval refresh dashboard (detik), default `5` |
| `MONITOR_PASSWORD` | Password dashboard (kosong = tanpa auth) |

Konfigurasi tersimpan di direktori writable per-OS:
- macOS: `~/Library/Application Support/CoolifyMonitor/.env`
- Windows: `%APPDATA%\CoolifyMonitor\.env`
- Linux: `~/.config/coolify-monitor/.env`

## Fitur

- **Web dashboard** — status semua aplikasi, service, database secara real-time
- **Notifikasi native** — alert saat resource down / recovery (macOS, Windows, Linux)
- **Uptime tracking** — riwayat transisi status & persentase uptime (SQLite)
- **Tray icon** (opsional) — kontrol monitor dari menu bar / system tray
- **Halaman Settings web** — atur semua konfigurasi dari browser
- **Auto-start saat login** — lintas OS (LaunchAgent / registry / `.desktop`)

## Tray Icon

```bash
coolify-monitor tray
```

Tray menyediakan: status monitor, start/stop, buka dashboard, lihat log, edit setting, dan toggle auto-start. Di macOS pakai backend native (rumps), di Windows/Linux pakai pystray.

## Installer Desktop (alternatif npm)

Tersedia juga installer desktop yang **membundel Python** (user tidak perlu install Python):

- **macOS** — `.app` / `.dmg` (py2app)
- **Windows** — `.exe` (PyInstaller)

Rilis dibuat otomatis lewat GitHub Actions. Cukup naikkan `version` di `package.json` lalu push ke `main`:

```bash
# contoh: 1.0.0 -> 1.0.1
npm version patch --no-git-tag-version
git commit -am "release: v1.0.1" && git push
```

Workflow akan membuat tag `vX.Y.Z`, membangun `.exe` + `.dmg`, lalu menerbitkan **GitHub Release** dengan catatan otomatis dari commit. Push tag manual (`git tag v1.0.0 && git push origin v1.0.0`) juga tetap memicu rilis. Installer muncul di tab **Releases**.

## Development

```bash
git clone https://github.com/Andy-susanto/coolify-monitor.git
cd coolify-monitor
npm install          # menyiapkan venv + dependency Python
node bin/cli.js      # jalankan mode dashboard
```

CLI dashboard berbasis terminal (rich) juga tersedia:

```bash
python monitor.py dashboard    # overview
python monitor.py apps         # daftar aplikasi
python monitor.py watch        # auto-refresh
python monitor.py health       # cek konektivitas API
```

## Verifikasi Lintas-OS

```bash
coolify-monitor smoke
```

Smoke test memverifikasi path config, Python venv, import modul, dan backend tray sesuai OS. CI menjalankannya otomatis di ubuntu, macOS, dan Windows (lihat `.github/workflows/smoke.yml`).

## Lisensi

MIT
