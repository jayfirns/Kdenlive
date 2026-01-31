"""
kdv - Kdenlive Video Workflow CLI

Main entry point for the command-line interface.
"""

import click
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from kdv import __version__
from kdv.config import get_config

console = Console()


def get_folder_stats(path: Path) -> tuple[int, int]:
    """Get file count and total size for a directory."""
    if not path.exists():
        return 0, 0

    total_size = 0
    file_count = 0

    for item in path.rglob("*"):
        if item.is_file() and item.suffix.lower() in (".mp4", ".mov", ".mkv", ".avi"):
            file_count += 1
            total_size += item.stat().st_size

    return file_count, total_size


def format_size(size_bytes: int) -> str:
    """Format bytes as human-readable size."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"


@click.group()
@click.version_option(version=__version__, prog_name="kdv")
@click.pass_context
def cli(ctx):
    """kdv - Kdenlive Video Workflow Toolkit

    Automate your drone footage workflow with Kdenlive.
    """
    ctx.ensure_object(dict)
    ctx.obj["config"] = get_config()


@cli.command()
@click.pass_context
def status(ctx):
    """Show folder statistics and pending work."""
    config = ctx.obj["config"]

    console.print(Panel.fit(
        f"[bold blue]kdv[/bold blue] v{__version__}",
        title="Kdenlive Video Workflow",
    ))

    # Folder statistics table
    table = Table(title="Folder Statistics", show_header=True)
    table.add_column("Folder", style="cyan")
    table.add_column("Files", justify="right")
    table.add_column("Size", justify="right", style="green")

    folders = [
        ("Raw Footage", config.raw_dir),
        ("B-Roll", config.broll_dir),
        ("Proxies", config.proxy_dir),
        ("Archive", config.archive_dir),
    ]

    total_files = 0
    total_size = 0

    for name, path in folders:
        count, size = get_folder_stats(path)
        total_files += count
        total_size += size
        status_str = f"{count}" if path.exists() else "[dim]not found[/dim]"
        size_str = format_size(size) if path.exists() else "-"
        table.add_row(name, status_str, size_str)

    table.add_row("", "", "", end_section=True)
    table.add_row("[bold]Total[/bold]", f"[bold]{total_files}[/bold]", f"[bold]{format_size(total_size)}[/bold]")

    console.print(table)

    # Check for files needing conversion
    raw_dir = config.raw_dir
    if raw_dir.exists():
        needs_convert = []
        for f in raw_dir.glob("*.mp4"):
            if "-30fps" not in f.name:
                converted = f.with_name(f.stem + "-30fps.mp4")
                if not converted.exists():
                    needs_convert.append(f.name)

        if needs_convert:
            console.print(f"\n[yellow]Files needing conversion:[/yellow] {len(needs_convert)}")
            for name in needs_convert[:5]:
                console.print(f"  • {name}")
            if len(needs_convert) > 5:
                console.print(f"  [dim]... and {len(needs_convert) - 5} more[/dim]")

    # Check for files needing proxies
    proxy_dir = config.proxy_dir
    if raw_dir.exists():
        needs_proxy = []
        for f in raw_dir.glob("*.mp4"):
            proxy_file = proxy_dir / f"{f.stem}.proxy.mp4"
            if not proxy_file.exists():
                needs_proxy.append(f.name)

        if needs_proxy:
            console.print(f"\n[yellow]Files needing proxies:[/yellow] {len(needs_proxy)}")

    # Projects info
    projects_dir = config.projects_dir
    if projects_dir.exists():
        projects = list(projects_dir.glob("*.kdenlive"))
        if projects:
            console.print(f"\n[blue]Kdenlive Projects:[/blue] {len(projects)}")
            for p in projects:
                console.print(f"  • {p.name}")


@cli.command()
@click.argument("files", nargs=-1, type=click.Path(exists=True))
@click.option("--all", "-a", "process_all", is_flag=True, help="Process all files in raw directory")
@click.option("--quality", "-q", type=click.Choice(["fast", "balanced", "quality"]), default="balanced")
@click.pass_context
def convert(ctx, files, process_all, quality):
    """Convert video files to target frame rate (60fps → 30fps)."""
    from kdv.convert import convert_files
    config = ctx.obj["config"]

    if process_all:
        files = list(config.raw_dir.glob("*.mp4"))
        files = [f for f in files if "-30fps" not in f.name]
    elif not files:
        console.print("[red]Error:[/red] No files specified. Use --all or provide file paths.")
        return

    convert_files(files, quality=quality, config=config)


@cli.command()
@click.argument("files", nargs=-1, type=click.Path(exists=True))
@click.option("--all", "-a", "process_all", is_flag=True, help="Process all files in raw directory")
@click.option("--resolution", "-r", type=click.Choice(["540", "720", "1080"]), default="540")
@click.pass_context
def proxy(ctx, files, process_all, resolution):
    """Generate lightweight proxy files for editing."""
    from kdv.proxy import generate_proxies
    config = ctx.obj["config"]

    if process_all:
        files = list(config.raw_dir.glob("*.mp4"))
    elif not files:
        console.print("[red]Error:[/red] No files specified. Use --all or provide file paths.")
        return

    generate_proxies(files, resolution=int(resolution), config=config)


@cli.command()
@click.argument("files", nargs=-1, type=click.Path(exists=True))
@click.option("--all", "-a", "process_all", is_flag=True, help="Process all files in raw directory")
@click.option("--output", "-o", type=click.Path(), help="Output JSON file path")
@click.pass_context
def meta(ctx, files, process_all, output):
    """Extract metadata from video files."""
    from kdv.metadata import extract_metadata
    config = ctx.obj["config"]

    if process_all:
        files = list(config.raw_dir.glob("*.mp4"))
    elif not files:
        console.print("[red]Error:[/red] No files specified. Use --all or provide file paths.")
        return

    extract_metadata(files, output_path=output, config=config)


@cli.command()
@click.argument("files", nargs=-1, type=click.Path(exists=True))
@click.option("--all", "-a", "process_all", is_flag=True, help="Process all files in raw directory")
@click.option("--contact-sheet", "-c", is_flag=True, help="Generate contact sheets")
@click.pass_context
def thumbs(ctx, files, process_all, contact_sheet):
    """Generate thumbnails and contact sheets."""
    from kdv.thumbnails import generate_thumbnails
    config = ctx.obj["config"]

    if process_all:
        files = list(config.raw_dir.glob("*.mp4"))
    elif not files:
        console.print("[red]Error:[/red] No files specified. Use --all or provide file paths.")
        return

    generate_thumbnails(files, contact_sheet=contact_sheet, config=config)


@cli.command()
@click.argument("source", type=click.Path(exists=True))
@click.option("--move", is_flag=True, help="Move files instead of copying")
@click.option("--verify", is_flag=True, default=True, help="Verify file integrity after copy")
@click.pass_context
def ingest(ctx, source, move, verify):
    """Import footage from a source directory or SD card."""
    from kdv.ingest import ingest_footage
    config = ctx.obj["config"]

    ingest_footage(source, move=move, verify=verify, config=config)


@cli.command()
@click.argument("project", type=click.Path(exists=True))
@click.option("--output-dir", "-o", type=click.Path(), help="Output directory for clips")
@click.option("--interactive", "-i", is_flag=True, help="Interactively categorize clips")
@click.pass_context
def extract(ctx, project, output_dir, interactive):
    """Extract marked clips from a Kdenlive project."""
    from kdv.extract import extract_clips
    config = ctx.obj["config"]

    extract_clips(project, output_dir=output_dir, interactive=interactive, config=config)


@cli.command(name="export")
@click.argument("project", type=click.Path(exists=True))
@click.option("--preset", "-p", type=str, default="youtube-1080", help="Export preset name")
@click.option("--output", "-o", type=click.Path(), help="Output file path")
@click.pass_context
def export_cmd(ctx, project, preset, output):
    """Render a Kdenlive project with preset settings."""
    from kdv.export import export_project
    config = ctx.obj["config"]

    export_project(project, preset=preset, output_path=output, config=config)


if __name__ == "__main__":
    cli()
