"""
Thumbnail and contact sheet generation.
"""

import subprocess
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.progress import Progress, BarColumn, TextColumn, TimeRemainingColumn

from kdv.config import Config

console = Console()


def generate_single_thumbnail(
    file_path: Path,
    output_path: Path,
    timestamp: str = "00:00:03",
    quality: int = 85,
) -> bool:
    """Generate a single thumbnail from a video file."""
    cmd = [
        "ffmpeg",
        "-y",
        "-ss", timestamp,
        "-i", str(file_path),
        "-vframes", "1",
        "-q:v", str(int((100 - quality) / 100 * 31)),  # Convert quality to FFmpeg scale
        str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0


def generate_contact_sheet(
    file_path: Path,
    output_path: Path,
    cols: int = 4,
    rows: int = 4,
    width: int = 1920,
) -> bool:
    """Generate a contact sheet (grid of frames) from a video file."""
    # First, get video duration
    probe_cmd = [
        "ffprobe",
        "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "csv=p=0",
        str(file_path),
    ]
    probe_result = subprocess.run(probe_cmd, capture_output=True, text=True)
    if probe_result.returncode != 0:
        return False

    try:
        duration = float(probe_result.stdout.strip())
    except ValueError:
        return False

    # Calculate frame interval
    total_frames = cols * rows
    interval = duration / (total_frames + 1)  # +1 to avoid first/last frames

    # Calculate tile dimensions
    tile_width = width // cols

    # Build FFmpeg filter for contact sheet
    # Uses the tile filter to create a grid
    filter_complex = (
        f"select='not(mod(n\\,{int(duration * 30 / total_frames)}))',"  # Select evenly spaced frames
        f"scale={tile_width}:-1,"
        f"tile={cols}x{rows}"
    )

    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(file_path),
        "-vf", filter_complex,
        "-frames:v", "1",
        "-q:v", "2",
        str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0


def generate_contact_sheet_simple(
    file_path: Path,
    output_path: Path,
    cols: int = 4,
    rows: int = 4,
    width: int = 1920,
) -> bool:
    """Generate contact sheet using fps filter (simpler, more reliable)."""
    # Get video duration
    probe_cmd = [
        "ffprobe",
        "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "csv=p=0",
        str(file_path),
    ]
    probe_result = subprocess.run(probe_cmd, capture_output=True, text=True)
    if probe_result.returncode != 0:
        return False

    try:
        duration = float(probe_result.stdout.strip())
    except ValueError:
        return False

    total_frames = cols * rows
    fps_rate = total_frames / duration

    tile_width = width // cols

    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(file_path),
        "-vf", f"fps={fps_rate},scale={tile_width}:-1,tile={cols}x{rows}",
        "-frames:v", "1",
        "-q:v", "2",
        str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0


def generate_thumbnails(
    files: list,
    contact_sheet: bool = False,
    config: Optional[Config] = None,
) -> dict:
    """Generate thumbnails for multiple video files."""
    files = [Path(f) for f in files]

    # Get settings from config
    if config:
        thumb_dir = config.thumbnails_dir
        timestamp = config.get("thumbnails.timestamp", "00:00:03")
        quality = config.get("thumbnails.quality", 85)
        cs_settings = config.get("thumbnails.contact_sheet", {})
        cs_cols = cs_settings.get("cols", 4)
        cs_rows = cs_settings.get("rows", 4)
        cs_width = cs_settings.get("width", 1920)
        contact_sheet = contact_sheet or cs_settings.get("enabled", False)
    else:
        thumb_dir = Path(".thumbnails")
        timestamp = "00:00:03"
        quality = 85
        cs_cols, cs_rows, cs_width = 4, 4, 1920

    thumb_dir.mkdir(parents=True, exist_ok=True)

    results = {"success": [], "failed": []}

    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Generating thumbnails...", total=len(files))

        for file_path in files:
            progress.update(task, description=f"Processing {file_path.name}...")

            # Generate single thumbnail
            thumb_path = thumb_dir / f"{file_path.stem}.jpg"
            if generate_single_thumbnail(file_path, thumb_path, timestamp, quality):
                results["success"].append(str(thumb_path))

                # Generate contact sheet if requested
                if contact_sheet:
                    cs_path = thumb_dir / f"{file_path.stem}_contact.jpg"
                    if generate_contact_sheet_simple(file_path, cs_path, cs_cols, cs_rows, cs_width):
                        results["success"].append(str(cs_path))
                    else:
                        console.print(f"[yellow]Warning:[/yellow] Contact sheet failed for {file_path.name}")
            else:
                results["failed"].append(file_path.name)

            progress.advance(task)

    # Summary
    console.print(f"\n[green]Generated {len(results['success'])} thumbnails[/green]")
    if results["failed"]:
        console.print(f"[red]Failed: {len(results['failed'])} files[/red]")
        for name in results["failed"]:
            console.print(f"  • {name}")

    console.print(f"\n[blue]Thumbnails saved to:[/blue] {thumb_dir}")

    return results


def generate_html_gallery(
    thumb_dir: Path,
    output_path: Optional[Path] = None,
) -> Path:
    """Generate an HTML gallery from thumbnails."""
    if output_path is None:
        output_path = thumb_dir / "gallery.html"

    thumbnails = sorted(thumb_dir.glob("*.jpg"))
    # Filter out contact sheets for main gallery
    main_thumbs = [t for t in thumbnails if "_contact" not in t.name]

    html = """<!DOCTYPE html>
<html>
<head>
    <title>Video Thumbnail Gallery</title>
    <style>
        body { font-family: system-ui; background: #1a1a1a; color: #fff; padding: 20px; }
        h1 { text-align: center; }
        .gallery { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 20px; }
        .item { background: #2a2a2a; border-radius: 8px; overflow: hidden; }
        .item img { width: 100%; display: block; }
        .item .name { padding: 10px; font-size: 14px; word-break: break-all; }
    </style>
</head>
<body>
    <h1>Video Thumbnails</h1>
    <div class="gallery">
"""

    for thumb in main_thumbs:
        html += f"""        <div class="item">
            <img src="{thumb.name}" alt="{thumb.stem}">
            <div class="name">{thumb.stem}</div>
        </div>
"""

    html += """    </div>
</body>
</html>"""

    with open(output_path, "w") as f:
        f.write(html)

    console.print(f"[green]Generated gallery:[/green] {output_path}")
    return output_path
