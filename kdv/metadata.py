"""
Metadata extraction for video files.
"""

import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

from kdv.config import Config

console = Console()


def run_ffprobe(file_path: Path) -> dict:
    """Run ffprobe and return parsed JSON output."""
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(file_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr}")

    return json.loads(result.stdout)


def parse_duration(duration_str: str) -> str:
    """Convert duration in seconds to HH:MM:SS format."""
    try:
        total_seconds = float(duration_str)
        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)
        seconds = total_seconds % 60
        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:05.2f}"
        return f"{minutes}:{seconds:05.2f}"
    except (ValueError, TypeError):
        return "unknown"


def get_video_metadata(file_path: Path) -> dict:
    """Extract comprehensive metadata from a video file."""
    probe_data = run_ffprobe(file_path)

    # Find video and audio streams
    video_stream = None
    audio_stream = None
    for stream in probe_data.get("streams", []):
        if stream.get("codec_type") == "video" and video_stream is None:
            video_stream = stream
        elif stream.get("codec_type") == "audio" and audio_stream is None:
            audio_stream = stream

    format_data = probe_data.get("format", {})

    # Calculate FPS
    fps = None
    if video_stream:
        fps_str = video_stream.get("r_frame_rate", "0/1")
        try:
            num, den = map(int, fps_str.split("/"))
            fps = round(num / den, 2) if den else None
        except (ValueError, ZeroDivisionError):
            fps = None

    # File stats
    stat = file_path.stat()

    metadata = {
        "filename": file_path.name,
        "path": str(file_path.absolute()),
        "size_bytes": stat.st_size,
        "size_human": format_size(stat.st_size),
        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        "duration_seconds": float(format_data.get("duration", 0)),
        "duration_human": parse_duration(format_data.get("duration", "0")),
        "bitrate": int(format_data.get("bit_rate", 0)),
        "bitrate_human": format_bitrate(format_data.get("bit_rate")),
        "format": format_data.get("format_name", "unknown"),
    }

    if video_stream:
        metadata["video"] = {
            "codec": video_stream.get("codec_name", "unknown"),
            "width": video_stream.get("width"),
            "height": video_stream.get("height"),
            "resolution": f"{video_stream.get('width')}x{video_stream.get('height')}",
            "fps": fps,
            "pixel_format": video_stream.get("pix_fmt"),
            "profile": video_stream.get("profile"),
        }

    if audio_stream:
        metadata["audio"] = {
            "codec": audio_stream.get("codec_name", "unknown"),
            "channels": audio_stream.get("channels"),
            "sample_rate": audio_stream.get("sample_rate"),
        }

    # Check for GPS/location data in format tags
    tags = format_data.get("tags", {})
    if "location" in tags:
        metadata["gps"] = tags["location"]
    elif "com.apple.quicktime.location.ISO6709" in tags:
        metadata["gps"] = tags["com.apple.quicktime.location.ISO6709"]

    return metadata


def format_size(size_bytes: int) -> str:
    """Format bytes as human-readable size."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"


def format_bitrate(bitrate: Any) -> str:
    """Format bitrate as human-readable string."""
    if not bitrate:
        return "unknown"
    try:
        br = int(bitrate)
        if br >= 1_000_000:
            return f"{br / 1_000_000:.1f} Mbps"
        return f"{br / 1_000:.0f} kbps"
    except (ValueError, TypeError):
        return "unknown"


def extract_metadata(
    files: list,
    output_path: Optional[str] = None,
    config: Optional[Config] = None,
) -> list[dict]:
    """Extract metadata from multiple files."""
    files = [Path(f) for f in files]
    results = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Extracting metadata...", total=len(files))

        for file_path in files:
            progress.update(task, description=f"Processing {file_path.name}...")
            try:
                metadata = get_video_metadata(file_path)
                results.append(metadata)
            except Exception as e:
                console.print(f"[red]Error processing {file_path.name}:[/red] {e}")
                results.append({"filename": file_path.name, "error": str(e)})

            progress.advance(task)

    # Display results table
    table = Table(title="Video Metadata", show_header=True)
    table.add_column("File", style="cyan", max_width=40)
    table.add_column("Resolution", justify="center")
    table.add_column("FPS", justify="right")
    table.add_column("Duration", justify="right")
    table.add_column("Size", justify="right", style="green")
    table.add_column("Bitrate", justify="right")

    for meta in results:
        if "error" in meta:
            table.add_row(meta["filename"], "[red]error[/red]", "-", "-", "-", "-")
        else:
            video = meta.get("video", {})
            table.add_row(
                meta["filename"],
                video.get("resolution", "-"),
                str(video.get("fps", "-")),
                meta.get("duration_human", "-"),
                meta.get("size_human", "-"),
                meta.get("bitrate_human", "-"),
            )

    console.print(table)

    # Save to JSON if requested
    if output_path:
        output_file = Path(output_path)
        with open(output_file, "w") as f:
            json.dump(results, f, indent=2)
        console.print(f"\n[green]Saved metadata to:[/green] {output_file}")
    elif config:
        # Auto-save to catalog.json in thumbnails dir
        catalog_file = config.thumbnails_dir / "catalog.json"
        catalog_file.parent.mkdir(parents=True, exist_ok=True)
        with open(catalog_file, "w") as f:
            json.dump(results, f, indent=2)
        console.print(f"\n[green]Saved catalog to:[/green] {catalog_file}")

    return results
