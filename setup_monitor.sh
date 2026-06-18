#!/bin/bash
# ============================================================
# Coolify Monitor — Instalasi / Uninstall / Management
# ============================================================
#
# Usage:
#   ./setup_monitor.sh install    # Instal & jalankan auto-start
#   ./setup_monitor.sh uninstall  # Hapus auto-start
#   ./setup_monitor.sh start      # Mulai manual
#   ./setup_monitor.sh stop       # Hentikan
#   ./setup_monitor.sh restart    # Restart
#   ./setup_monitor.sh status     # Cek status
#   ./setup_monitor.sh logs       # Lihat log realtime
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DEPLOY_DIR="$HOME/.local/bin"
PLIST_NAME="com.coolify.monitor"
PLIST_FILE="$SCRIPT_DIR/$PLIST_NAME.plist"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
INSTALL_PATH="$LAUNCH_AGENTS_DIR/$PLIST_NAME.plist"
PYTHON_BIN="$SCRIPT_DIR/venv/bin/python3"
MONITOR_SCRIPT="$DEPLOY_DIR/background_monitor.py"
PID_FILE="$DEPLOY_DIR/.monitor.pid"
LOG_FILE="$HOME/Library/Logs/coolify_monitor.log"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

print_header() {
    echo ""
    echo -e "${CYAN}╔══════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║     Coolify Monitor — Setup Manager     ║${NC}"
    echo -e "${CYAN}╚══════════════════════════════════════════╝${NC}"
    echo ""
}

check_prerequisites() {
    echo -e "${CYAN}[1/4] Checking prerequisites...${NC}"

    # Check Python venv
    if [ ! -f "$PYTHON_BIN" ]; then
        echo -e "${RED}  ✗ Python venv not found at $PYTHON_BIN${NC}"
        echo -e "  Run: python3 -m venv venv && source venv/bin/activate && pip install requests python-dotenv"
        exit 1
    fi
    echo -e "  ${GREEN}✓ Python venv found${NC}"

    # Check .env file
    if [ ! -f "$SCRIPT_DIR/.env" ]; then
        echo -e "${RED}  ✗ .env file not found${NC}"
        echo -e "  Copy .env.example to .env and configure it"
        exit 1
    fi
    echo -e "  ${GREEN}✓ .env file found${NC}"

    # Check monitor script
    if [ ! -f "$MONITOR_SCRIPT" ]; then
        echo -e "${RED}  ✗ background_monitor.py not found${NC}"
        exit 1
    fi
    echo -e "  ${GREEN}✓ Monitor script found${NC}"
}

install() {
    print_header

    check_prerequisites

    # Create LaunchAgents dir if needed
    mkdir -p "$LAUNCH_AGENTS_DIR"

    echo -e "${CYAN}[2/5] Deploying to $DEPLOY_DIR...${NC}"

    mkdir -p "$DEPLOY_DIR"

    # Copy monitor files
    for f in background_monitor.py coolify_client.py uptime_tracker.py display.py .env uptime.db; do
        cp "$SCRIPT_DIR/$f" "$DEPLOY_DIR/$f" 2>/dev/null || true
    done
    chmod +x "$DEPLOY_DIR/background_monitor.py"
    echo -e "  ${GREEN}✓ Files deployed to $DEPLOY_DIR${NC}"

    echo -e "${CYAN}[3/5] Installing LaunchAgent...${NC}"

    # Copy plist with corrected path
    cp "$PLIST_FILE" "$INSTALL_PATH"
    echo -e "  ${GREEN}✓ Plist copied to $INSTALL_PATH${NC}"

    echo -e "${CYAN}[4/5] Loading LaunchAgent...${NC}"

    # Unload first if already loaded
    launchctl bootout "gui/$(id -u)/$PLIST_NAME" 2>/dev/null || true

    # Load the agent
    launchctl bootstrap "gui/$(id -u)" "$INSTALL_PATH"
    echo -e "  ${GREEN}✓ LaunchAgent loaded${NC}"

    echo -e "${CYAN}[5/5] Verifying...${NC}"
    sleep 2
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if kill -0 "$PID" 2>/dev/null; then
            echo -e "  ${GREEN}✓ Monitor berjalan (PID $PID)${NC}"
        else
            echo -e "  ${YELLOW}⚠ Monitor sedang mulai, tunggu sebentar...${NC}"
        fi
    else
        echo -e "  ${YELLOW}⚠ Monitor belum terdeteksi, cek log: $LOG_FILE${NC}"
    fi

    echo ""
    echo -e "${GREEN}═══════════════════════════════════════════${NC}"
    echo -e "  ${GREEN}Instalasi selesai!${NC}"
    echo -e "  Monitor akan auto-start setiap login macOS."
    echo -e ""
    echo -e "  Log:  ${CYAN}$LOG_FILE${NC}"
    echo -e "  Stop: ${CYAN}./setup_monitor.sh stop${NC}"
    echo -e "${GREEN}═══════════════════════════════════════════${NC}"
    echo ""
}

uninstall() {
    print_header
    echo -e "${CYAN}Uninstalling Coolify Monitor...${NC}"

    # Stop monitor if running
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if kill -0 "$PID" 2>/dev/null; then
            echo -e "  Menghentikan monitor (PID $PID)..."
            kill "$PID" 2>/dev/null || true
            sleep 1
        fi
    fi

    # Unload LaunchAgent
    launchctl bootout "gui/$(id -u)/$PLIST_NAME" 2>/dev/null || true
    echo -e "  ${GREEN}✓ LaunchAgent unloaded${NC}"

    # Remove plist
    rm -f "$INSTALL_PATH"
    echo -e "  ${GREEN}✓ Plist removed${NC}"

    # Remove PID file
    rm -f "$PID_FILE"

    echo ""
    echo -e "${GREEN}  Uninstall selesai. Monitor tidak akan auto-start lagi.${NC}"
    echo ""
}

start() {
    print_header
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if kill -0 "$PID" 2>/dev/null; then
            echo -e "${YELLOW}Monitor sudah berjalan (PID $PID)${NC}"
            return
        fi
    fi

    echo -e "${CYAN}Memulai monitor...${NC}"
    cd "$SCRIPT_DIR"
    source venv/bin/activate
    nohup python3 "$MONITOR_SCRIPT" >> "$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"
    sleep 2

    if kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        echo -e "${GREEN}✓ Monitor dimulai (PID $(cat "$PID_FILE"))${NC}"
    else
        echo -e "${RED}✗ Gagal memulai monitor. Cek log: $LOG_FILE${NC}"
    fi
}

stop() {
    print_header
    if [ ! -f "$PID_FILE" ]; then
        echo -e "${YELLOW}Monitor tidak berjalan.${NC}"
        return
    fi

    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        echo -e "Menghentikan monitor (PID $PID)..."
        kill "$PID"
        sleep 1
        rm -f "$PID_FILE"
        echo -e "${GREEN}✓ Monitor dihentikan.${NC}"
    else
        echo -e "${YELLOW}PID $PID sudah tidak aktif.${NC}"
        rm -f "$PID_FILE"
    fi
}

status() {
    print_header
    # Check LaunchAgent
    if launchctl print "gui/$(id -u)/$PLIST_NAME" &>/dev/null; then
        echo -e "${GREEN}LaunchAgent: installed & loaded${NC}"
    else
        echo -e "${YELLOW}LaunchAgent: not loaded${NC}"
    fi

    # Check running process
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if kill -0 "$PID" 2>/dev/null; then
            echo -e "Process:     ${GREEN}running${NC} (PID $PID)"
        else
            echo -e "Process:     ${YELLOW}stale PID file${NC}"
        fi
    else
        echo -e "Process:     ${YELLOW}not running${NC}"
    fi
}

logs() {
    if [ -f "$LOG_FILE" ]; then
        tail -f "$LOG_FILE"
    else
        echo -e "${YELLOW}Log file belum ada: $LOG_FILE${NC}"
    fi
}

# ─── Main ─────────────────────────────────────────────

case "${1:-}" in
    install)
        install
        ;;
    uninstall)
        uninstall
        ;;
    start)
        start
        ;;
    stop)
        stop
        ;;
    restart)
        stop
        sleep 1
        start
        ;;
    status)
        status
        ;;
    logs)
        logs
        ;;
    *)
        echo "Usage: $0 {install|uninstall|start|stop|restart|status|logs}"
        echo ""
        echo "  install   — Instal LaunchAgent & mulai auto-start"
        echo "  uninstall — Hapus auto-start"
        echo "  start     — Mulai monitor manual"
        echo "  stop      — Hentikan monitor"
        echo "  restart   — Restart monitor"
        echo "  status    — Cek status monitor"
        echo "  logs      — Lihat log realtime"
        exit 1
        ;;
esac
