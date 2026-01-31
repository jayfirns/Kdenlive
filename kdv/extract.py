"""
Clip extraction from Kdenlive projects.
"""

import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.progress import Progress, BarColumn, TextColumn, TimeRemainingColumn
from rich.prompt import Prompt, Confirm
from rich.table import Table

from kdv.config import Config

console = Console()


@dataclass
class TimelineClip:
    """Represents a clip on the timeline."""
    producer_id: str
    source_path: Path
    in_point: int  # frames
    out_point: int  # frames
    duration: int  # frames
    track: str
    position: int  # position on timeline in frames
    fps: float = 30.0

    @property
    def in_seconds(self) -> float:
        return self.in_point / self.fps

    @property
    def out_seconds(self) -> float:
        return self.out_point / self.fps

    @property
    def duration_seconds(self) -> float:
        return self.duration / self.fps

    def in_timecode(self) -> str:
        """Convert in point to timecode string."""
        return frames_to_timecode(self.in_point, self.fps)

    def out_timecode(self) -> str:
        """Convert out point to timecode string."""
        return frames_to_timecode(self.out_point, self.fps)


def frames_to_timecode(frames: int, fps: float) -> str:
    """Convert frame count to HH:MM:SS.mmm timecode."""
    total_seconds = frames / fps
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    seconds = total_seconds % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:06.3f}"


def parse_kdenlive_project(project_path: Path) -> tuple[dict, list[TimelineClip]]:
    """Parse a Kdenlive project file and extract clip information."""
    tree = ET.parse(project_path)
    root = tree.getroot()

    # Get project FPS from profile
    fps = 30.0
    for profile in root.iter("profile"):
        frame_rate_num = profile.get("frame_rate_num", "30")
        frame_rate_den = profile.get("frame_rate_den", "1")
        try:
            fps = int(frame_rate_num) / int(frame_rate_den)
        except (ValueError, ZeroDivisionError):
            pass
        break

    # Build producer map (clip ID -> source file)
    producers = {}
    for producer in root.iter("producer"):
        prod_id = producer.get("id", "")
        for prop in producer.findall("property"):
            if prop.get("name") == "resource":
                resource_path = prop.text
                if resource_path and not resource_path.startswith("black"):
                    producers[prod_id] = Path(resource_path)
                break

    # Parse timeline entries from playlist/tractor
    clips = []

    # Find the main timeline (usually a tractor with tracks)
    for tractor in root.iter("tractor"):
        for track in tractor.findall("track"):
            track_producer = track.get("producer", "")

            # Find the playlist for this track
            for playlist in root.iter("playlist"):
                if playlist.get("id") == track_producer:
                    position = 0
                    for entry in playlist.findall("entry"):
                        prod_ref = entry.get("producer", "")
                        in_frame = int(entry.get("in", "0"))
                        out_frame = int(entry.get("out", "0"))

                        # Look up the actual source
                        if prod_ref in producers:
                            clip = TimelineClip(
                                producer_id=prod_ref,
                                source_path=producers[prod_ref],
                                in_point=in_frame,
                                out_point=out_frame,
                                duration=out_frame - in_frame + 1,
                                track=track_producer,
                                position=position,
                                fps=fps,
                            )
                            clips.append(clip)

                        position += out_frame - in_frame + 1

    project_info = {
        "path": str(project_path),
        "fps": fps,
        "total_clips": len(clips),
        "sources": list(set(str(p) for p in producers.values())),
    }

    return project_info, clips


def extract_clip_segment(
    source_path: Path,
    output_path: Path,
    start_time: str,
    duration: float,
    copy_codec: bool = True,
) -> bool:
    """Extract a segment from a video file."""
    cmd = [
        "ffmpeg",
        "-y",
        "-ss", start_time,
        "-i", str(source_path),
        "-t", str(duration),
    ]

    if copy_codec:
        # Stream copy (fast, no re-encode)
        cmd.extend(["-c", "copy"])
    else:
        # Re-encode for precise cuts
        cmd.extend([
            "-c:v", "libx264",
            "-crf", "18",
            "-preset", "medium",
            "-c:a", "aac",
            "-b:a", "256k",
        ])

    cmd.append(str(output_path))

    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0


def get_broll_categories(config: Config) -> dict[str, list[str]]:
    """Get available B-roll categories from config."""
    return config.get_broll_categories()


def prompt_for_category(
    clip: TimelineClip,
    categories: dict[str, list[str]],
) -> Optional[tuple[str, str]]:
    """Interactively prompt user for B-roll category."""
    console.print(f"\n[cyan]Clip:[/cyan] {clip.source_path.name}")
    console.print(f"  Duration: {clip.duration_seconds:.1f}s ({clip.in_timecode()} - {clip.out_timecode()})")

    # Build category options
    all_options = []
    for category_type, subcategories in categories.items():
        for sub in subcategories:
            all_options.append(f"{category_type}/{sub}")

    console.print("\n[bold]Categories:[/bold]")
    for i, opt in enumerate(all_options, 1):
        console.print(f"  {i}. {opt}")
    console.print(f"  {len(all_options) + 1}. [dim]Skip this clip[/dim]")

    choice = Prompt.ask(
        "Select category",
        default=str(len(all_options) + 1),
    )

    try:
        idx = int(choice) - 1
        if 0 <= idx < len(all_options):
            parts = all_options[idx].split("/")
            return (parts[0], parts[1])
    except ValueError:
        pass

    return None


def extract_clips(
    project: str,
    output_dir: Optional[str] = None,
    interactive: bool = False,
    config: Optional[Config] = None,
) -> dict:
    """Extract clips from a Kdenlive project to B-roll folders."""
    project_path = Path(project)

    if not project_path.exists():
        console.print(f"[red]Error:[/red] Project not found: {project}")
        return {"success": [], "failed": []}

    # Parse project
    console.print(f"\n[blue]Parsing project:[/blue] {project_path.name}")
    project_info, clips = parse_kdenlive_project(project_path)

    console.print(f"  FPS: {project_info['fps']}")
    console.print(f"  Clips on timeline: {len(clips)}")

    if not clips:
        console.print("[yellow]No clips found on timeline.[/yellow]")
        return {"success": [], "failed": []}

    # Display clips table
    table = Table(title="Timeline Clips", show_header=True)
    table.add_column("#", style="dim")
    table.add_column("Source", style="cyan", max_width=40)
    table.add_column("In", justify="right")
    table.add_column("Out", justify="right")
    table.add_column("Duration", justify="right")

    for i, clip in enumerate(clips, 1):
        table.add_row(
            str(i),
            clip.source_path.name,
            clip.in_timecode(),
            clip.out_timecode(),
            f"{clip.duration_seconds:.1f}s",
        )

    console.print(table)

    # Determine output directory
    if output_dir:
        out_path = Path(output_dir)
    elif config:
        out_path = config.broll_dir
    else:
        out_path = Path("BRoll")

    out_path.mkdir(parents=True, exist_ok=True)

    # Get categories for interactive mode
    categories = {}
    if interactive and config:
        categories = get_broll_categories(config)

    if not Confirm.ask(f"\nExtract {len(clips)} clips to {out_path}?", default=True):
        console.print("[dim]Cancelled.[/dim]")
        return {"success": [], "failed": [], "cancelled": True}

    results = {"success": [], "failed": [], "skipped": []}

    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Extracting clips...", total=len(clips))

        for i, clip in enumerate(clips, 1):
            progress.update(task, description=f"Extracting clip {i}/{len(clips)}...")

            # Determine output path
            if interactive and categories:
                category = prompt_for_category(clip, categories)
                if category is None:
                    results["skipped"].append(clip.source_path.name)
                    progress.advance(task)
                    continue
                clip_out_dir = out_path / category[0].capitalize() / category[1]
            else:
                clip_out_dir = out_path

            clip_out_dir.mkdir(parents=True, exist_ok=True)

            # Generate output filename
            source_stem = clip.source_path.stem
            output_name = f"{source_stem}_clip{i:03d}.mp4"
            output_file = clip_out_dir / output_name

            # Skip if exists
            if output_file.exists():
                results["skipped"].append(output_name)
                progress.advance(task)
                continue

            # Extract the clip
            if extract_clip_segment(
                clip.source_path,
                output_file,
                clip.in_timecode(),
                clip.duration_seconds,
            ):
                results["success"].append(str(output_file.relative_to(out_path)))
            else:
                results["failed"].append(clip.source_path.name)

            progress.advance(task)

    # Summary
    console.print(f"\n[bold]Extraction complete:[/bold]")
    console.print(f"  [green]Success:[/green] {len(results['success'])}")
    if results["skipped"]:
        console.print(f"  [yellow]Skipped:[/yellow] {len(results['skipped'])}")
    if results["failed"]:
        console.print(f"  [red]Failed:[/red] {len(results['failed'])}")

    return results
