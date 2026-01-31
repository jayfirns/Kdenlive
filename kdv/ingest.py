"""
Footage ingest and organization.
"""

import hashlib
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.progress import Progress, BarColumn, TextColumn, TimeRemainingColumn
from rich.prompt import Confirm

from kdv.config import Config

console = Console()

# HoverAir naming pattern
HOVERAIR_PATTERN = re.compile(r"HOVER_X1PROMAX_(\d{4})")


def calculate_checksum(file_path: Path, chunk_size: int = 8192) -> str:
    """Calculate MD5 checksum of a file."""
    md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        while chunk := f.read(chunk_size):
            md5.update(chunk)
    return md5.hexdigest()


def get_next_sequence_number(dest_dir: Path) -> int:
    """Find the next available sequence number in the destination directory."""
    max_seq = 0

    for file in dest_dir.glob("HOVER_X1PROMAX_*.mp4"):
        match = HOVERAIR_PATTERN.search(file.name)
        if match:
            seq = int(match.group(1))
            max_seq = max(max_seq, seq)

    return max_seq + 1


def find_video_files(source: Path) -> list[Path]:
    """Find all video files in source directory."""
    extensions = {".mp4", ".mov", ".mkv", ".avi", ".mxf"}
    files = []

    if source.is_file():
        if source.suffix.lower() in extensions:
            return [source]
        return []

    for ext in extensions:
        files.extend(source.glob(f"*{ext}"))
        files.extend(source.glob(f"*{ext.upper()}"))

    # Also check DCIM folder structure (common on SD cards)
    dcim = source / "DCIM"
    if dcim.exists():
        for ext in extensions:
            files.extend(dcim.rglob(f"*{ext}"))
            files.extend(dcim.rglob(f"*{ext.upper()}"))

    return sorted(files)


def ingest_footage(
    source: str,
    move: bool = False,
    verify: bool = True,
    config: Optional[Config] = None,
) -> dict:
    """Import footage from a source directory."""
    source_path = Path(source)

    if not source_path.exists():
        console.print(f"[red]Error:[/red] Source not found: {source}")
        return {"success": [], "failed": []}

    # Get destination from config
    if config:
        dest_dir = config.raw_dir
        naming_pattern = config.get("ingest.naming_pattern", "HOVER_X1PROMAX_{seq:04d}")
        create_dated = config.get("ingest.create_dated_folders", False)
    else:
        dest_dir = Path("Raw_HoverAir_Vids")
        naming_pattern = "HOVER_X1PROMAX_{seq:04d}"
        create_dated = False

    dest_dir.mkdir(parents=True, exist_ok=True)

    # Find video files
    files = find_video_files(source_path)

    if not files:
        console.print(f"[yellow]No video files found in {source}[/yellow]")
        return {"success": [], "failed": []}

    console.print(f"\n[blue]Found {len(files)} video files[/blue]")

    # Check for existing files
    existing = []
    for f in files:
        dest_file = dest_dir / f.name
        if dest_file.exists():
            existing.append(f.name)

    if existing:
        console.print(f"[yellow]Warning:[/yellow] {len(existing)} files already exist in destination")
        for name in existing[:3]:
            console.print(f"  • {name}")
        if len(existing) > 3:
            console.print(f"  [dim]... and {len(existing) - 3} more[/dim]")

    # Determine operation
    op = "Moving" if move else "Copying"
    console.print(f"\n{op} files to: {dest_dir}")

    if not Confirm.ask("Continue?", default=True):
        console.print("[dim]Cancelled.[/dim]")
        return {"success": [], "failed": [], "cancelled": True}

    results = {"success": [], "failed": [], "skipped": []}

    # Get starting sequence number for renaming
    next_seq = get_next_sequence_number(dest_dir)

    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(f"{op} files...", total=len(files))

        for src_file in files:
            progress.update(task, description=f"{op} {src_file.name}...")

            # Determine destination filename
            # Check if it's already in HoverAir format
            if HOVERAIR_PATTERN.search(src_file.name):
                dest_name = src_file.name
            else:
                # Rename using pattern
                dest_name = naming_pattern.format(seq=next_seq) + src_file.suffix.lower()
                next_seq += 1

            # Handle dated folders
            if create_dated:
                date_str = datetime.now().strftime("%Y-%m-%d")
                final_dest_dir = dest_dir / date_str
                final_dest_dir.mkdir(parents=True, exist_ok=True)
            else:
                final_dest_dir = dest_dir

            dest_file = final_dest_dir / dest_name

            # Skip if exists
            if dest_file.exists():
                results["skipped"].append(src_file.name)
                progress.advance(task)
                continue

            try:
                # Calculate source checksum if verifying
                src_checksum = None
                if verify:
                    src_checksum = calculate_checksum(src_file)

                # Copy or move
                if move:
                    shutil.move(src_file, dest_file)
                else:
                    shutil.copy2(src_file, dest_file)

                # Verify checksum
                if verify and src_checksum:
                    dest_checksum = calculate_checksum(dest_file)
                    if src_checksum != dest_checksum:
                        console.print(f"[red]Checksum mismatch:[/red] {src_file.name}")
                        dest_file.unlink()
                        results["failed"].append(src_file.name)
                        progress.advance(task)
                        continue

                results["success"].append(dest_name)

            except Exception as e:
                console.print(f"[red]Error {op.lower()} {src_file.name}:[/red] {e}")
                results["failed"].append(src_file.name)

            progress.advance(task)

    # Summary
    console.print(f"\n[bold]Ingest complete:[/bold]")
    console.print(f"  [green]Success:[/green] {len(results['success'])}")
    if results["skipped"]:
        console.print(f"  [yellow]Skipped:[/yellow] {len(results['skipped'])}")
    if results["failed"]:
        console.print(f"  [red]Failed:[/red] {len(results['failed'])}")

    return results


def detect_sd_card() -> Optional[Path]:
    """Try to detect an SD card mount point (macOS)."""
    volumes = Path("/Volumes")
    if not volumes.exists():
        return None

    for vol in volumes.iterdir():
        if vol.name in ("Macintosh HD", "Recovery"):
            continue

        # Check for DCIM folder (common camera structure)
        dcim = vol / "DCIM"
        if dcim.exists():
            return vol

        # Check for HoverAir files
        for f in vol.glob("HOVER_*.mp4"):
            return vol

    return None
