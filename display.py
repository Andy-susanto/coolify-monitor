#!/usr/bin/env python3
"""
Terminal display module using Rich.
Renders tables, panels, and dashboard layouts for Coolify monitoring.
"""

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box
from datetime import datetime


console = Console()


def normalize_status(status: str) -> tuple:
    """Normalize compound status like 'running:healthy' -> ('running', 'healthy')"""
    if not status:
        return ("unknown", "")
    parts = status.lower().strip().split(":")
    main = parts[0]
    sub = parts[1] if len(parts) > 1 else ""
    return (main, sub)


def status_style(status: str) -> Text:
    """Colorize status text with compound status support"""
    main, sub = normalize_status(status)
    display = status or "unknown"

    if main in ("running", "healthy", "started"):
        return Text(f"● {display}", style="bold green")
    elif main in ("stopped", "exited", "dead", "failed"):
        return Text(f"● {display}", style="bold red")
    elif main in ("starting", "restarting", "deploying", "queued"):
        return Text(f"● {display}", style="bold yellow")
    elif main in ("degraded", "unhealthy"):
        return Text(f"● {display}", style="bold orange1")
    else:
        return Text(f"● {display}", style="dim")


def format_bytes(size) -> str:
    if size is None:
        return "N/A"
    try:
        size = float(size)
    except (TypeError, ValueError):
        return "N/A"
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if abs(size) < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"


def render_projects(projects: list):
    table = Table(
        title="📁 Projects", box=box.ROUNDED, show_lines=True,
        title_style="bold cyan", header_style="bold white on dark_blue",
    )
    table.add_column("Name", style="cyan", min_width=20)
    table.add_column("UUID", style="dim", max_width=12)
    table.add_column("Description", style="dim", max_width=40)

    if not projects:
        table.add_row("[dim]No projects found[/]", "", "")
    else:
        for proj in projects:
            desc = proj.get("description") or "-"
            if len(desc) > 38:
                desc = desc[:38] + ".."
            table.add_row(
                proj.get("name", "N/A"),
                (proj.get("uuid") or "?")[:8],
                desc,
            )
    console.print(table)


def render_applications(applications: list):
    table = Table(
        title="🚀 Applications", box=box.ROUNDED, show_lines=True,
        title_style="bold cyan", header_style="bold white on dark_blue",
    )
    table.add_column("Name", style="cyan", min_width=20)
    table.add_column("Status", justify="center", min_width=16)
    table.add_column("FQDN / URL", style="dim blue", max_width=42)
    table.add_column("Build Pack", style="dim", max_width=14)
    table.add_column("Git Branch", style="dim", max_width=14)
    table.add_column("Resources", justify="center")

    if not applications:
        table.add_row("[dim]No applications found[/]", "", "", "", "", "")
    else:
        for app in applications:
            status = app.get("status", "unknown")
            fqdn = app.get("fqdn") or "-"
            if fqdn != "-" and len(fqdn) > 40:
                fqdn = fqdn[:40] + ".."

            resource_parts = []
            if app.get("limits_memory"):
                resource_parts.append(f"mem:{app['limits_memory']}MB")
            if app.get("limits_cpus"):
                resource_parts.append(f"cpu:{app['limits_cpus']}")
            resource = " | ".join(resource_parts) if resource_parts else "-"

            table.add_row(
                app.get("name", app.get("uuid", "?")[:8]),
                status_style(status),
                fqdn,
                app.get("build_pack") or "-",
                app.get("git_branch") or "-",
                resource,
            )
    console.print(table)


def render_services(services: list):
    table = Table(
        title="⚙️  Services", box=box.ROUNDED, show_lines=True,
        title_style="bold cyan", header_style="bold white on dark_blue",
    )
    table.add_column("Name", style="cyan", min_width=20)
    table.add_column("Status", justify="center", min_width=16)
    table.add_column("Type", style="magenta")
    table.add_column("FQDN / URL", style="dim blue", max_width=42)

    if not services:
        table.add_row("[dim]No services found[/]", "", "", "")
    else:
        for svc in services:
            fqdn = svc.get("fqdn") or "-"
            if fqdn != "-" and len(fqdn) > 40:
                fqdn = fqdn[:40] + ".."

            table.add_row(
                svc.get("name", svc.get("uuid", "?")[:8]),
                status_style(svc.get("status", "unknown")),
                svc.get("service_type") or svc.get("type") or "-",
                fqdn,
            )
    console.print(table)


def render_databases(databases: list):
    table = Table(
        title="🗄️  Databases", box=box.ROUNDED, show_lines=True,
        title_style="bold cyan", header_style="bold white on dark_blue",
    )
    table.add_column("Name", style="cyan", min_width=20)
    table.add_column("Status", justify="center", min_width=16)
    table.add_column("Type", style="magenta")
    table.add_column("Version", justify="center")
    table.add_column("Host:Port", style="dim")

    if not databases:
        table.add_row("[dim]No databases found[/]", "", "", "", "")
    else:
        for db in databases:
            host = db.get("host") or "-"
            port = db.get("public_port") or db.get("port") or ""
            hp = f"{host}:{port}" if port else host

            table.add_row(
                db.get("name", db.get("uuid", "?")[:8]),
                status_style(db.get("status", "unknown")),
                db.get("database_type") or db.get("type") or "-",
                db.get("version") or "-",
                hp,
            )
    console.print(table)


def render_servers(servers: list):
    table = Table(
        title="🖥️  Servers", box=box.ROUNDED, show_lines=True,
        title_style="bold cyan", header_style="bold white on dark_blue",
    )
    table.add_column("Name", style="cyan", min_width=15)
    table.add_column("Status", justify="center", min_width=12)
    table.add_column("IP / FQDN", style="dim")
    table.add_column("Port", justify="center")
    table.add_column("Usable", justify="center")

    if not servers:
        table.add_row("[dim]No servers found[/]", "", "", "", "")
    else:
        for srv in servers:
            reachable = srv.get("is_reachable", srv.get("settings", {}).get("is_reachable", None))
            status = "healthy" if reachable else "unreachable"
            usable = "✓" if srv.get("is_usable", srv.get("settings", {}).get("is_usable", False)) else "✗"

            table.add_row(
                srv.get("name", srv.get("uuid", "?")[:8]),
                status_style(status),
                srv.get("ip") or srv.get("fqdn") or "-",
                str(srv.get("port", "-")),
                usable,
            )
    console.print(table)


def render_dashboard(servers: list, projects: list, applications: list, services: list, databases: list):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    header = Panel(
        f"[bold cyan]Coolify Monitor[/]  •  {now}\n"
        f"[dim]Servers: {len(servers)}  |  Projects: {len(projects)}  |  "
        f"Apps: {len(applications)}  |  Services: {len(services)}  |  DBs: {len(databases)}[/]",
        box=box.DOUBLE, style="cyan",
    )
    console.print(header)

    # Status summary
    all_resources = applications + services + databases
    running = sum(1 for r in all_resources if normalize_status(r.get("status", ""))[0] in ("running", "started", "healthy"))
    stopped = sum(1 for r in all_resources if normalize_status(r.get("status", ""))[0] in ("stopped", "exited", "dead", "failed"))
    other = len(all_resources) - running - stopped

    summary = Table(box=None, show_header=False, padding=(0, 2))
    summary.add_column(style="bold")
    summary.add_column()
    summary.add_row("[green]● Running[/]", f"[green]{running}[/]")
    summary.add_row("[red]● Stopped[/]", f"[red]{stopped}[/]")
    summary.add_row("[yellow]● Other[/]", f"[yellow]{other}[/]")
    summary.add_row("[cyan]● Total[/]", f"{len(all_resources)}")

    console.print(Panel(summary, title="📊 Status Summary", box=box.ROUNDED, style="cyan"))

    render_servers(servers)
    render_projects(projects)
    render_applications(applications)
    render_services(services)
    render_databases(databases)


def render_logs(logs: str, app_name: str = ""):
    title = f"📋 Logs: {app_name}" if app_name else "📋 Logs"
    console.print(Panel(
        logs[-4000:] if len(logs) > 4000 else logs,
        title=title, box=box.ROUNDED, style="cyan",
    ))
