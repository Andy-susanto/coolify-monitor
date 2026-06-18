# Coolify Monitor

CLI dashboard untuk monitoring container dan project di server Coolify.

## Setup

```bash
cd /Users/uinjambi/Documents/project/coolify-monitor
cp .env.example .env
```

Edit `.env`:
- `COOLIFY_URL` — URL Coolify kamu (default: `http://localhost:8000`)
- `COOLIFY_API_KEY` — API key dari Coolify UI → Settings → API

## Usage

```bash
# Activate venv
source venv/bin/activate

# Full dashboard overview
python monitor.py dashboard

# Specific views
python monitor.py projects
python monitor.py apps
python monitor.py services
python monitor.py databases
python monitor.py servers

# Application logs
python monitor.py logs <app_name_or_uuid>

# Auto-refresh mode (default 5s, configurable via REFRESH_INTERVAL in .env)
python monitor.py watch
python monitor.py watch apps

# Check API connectivity
python monitor.py health
```

## Quick Alias

Tambahkan ke ~/.zshrc:
```bash
alias cfm='python /Users/uinjambi/Documents/project/coolify-monitor/monitor.py'
```

Lalu bisa pakai:
```bash
cfm dashboard
cfm apps
cfm watch
```
