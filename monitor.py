#!/usr/bin/env python3
"""
Coolify Monitor — CLI dashboard for Coolify-managed containers and projects.

Usage:
    python monitor.py dashboard       # Full overview
    python monitor.py projects        # List all projects
    python monitor.py apps            # List all applications
    python monitor.py services        # List all services
    python monitor.py databases       # List all databases
    python monitor.py servers         # List all servers
    python monitor.py logs <app_name> # Show application logs
    python monitor.py watch           # Auto-refresh dashboard
    python monitor.py watch apps      # Auto-refresh apps view
    python monitor.py health          # Check API connectivity
"""

import sys
import os
import time
import signal

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

from coolify_client import CoolifyClient
from display import (
    console,
    render_dashboard,
    render_projects,
    render_applications,
    render_services,
    render_databases,
    render_servers,
    render_logs,
)


def get_client() -> CoolifyClient:
    url = os.getenv("COOLIFY_URL", "http://localhost:8000")
    key = os.getenv("COOLIFY_API_KEY", "")

    if not key or key == "your-api-key-here":
        console.print("[bold red]Error:[/] COOLIFY_API_KEY not configured.")
        console.print("[dim]1. Copy .env.example to .env[/]")
        console.print("[dim]2. Set COOLIFY_URL and COOLIFY_API_KEY[/]")
        console.print("[dim]3. Get API key from Coolify UI -> Settings -> API[/]")
        sys.exit(1)

    return CoolifyClient(url, key)


def cmd_health(client: CoolifyClient):
    try:
        result = client.health()
        console.print("[bold green]✓ Coolify API is healthy[/]")
        if result:
            for k, v in result.items():
                console.print(f"  {k}: {v}")
    except Exception as e:
        console.print(f"[bold red]✗ Health check failed:[/] {e}")
        sys.exit(1)


def cmd_dashboard(client: CoolifyClient):
    console.print("\n[bold]Fetching data from Coolify...[/]\n")
    data = client.get_all_status()
    render_dashboard(
        data["servers"],
        data["projects"],
        data["applications"],
        data["services"],
        data["databases"],
    )


def cmd_projects(client: CoolifyClient):
    projects = client.get_projects()
    render_projects(projects)


def cmd_apps(client: CoolifyClient):
    apps = client.get_applications()
    render_applications(apps)


def cmd_services(client: CoolifyClient):
    services = client.get_services()
    render_services(services)


def cmd_databases(client: CoolifyClient):
    databases = client.get_databases()
    render_databases(databases)


def cmd_servers(client: CoolifyClient):
    servers = client.get_servers()
    render_servers(servers)


def cmd_logs(client: CoolifyClient, app_name_or_uuid: str):
    apps = client.get_applications()
    target = None
    for app in apps:
        if (app.get("name", "").lower() == app_name_or_uuid.lower() or
                app.get("uuid", "").startswith(app_name_or_uuid)):
            target = app
            break

    if not target:
        console.print(f"[bold red]App not found:[/] {app_name_or_uuid}")
        console.print("[dim]Available apps:[/]")
        for a in apps:
            console.print(f"  - {a.get('name', a.get('uuid', '?')[:8])}")
        sys.exit(1)

    try:
        logs = client.get_application_logs(target["uuid"])
        if isinstance(logs, dict):
            logs = logs.get("logs", logs.get("data", str(logs)))
        render_logs(str(logs), target.get("name", app_name_or_uuid))
    except Exception as e:
        console.print(f"[bold red]Error fetching logs:[/] {e}")


def cmd_watch(client: CoolifyClient, subcmd: str = "dashboard"):
    interval = int(os.getenv("REFRESH_INTERVAL", "5"))
    running = True

    def handler(sig, frame):
        nonlocal running
        running = False
        console.print("\n[yellow]Stopping watch mode...[/]")

    signal.signal(signal.SIGINT, handler)

    cmd_map = {
        "dashboard": cmd_dashboard,
        "projects": cmd_projects,
        "apps": cmd_apps,
        "services": cmd_services,
        "databases": cmd_databases,
        "servers": cmd_servers,
    }
    fn = cmd_map.get(subcmd, cmd_dashboard)
    console.print(f"[bold cyan]Watch mode[/] — refreshing every {interval}s (Ctrl+C to stop)\n")

    while running:
        os.system("clear" if os.name != "nt" else "cls")
        try:
            fn(client)
        except Exception as e:
            console.print(f"[bold red]Error:[/] {e}")
        console.print(f"\n[dim]Refreshing in {interval}s... (Ctrl+C to stop)[/]")
        time.sleep(interval)

    console.print("[dim]Watch mode stopped.[/]")


def main():
    if len(sys.argv) < 2:
        console.print("[bold cyan]Coolify Monitor[/] — CLI dashboard for Coolify")
        console.print()
        console.print("Usage: [bold]python monitor.py <command>[/]")
        console.print()
        console.print("Commands:")
        console.print("  [cyan]dashboard[/]       Full overview of all resources")
        console.print("  [cyan]projects[/]        List all projects")
        console.print("  [cyan]apps[/]            List all applications")
        console.print("  [cyan]services[/]        List all services")
        console.print("  [cyan]databases[/]       List all databases")
        console.print("  [cyan]servers[/]         List all servers")
        console.print("  [cyan]logs <name|uuid>[/] Show application logs")
        console.print("  [cyan]watch [view][/]     Auto-refresh (default: dashboard)")
        console.print("  [cyan]health[/]          Check API connectivity")
        console.print()
        console.print("[dim]Configure .env with COOLIFY_URL and COOLIFY_API_KEY[/]")
        sys.exit(0)

    cmd = sys.argv[1].lower()
    client = get_client()

    commands = {
        "health": cmd_health,
        "dashboard": cmd_dashboard,
        "projects": cmd_projects,
        "apps": cmd_apps,
        "services": cmd_services,
        "databases": cmd_databases,
        "servers": cmd_servers,
    }

    if cmd == "logs":
        if len(sys.argv) < 3:
            console.print("[bold red]Usage:[/] python monitor.py logs <app_name|uuid>")
            sys.exit(1)
        cmd_logs(client, sys.argv[2])
    elif cmd == "watch":
        subcmd = sys.argv[2] if len(sys.argv) > 2 else "dashboard"
        cmd_watch(client, subcmd)
    elif cmd in commands:
        try:
            commands[cmd](client)
        except Exception as e:
            console.print(f"[bold red]Error:[/] {e}")
            sys.exit(1)
    else:
        console.print(f"[bold red]Unknown command:[/] {cmd}")
        console.print("[dim]Run without arguments to see available commands[/]")
        sys.exit(1)


if __name__ == "__main__":
    main()
