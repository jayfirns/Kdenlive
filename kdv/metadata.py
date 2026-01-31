"""
Metadata extraction and catalog management for video files.
"""

import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Prompt

from kdv.config import Config

console = Console()


# Enhanced catalog schema adds user annotations
ANNOTATION_FIELDS = {
    "tags": [],           # User tags like ["hero-shot", "sunset", "family"]
    "rating": None,       # 1-5 star rating
    "notes": "",          # Free-form notes
    "motion_type": None,  # Ascending, Descending, PushIn, etc.
    "vibe": None,         # Calm, Epic, Energetic, etc.
    "usable": True,       # Mark clips as usable/unusable
    "used_in": [],        # List of projects this clip appears in
}


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


def load_catalog(config: Config) -> list[dict]:
    """Load the catalog from disk."""
    catalog_file = config.thumbnails_dir / "catalog.json"
    if not catalog_file.exists():
        return []
    with open(catalog_file) as f:
        return json.load(f)


def save_catalog(catalog: list[dict], config: Config) -> None:
    """Save the catalog to disk."""
    catalog_file = config.thumbnails_dir / "catalog.json"
    catalog_file.parent.mkdir(parents=True, exist_ok=True)
    with open(catalog_file, "w") as f:
        json.dump(catalog, f, indent=2)


def get_clip_by_name(catalog: list[dict], name: str) -> Optional[dict]:
    """Find a clip in the catalog by filename (partial match)."""
    name_lower = name.lower()
    for clip in catalog:
        if name_lower in clip.get("filename", "").lower():
            return clip
    return None


def annotate_clip(
    clip_name: str,
    tags: Optional[list[str]] = None,
    rating: Optional[int] = None,
    notes: Optional[str] = None,
    motion_type: Optional[str] = None,
    vibe: Optional[str] = None,
    usable: Optional[bool] = None,
    config: Optional[Config] = None,
) -> bool:
    """Add annotations to a clip in the catalog."""
    if not config:
        from kdv.config import get_config
        config = get_config()

    catalog = load_catalog(config)
    clip = get_clip_by_name(catalog, clip_name)

    if not clip:
        console.print(f"[red]Clip not found:[/red] {clip_name}")
        return False

    # Ensure annotation fields exist
    for field, default in ANNOTATION_FIELDS.items():
        if field not in clip:
            clip[field] = default if not isinstance(default, list) else []

    # Update provided fields
    if tags is not None:
        clip["tags"] = list(set(clip.get("tags", []) + tags))
    if rating is not None:
        clip["rating"] = max(1, min(5, rating))
    if notes is not None:
        clip["notes"] = notes
    if motion_type is not None:
        clip["motion_type"] = motion_type
    if vibe is not None:
        clip["vibe"] = vibe
    if usable is not None:
        clip["usable"] = usable

    save_catalog(catalog, config)
    console.print(f"[green]Updated:[/green] {clip['filename']}")
    return True


def show_catalog_summary(config: Config) -> None:
    """Display a summary of the catalog with statistics."""
    catalog = load_catalog(config)

    if not catalog:
        console.print("[yellow]Catalog is empty. Run 'kdv meta --all' first.[/yellow]")
        return

    # Calculate statistics
    total_clips = len(catalog)
    total_duration = sum(c.get("duration_seconds", 0) for c in catalog)
    total_size = sum(c.get("size_bytes", 0) for c in catalog)

    # Count by status
    converted = sum(1 for c in catalog if "-30fps" in c.get("filename", ""))
    originals = total_clips - converted
    rated = sum(1 for c in catalog if c.get("rating"))
    tagged = sum(1 for c in catalog if c.get("tags"))
    with_motion = sum(1 for c in catalog if c.get("motion_type"))
    with_vibe = sum(1 for c in catalog if c.get("vibe"))
    unusable = sum(1 for c in catalog if c.get("usable") is False)

    # Collect all tags
    all_tags = {}
    for clip in catalog:
        for tag in clip.get("tags", []):
            all_tags[tag] = all_tags.get(tag, 0) + 1

    # Display summary
    console.print(Panel.fit(
        f"[bold]Catalog Summary[/bold]\n"
        f"Total clips: {total_clips}\n"
        f"Total duration: {format_duration(total_duration)}\n"
        f"Total size: {format_size(total_size)}",
        title="kdv catalog",
    ))

    # Status table
    status_table = Table(title="Clip Status", show_header=True)
    status_table.add_column("Category", style="cyan")
    status_table.add_column("Count", justify="right")
    status_table.add_column("Percentage", justify="right")

    status_table.add_row("Original files", str(originals), f"{originals/total_clips*100:.0f}%")
    status_table.add_row("30fps converted", str(converted), f"{converted/total_clips*100:.0f}%")
    status_table.add_row("Rated", str(rated), f"{rated/total_clips*100:.0f}%")
    status_table.add_row("Tagged", str(tagged), f"{tagged/total_clips*100:.0f}%")
    status_table.add_row("Motion classified", str(with_motion), f"{with_motion/total_clips*100:.0f}%")
    status_table.add_row("Vibe classified", str(with_vibe), f"{with_vibe/total_clips*100:.0f}%")
    if unusable:
        status_table.add_row("[red]Marked unusable[/red]", str(unusable), f"{unusable/total_clips*100:.0f}%")

    console.print(status_table)

    # Tags cloud
    if all_tags:
        tags_str = ", ".join(f"{tag}({count})" for tag, count in sorted(all_tags.items(), key=lambda x: -x[1]))
        console.print(f"\n[bold]Tags:[/bold] {tags_str}")

    # Top rated clips
    rated_clips = [c for c in catalog if c.get("rating")]
    if rated_clips:
        rated_clips.sort(key=lambda x: x.get("rating", 0), reverse=True)
        console.print("\n[bold]Top Rated:[/bold]")
        for clip in rated_clips[:5]:
            stars = "★" * clip["rating"] + "☆" * (5 - clip["rating"])
            console.print(f"  {stars} {clip['filename']}")


def format_duration(seconds: float) -> str:
    """Format seconds as human-readable duration."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    if hours:
        return f"{hours}h {minutes}m {secs}s"
    return f"{minutes}m {secs}s"


def browse_catalog(config: Config) -> None:
    """Interactive catalog browser."""
    catalog = load_catalog(config)

    if not catalog:
        console.print("[yellow]Catalog is empty. Run 'kdv meta --all' first.[/yellow]")
        return

    # Sort by filename
    catalog.sort(key=lambda x: x.get("filename", ""))

    # Pagination
    page_size = 15
    page = 0
    total_pages = (len(catalog) + page_size - 1) // page_size

    while True:
        console.clear()
        start = page * page_size
        end = min(start + page_size, len(catalog))
        page_clips = catalog[start:end]

        table = Table(title=f"Catalog Browser (Page {page+1}/{total_pages})", show_header=True)
        table.add_column("#", style="dim", width=4)
        table.add_column("File", style="cyan", max_width=35)
        table.add_column("Duration", justify="right", width=8)
        table.add_column("Size", justify="right", width=10)
        table.add_column("Rating", justify="center", width=7)
        table.add_column("Tags", max_width=20)
        table.add_column("Motion", width=10)

        for i, clip in enumerate(page_clips, start + 1):
            rating = ""
            if clip.get("rating"):
                rating = "★" * clip["rating"]

            tags = ", ".join(clip.get("tags", [])[:3])
            if len(clip.get("tags", [])) > 3:
                tags += "..."

            table.add_row(
                str(i),
                clip.get("filename", "")[:35],
                clip.get("duration_human", "-"),
                clip.get("size_human", "-"),
                rating,
                tags,
                clip.get("motion_type", ""),
            )

        console.print(table)
        console.print("\n[dim]Commands: (n)ext, (p)rev, (e)dit #, (q)uit[/dim]")

        cmd = Prompt.ask("Action", default="n")

        if cmd.lower() == "q":
            break
        elif cmd.lower() == "n" and page < total_pages - 1:
            page += 1
        elif cmd.lower() == "p" and page > 0:
            page -= 1
        elif cmd.lower().startswith("e"):
            try:
                num = int(cmd.split()[1]) if " " in cmd else int(Prompt.ask("Clip #"))
                if 1 <= num <= len(catalog):
                    edit_clip_interactive(catalog[num-1], config)
            except (ValueError, IndexError):
                console.print("[red]Invalid clip number[/red]")


def edit_clip_interactive(clip: dict, config: Config) -> None:
    """Interactively edit a clip's annotations."""
    console.print(f"\n[bold]Editing:[/bold] {clip['filename']}")
    console.print(f"Duration: {clip.get('duration_human', '-')} | Size: {clip.get('size_human', '-')}")

    # Current annotations
    console.print(f"\nCurrent rating: {'★' * clip.get('rating', 0) if clip.get('rating') else 'none'}")
    console.print(f"Current tags: {', '.join(clip.get('tags', [])) or 'none'}")
    console.print(f"Current motion: {clip.get('motion_type', 'none')}")
    console.print(f"Current vibe: {clip.get('vibe', 'none')}")
    console.print(f"Notes: {clip.get('notes', '') or 'none'}")

    # Edit rating
    rating_input = Prompt.ask("Rating (1-5, or Enter to skip)", default="")
    if rating_input:
        try:
            clip["rating"] = max(1, min(5, int(rating_input)))
        except ValueError:
            pass

    # Edit tags
    tags_input = Prompt.ask("Add tags (comma-separated, or Enter to skip)", default="")
    if tags_input:
        new_tags = [t.strip() for t in tags_input.split(",") if t.strip()]
        clip["tags"] = list(set(clip.get("tags", []) + new_tags))

    # Motion type
    motion_options = ["Ascending", "Descending", "Orbit", "PullOut", "PushIn", "Reveal", "Rotation", "Strafing", "Tracking"]
    console.print(f"Motion types: {', '.join(motion_options)}")
    motion_input = Prompt.ask("Motion type (or Enter to skip)", default="")
    if motion_input:
        # Fuzzy match
        for opt in motion_options:
            if motion_input.lower() in opt.lower():
                clip["motion_type"] = opt
                break

    # Vibe
    vibe_options = ["Calm", "Energetic", "Epic", "Lonely", "Mysterious", "Nostalgic"]
    console.print(f"Vibes: {', '.join(vibe_options)}")
    vibe_input = Prompt.ask("Vibe (or Enter to skip)", default="")
    if vibe_input:
        for opt in vibe_options:
            if vibe_input.lower() in opt.lower():
                clip["vibe"] = opt
                break

    # Notes
    notes_input = Prompt.ask("Notes (or Enter to skip)", default="")
    if notes_input:
        clip["notes"] = notes_input

    # Save
    catalog = load_catalog(config)
    for i, c in enumerate(catalog):
        if c.get("filename") == clip.get("filename"):
            catalog[i] = clip
            break
    save_catalog(catalog, config)
    console.print("[green]Saved![/green]")
