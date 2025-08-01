#!/usr/bin/env python3

import json
import subprocess
import argparse
from rich.console import Console
from rich.table import Table
from rich.box import HORIZONTALS
from textwrap import wrap
import shutil
import csv
import sys
from pathlib import Path

console = Console()

def run_cmd(cmd):
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True).stdout.strip()

def parse_args():
    parser = argparse.ArgumentParser(
        description="\U0001F4E6 Prettified Docker ps output with wrapped columns, filtering, paging, and export",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""
Examples:

  ./docker-ps-pretty.py --sortby name --desc
  ./docker-ps-pretty.py --filter "name:ombi status:running"
  ./docker-ps-pretty.py --format csv --output containers.csv
  ./docker-ps-pretty.py --limit 5 --pager
  ./docker-ps-pretty.py --fzf
        """
    )
    parser.add_argument("--sortby", choices=["id", "name", "image", "status", "created", "ports"], help="Sort containers by one of: id, name, image, status, created, ports")
    parser.add_argument("--desc", action="store_true", help="Sort in descending order")
    parser.add_argument("--filter", help="Multi-key filter (e.g., \"name:ombi status:running\")")
    parser.add_argument("--fzf", action="store_true", help="Pipe output to fzf for interactive selection")
    parser.add_argument("--format", choices=["table", "json", "csv", "markdown"], default="table", help="Output format")
    parser.add_argument("--limit", type=int, help="Limit number of rows shown")
    parser.add_argument("--pager", action="store_true", help="Pipe output to less or bat for paging")
    parser.add_argument("--output", type=str, help="Write output to file instead of stdout")
    return parser.parse_args()

def get_sort_key(field):
    return {
        "id": "ID",
        "name": "Names",
        "image": "Image",
        "status": "Status",
        "created": "CreatedAt",
        "ports": "Ports"
    }.get(field)

def parse_filters(filter_string):
    if not filter_string:
        return []
    parts = filter_string.split()
    filters = []
    for part in parts:
        if ':' in part:
            k, v = part.split(':', 1)
            filters.append((k.lower(), v.lower()))
    return filters

def apply_filters(containers, filters):
    def matches(container):
        for key, val in filters:
            if not any(key in k.lower() and val in str(v).lower() for k, v in container.items()):
                return False
        return True
    return list(filter(matches, containers))

def style_status(status):
    if "up" in status.lower():
        return f"[green]{status}[/green]"
    elif "exited" in status.lower() or "dead" in status.lower():
        return f"[red]{status}[/red]"
    else:
        return f"[yellow]{status}[/yellow]"

def render_table(containers):
    table = Table(show_header=True, header_style="bold cyan", box=HORIZONTALS, show_lines=True, pad_edge=False, border_style="dim cyan")

    # Auto-width logic
    table.add_column("ID", style="bold", no_wrap=True)
    table.add_column("Name")
    table.add_column("Image", overflow="fold")
    table.add_column("Status")
    table.add_column("Created")
    table.add_column("Ports", overflow="fold")

    for c in containers:
        ports = "\n".join(wrap(c.get("Ports", ""), 48))
        table.add_row(
            c.get("ID", ""),
            c.get("Names", ""),
            c.get("Image", ""),
            style_status(c.get("Status", "")),
            c.get("CreatedAt", ""),
            ports
        )
    return table

def output_data(containers, fmt, output=None):
    out = Path(output) if output else None
    if fmt == "json":
        json_output = json.dumps(containers, indent=2)
        if out:
            out.write_text(json_output)
        else:
            print(json_output)
    elif fmt == "csv":
        target = out.open("w", newline="") if out else sys.stdout
        writer = csv.DictWriter(target, fieldnames=["ID", "Names", "Image", "Status", "CreatedAt", "Ports"])
        writer.writeheader()
        for c in containers:
            writer.writerow(c)
        if out:
            target.close()
    elif fmt == "markdown":
        md_lines = ["| ID | Name | Image | Status | Created | Ports |", "|----|------|-------|--------|---------|-------|"]
        for c in containers:
            md_lines.append(f"| {c['ID']} | {c['Names']} | {c['Image']} | {c['Status']} | {c['CreatedAt']} | {c['Ports']} |")
        result = "\n".join(md_lines)
        if out:
            out.write_text(result)
        else:
            console.print(result)
    else:
        table = render_table(containers)
        if out:
            with out.open("w") as f:
                with Console(file=f, force_terminal=True, width=140) as file_console:
                    file_console.print(table)
        elif args.pager:
            with console.pager():
                console.print(table)
        else:
            console.print(table)

def main():
    global args
    args = parse_args()
    raw = run_cmd(["docker", "ps", "--format", "{{json .}}"])
    if not raw:
        console.print("No containers found.")
        return

    containers = [json.loads(line) for line in raw.splitlines()]

    if args.filter:
        filters = parse_filters(args.filter)
        containers = apply_filters(containers, filters)

    if args.sortby:
        key = get_sort_key(args.sortby)
        containers.sort(key=lambda x: x.get(key, "").lower(), reverse=args.desc)

    if args.limit:
        containers = containers[:args.limit]

    if args.fzf:
        if not shutil.which("fzf"):
            console.print("[red]fzf is not installed or not in PATH.[/red]")
            return
        with console.capture() as capture:
            output_data(containers, args.format)
        subprocess.run(["fzf", "--ansi"], input=capture.get(), text=True)
    else:
        output_data(containers, args.format, output=args.output)


