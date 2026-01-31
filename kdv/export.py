"""
Export automation for Kdenlive projects.
"""

import subprocess
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.progress import Progress, BarColumn, TextColumn, TimeRemainingColumn
from rich.table import Table

from kdv.config import Config

console = Console()


def check_melt_available() -> bool:
    """Check if melt (MLT command-line tool) is available."""
    result = subprocess.run(["which", "melt"], capture_output=True)
    return result.returncode == 0


def get_project_duration(project_path: Path) -> float:
    """Get total duration of project in seconds."""
    tree = ET.parse(project_path)
    root = tree.getroot()

    # Get FPS
    fps = 30.0
    for profile in root.iter("profile"):
        frame_rate_num = profile.get("frame_rate_num", "30")
        frame_rate_den = profile.get("frame_rate_den", "1")
        try:
            fps = int(frame_rate_num) / int(frame_rate_den)
        except (ValueError, ZeroDivisionError):
            pass
        break

    # Find main tractor length
    for tractor in root.iter("tractor"):
        out_attr = tractor.get("out")
        if out_attr:
            try:
                frames = int(out_attr)
                return frames / fps
            except ValueError:
                pass

    return 0


def list_presets(config: Config) -> None:
    """Display available export presets."""
    presets = config.get("export.presets", {})
    default = config.get("export.default_preset", "youtube-1080")

    table = Table(title="Export Presets", show_header=True)
    table.add_column("Name", style="cyan")
    table.add_column("Resolution")
    table.add_column("Bitrate", justify="right")
    table.add_column("Codec")
    table.add_column("Default", justify="center")

    for name, settings in presets.items():
        is_default = "✓" if name == default else ""
        table.add_row(
            name,
            settings.get("resolution", "original"),
            settings.get("video_bitrate", "-"),
            settings.get("codec", "libx264"),
            is_default,
        )

    console.print(table)


def export_with_ffmpeg(
    project_path: Path,
    output_path: Path,
    preset: dict,
    progress: Progress,
    task_id,
) -> bool:
    """
    Export using FFmpeg (requires pre-rendered intermediate).

    Note: This is a fallback when melt is not available.
    For best results, use Kdenlive's built-in render or melt.
    """
    console.print("[yellow]Warning:[/yellow] melt not available, using FFmpeg fallback")
    console.print("[dim]For best results, render from Kdenlive directly[/dim]")

    # This would need an intermediate file - not fully implementable without melt
    return False


def export_with_melt(
    project_path: Path,
    output_path: Path,
    preset: dict,
    progress: Progress,
    task_id,
) -> bool:
    """Export Kdenlive project using melt."""
    duration = get_project_duration(project_path)

    # Build melt command
    resolution = preset.get("resolution", "1920x1080")
    video_bitrate = preset.get("video_bitrate", "12M")
    audio_bitrate = preset.get("audio_bitrate", "256k")
    codec = preset.get("codec", "libx264")
    melt_preset = preset.get("preset", "medium")
    profile = preset.get("profile", "high")

    # Parse resolution
    if resolution != "original":
        width, height = resolution.split("x")
        scale_filter = f"scale={width}:{height}"
    else:
        scale_filter = None

    cmd = [
        "melt",
        str(project_path),
        "-consumer", f"avformat:{output_path}",
        f"vcodec={codec}",
        f"b={video_bitrate}",
        f"acodec=aac",
        f"ab={audio_bitrate}",
        f"preset={melt_preset}",
        f"profile={profile}",
    ]

    if scale_filter:
        cmd.extend([f"s={resolution}"])

    # Add progress reporting
    cmd.extend(["-progress"])

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
    )

    # Parse melt progress output
    while True:
        line = process.stdout.readline()
        if not line and process.poll() is not None:
            break

        # Melt outputs "Current Frame: NNNN"
        if "Current Frame:" in line or "percentage:" in line:
            try:
                if "percentage:" in line:
                    pct = float(line.split(":")[1].strip())
                    progress.update(task_id, completed=pct)
            except (ValueError, IndexError):
                pass

    process.wait()
    progress.update(task_id, completed=100)

    return process.returncode == 0


def export_project(
    project: str,
    preset: str = "youtube-1080",
    output_path: Optional[str] = None,
    config: Optional[Config] = None,
) -> dict:
    """Export a Kdenlive project with preset settings."""
    project_path = Path(project)

    if not project_path.exists():
        console.print(f"[red]Error:[/red] Project not found: {project}")
        return {"success": False}

    # Get preset settings
    if config:
        try:
            preset_settings = config.get_export_preset(preset)
        except KeyError:
            console.print(f"[red]Error:[/red] Unknown preset: {preset}")
            list_presets(config)
            return {"success": False}
    else:
        # Default preset
        preset_settings = {
            "resolution": "1920x1080",
            "fps": 30,
            "video_bitrate": "12M",
            "audio_bitrate": "256k",
            "codec": "libx264",
            "preset": "medium",
            "profile": "high",
        }

    # Determine output path
    if output_path:
        out_file = Path(output_path)
    else:
        # Auto-generate output name
        date_str = datetime.now().strftime("%Y%m%d")
        out_name = f"{project_path.stem}_{preset}_{date_str}.mp4"
        out_file = project_path.parent / out_name

    console.print(f"\n[blue]Exporting project:[/blue] {project_path.name}")
    console.print(f"  Preset: {preset}")
    console.print(f"  Resolution: {preset_settings.get('resolution')}")
    console.print(f"  Video bitrate: {preset_settings.get('video_bitrate')}")
    console.print(f"  Output: {out_file}")

    # Check for melt
    has_melt = check_melt_available()

    if not has_melt:
        console.print("\n[yellow]Note:[/yellow] melt is not installed.")
        console.print("For command-line rendering, install MLT framework:")
        console.print("  [dim]brew install mlt[/dim]")
        console.print("\nAlternatively, render directly from Kdenlive:")
        console.print(f"  1. Open {project_path.name} in Kdenlive")
        console.print(f"  2. Go to Project → Render")
        console.print(f"  3. Configure output settings and click Render")

        # Generate render script for later use
        script_path = project_path.with_suffix(".render.sh")
        with open(script_path, "w") as f:
            f.write("#!/bin/bash\n")
            f.write(f"# Render script for {project_path.name}\n")
            f.write(f"# Run after installing melt: brew install mlt\n\n")
            f.write(f'melt "{project_path}" \\\n')
            f.write(f'  -consumer avformat:"{out_file}" \\\n')
            f.write(f'  vcodec={preset_settings.get("codec", "libx264")} \\\n')
            f.write(f'  b={preset_settings.get("video_bitrate", "12M")} \\\n')
            f.write(f'  acodec=aac \\\n')
            f.write(f'  ab={preset_settings.get("audio_bitrate", "256k")} \\\n')
            f.write(f'  preset={preset_settings.get("preset", "medium")}\n')

        script_path.chmod(0o755)
        console.print(f"\n[green]Generated render script:[/green] {script_path}")

        return {"success": False, "script": str(script_path)}

    # Export with melt
    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Rendering...", total=100)

        success = export_with_melt(
            project_path,
            out_file,
            preset_settings,
            progress,
            task,
        )

    if success:
        file_size = out_file.stat().st_size
        console.print(f"\n[green]Export complete:[/green] {out_file}")
        console.print(f"  Size: {format_size(file_size)}")
        return {"success": True, "output": str(out_file)}
    else:
        console.print(f"\n[red]Export failed[/red]")
        return {"success": False}


def format_size(size_bytes: int) -> str:
    """Format bytes as human-readable size."""
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"
