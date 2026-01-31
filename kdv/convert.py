"""
Frame rate conversion for video files.
"""

import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.progress import Progress, BarColumn, TextColumn, TimeRemainingColumn, TaskID

from kdv.config import Config

console = Console()


def get_video_info(file_path: Path) -> dict:
    """Get video duration and frame rate."""
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-show_entries", "format=duration:stream=r_frame_rate",
        "-select_streams", "v:0",
        "-of", "csv=p=0",
        str(file_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return {}

    lines = result.stdout.strip().split("\n")
    info = {}

    for line in lines:
        if "/" in line:  # Frame rate
            try:
                num, den = map(int, line.split("/"))
                info["fps"] = num / den if den else 0
            except ValueError:
                pass
        else:  # Duration
            try:
                info["duration"] = float(line)
            except ValueError:
                pass

    return info


def convert_single_file(
    input_path: Path,
    output_path: Path,
    target_fps: int,
    quality: str,
    progress: Progress,
    task_id: TaskID,
) -> bool:
    """Convert a single video file to target frame rate."""
    # Get quality settings
    quality_presets = {
        "fast": {"crf": "23", "preset": "fast"},
        "balanced": {"crf": "18", "preset": "medium"},
        "quality": {"crf": "15", "preset": "slow"},
    }
    settings = quality_presets.get(quality, quality_presets["balanced"])

    # Get video duration for progress
    info = get_video_info(input_path)
    duration = info.get("duration", 0)

    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(input_path),
        "-r", str(target_fps),
        "-c:v", "libx264",
        "-crf", settings["crf"],
        "-preset", settings["preset"],
        "-c:a", "aac",
        "-b:a", "256k",
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

    # Parse ffmpeg progress output
    current_time = 0
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


def convert_files(
    files: list,
    quality: str = "balanced",
    config: Optional[Config] = None,
) -> dict:
    """Convert multiple video files to target frame rate."""
    files = [Path(f) for f in files]

    # Get target FPS from config
    target_fps = 30
    if config:
        target_fps = config.get("conversion.target_fps", 30)

    results = {"success": [], "skipped": [], "failed": []}

    # Filter out already converted files
    to_convert = []
    for f in files:
        if "-30fps" in f.name:
            results["skipped"].append(f.name)
            continue

        output_path = f.with_name(f"{f.stem}-{target_fps}fps{f.suffix}")
        if output_path.exists():
            results["skipped"].append(f.name)
            console.print(f"[dim]Skipping {f.name} (already converted)[/dim]")
            continue

        to_convert.append((f, output_path))

    if not to_convert:
        console.print("[yellow]No files to convert.[/yellow]")
        return results

    console.print(f"\n[blue]Converting {len(to_convert)} files to {target_fps}fps[/blue]")
    console.print(f"[dim]Quality preset: {quality}[/dim]\n")

    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        for input_path, output_path in to_convert:
            task = progress.add_task(f"Converting {input_path.name}...", total=100)

            if convert_single_file(input_path, output_path, target_fps, quality, progress, task):
                results["success"].append(output_path.name)
                console.print(f"[green]✓[/green] {output_path.name}")
            else:
                results["failed"].append(input_path.name)
                console.print(f"[red]✗[/red] {input_path.name}")
                # Clean up partial file
                if output_path.exists():
                    output_path.unlink()

    # Summary
    console.print(f"\n[bold]Conversion complete:[/bold]")
    console.print(f"  [green]Success:[/green] {len(results['success'])}")
    if results["skipped"]:
        console.print(f"  [yellow]Skipped:[/yellow] {len(results['skipped'])}")
    if results["failed"]:
        console.print(f"  [red]Failed:[/red] {len(results['failed'])}")

    return results
