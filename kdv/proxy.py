"""
Proxy generation for video files.
"""

import subprocess
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.progress import Progress, BarColumn, TextColumn, TimeRemainingColumn, TaskID

from kdv.config import Config

console = Console()


def get_video_duration(file_path: Path) -> float:
    """Get video duration in seconds."""
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "csv=p=0",
        str(file_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0


def generate_single_proxy(
    input_path: Path,
    output_path: Path,
    resolution: int,
    crf: int,
    preset: str,
    progress: Progress,
    task_id: TaskID,
) -> bool:
    """Generate a proxy file for a single video."""
    duration = get_video_duration(input_path)

    # Scale to target height while maintaining aspect ratio
    scale_filter = f"scale=-2:{resolution}"

    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(input_path),
        "-vf", scale_filter,
        "-c:v", "libx264",
        "-crf", str(crf),
        "-preset", preset,
        "-c:a", "aac",
        "-b:a", "128k",
        "-progress", "pipe:1",
        "-nostats",
        str(output_path),
    ]

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )

    while True:
        line = process.stdout.readline()
        if not line and process.poll() is not None:
            break

        if line.startswith("out_time_ms="):
            try:
                time_ms = int(line.split("=")[1])
                current_time = time_ms / 1_000_000
                if duration > 0:
                    pct = min(current_time / duration, 1.0)
                    progress.update(task_id, completed=pct * 100)
            except (ValueError, IndexError):
                pass

    process.wait()
    progress.update(task_id, completed=100)

    return process.returncode == 0


def generate_proxies(
    files: list,
    resolution: int = 540,
    config: Optional[Config] = None,
) -> dict:
    """Generate proxy files for multiple videos."""
    files = [Path(f) for f in files]

    # Get settings from config
    if config:
        proxy_dir = config.proxy_dir
        resolution = config.get("proxy.resolution", resolution)
        crf = config.get("proxy.crf", 28)
        preset = config.get("proxy.preset", "ultrafast")
    else:
        proxy_dir = Path("proxy")
        crf = 28
        preset = "ultrafast"

    proxy_dir.mkdir(parents=True, exist_ok=True)

    results = {"success": [], "skipped": [], "failed": []}

    # Check which files need proxies
    to_process = []
    for f in files:
        proxy_path = proxy_dir / f"{f.stem}.proxy.mp4"
        if proxy_path.exists():
            results["skipped"].append(f.name)
            continue
        to_process.append((f, proxy_path))

    if not to_process:
        console.print("[yellow]All files already have proxies.[/yellow]")
        return results

    console.print(f"\n[blue]Generating {len(to_process)} proxy files[/blue]")
    console.print(f"[dim]Resolution: {resolution}p | CRF: {crf} | Preset: {preset}[/dim]\n")

    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        for input_path, proxy_path in to_process:
            task = progress.add_task(f"Generating proxy for {input_path.name}...", total=100)

            if generate_single_proxy(input_path, proxy_path, resolution, crf, preset, progress, task):
                results["success"].append(proxy_path.name)
                # Show size comparison
                original_size = input_path.stat().st_size
                proxy_size = proxy_path.stat().st_size
                ratio = (1 - proxy_size / original_size) * 100
                console.print(
                    f"[green]✓[/green] {proxy_path.name} "
                    f"[dim]({format_size(proxy_size)}, {ratio:.0f}% smaller)[/dim]"
                )
            else:
                results["failed"].append(input_path.name)
                console.print(f"[red]✗[/red] {input_path.name}")
                if proxy_path.exists():
                    proxy_path.unlink()

    # Summary
    console.print(f"\n[bold]Proxy generation complete:[/bold]")
    console.print(f"  [green]Success:[/green] {len(results['success'])}")
    if results["skipped"]:
        console.print(f"  [yellow]Skipped:[/yellow] {len(results['skipped'])}")
    if results["failed"]:
        console.print(f"  [red]Failed:[/red] {len(results['failed'])}")

    console.print(f"\n[blue]Proxies saved to:[/blue] {proxy_dir}")

    return results


def format_size(size_bytes: int) -> str:
    """Format bytes as human-readable size."""
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def link_proxies_to_project(project_path: Path, proxy_dir: Path) -> int:
    """
    Update a Kdenlive project file to use proxy files.

    Returns the number of clips updated.
    """
    import xml.etree.ElementTree as ET

    tree = ET.parse(project_path)
    root = tree.getroot()

    updated = 0

    # Find all producer elements (clips)
    for producer in root.iter("producer"):
        # Get the resource property
        for prop in producer.findall("property"):
            if prop.get("name") == "resource":
                original_path = Path(prop.text)
                proxy_path = proxy_dir / f"{original_path.stem}.proxy.mp4"

                if proxy_path.exists():
                    # Add or update kdenlive:proxy property
                    proxy_prop = None
                    for p in producer.findall("property"):
                        if p.get("name") == "kdenlive:proxy":
                            proxy_prop = p
                            break

                    if proxy_prop is None:
                        proxy_prop = ET.SubElement(producer, "property")
                        proxy_prop.set("name", "kdenlive:proxy")

                    proxy_prop.text = str(proxy_path.absolute())
                    updated += 1

    if updated > 0:
        # Backup original
        backup_path = project_path.with_suffix(".kdenlive.bak")
        import shutil
        shutil.copy2(project_path, backup_path)

        # Write updated project
        tree.write(project_path, encoding="unicode", xml_declaration=True)
        console.print(f"[green]Updated {updated} clips with proxy references[/green]")
        console.print(f"[dim]Backup saved to: {backup_path}[/dim]")

    return updated
