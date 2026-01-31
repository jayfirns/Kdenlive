# kdv - Kdenlive Video Workflow Toolkit

A Python CLI tool for automating drone footage workflows with Kdenlive.

## Features

- **Ingest** - Import footage from SD cards with auto-rename and organization
- **Convert** - Batch convert 60fps to 30fps with quality presets
- **Proxy** - Generate lightweight editing proxies (540p/720p)
- **Metadata** - Extract and catalog video metadata to JSON
- **Thumbnails** - Generate thumbnails and contact sheets
- **Extract** - Export clips from Kdenlive projects to B-roll folders
- **Export** - Render projects with preset configurations

## Installation

```bash
# Clone the repository
git clone git@github.com:jayfirns/Kdenlive.git
cd Kdenlive

# Install in development mode
pip install -e .

# Verify installation
kdv --help
```

## Requirements

- Python 3.9+
- FFmpeg (for video processing)
- Optional: MLT/melt (for project rendering)

```bash
# macOS
brew install ffmpeg
brew install mlt  # optional, for export command
```

## Usage

### Check Status

```bash
kdv status
```

Shows folder statistics, files needing conversion, and pending work.

### Ingest Footage

```bash
# From SD card or folder
kdv ingest /Volumes/SDCARD

# Move instead of copy
kdv ingest /path/to/source --move
```

### Convert Frame Rate

```bash
# Convert specific files
kdv convert video1.mp4 video2.mp4

# Convert all raw footage
kdv convert --all

# With quality preset
kdv convert --all --quality quality  # fast|balanced|quality
```

### Generate Proxies

```bash
# Generate proxies for all raw footage
kdv proxy --all

# Specific resolution
kdv proxy --all --resolution 720
```

### Extract Metadata

```bash
# Extract metadata from all raw footage
kdv meta --all

# Save to specific file
kdv meta --all --output catalog.json
```

### Generate Thumbnails

```bash
# Generate thumbnails
kdv thumbs --all

# Include contact sheets
kdv thumbs --all --contact-sheet
```

### Extract Clips from Project

```bash
# Extract clips from Kdenlive project
kdv extract Projects/MyProject.kdenlive

# Interactive mode (choose B-roll categories)
kdv extract Projects/MyProject.kdenlive --interactive
```

### Export Project

```bash
# Export with default preset (youtube-1080)
kdv export Projects/MyProject.kdenlive

# With specific preset
kdv export Projects/MyProject.kdenlive --preset youtube-4k
```

## Configuration

Edit `config/kdv.yaml` to customize settings:

```yaml
paths:
  raw: Raw_HoverAir_Vids
  broll: BRoll
  proxy: proxy

conversion:
  target_fps: 30
  quality: balanced

proxy:
  resolution: 540
  crf: 28

export:
  presets:
    youtube-4k:
      resolution: 3840x2160
      video_bitrate: 45M
    youtube-1080:
      resolution: 1920x1080
      video_bitrate: 12M
```

## Folder Structure

```
Kdenlive/
├── Raw_HoverAir_Vids/    # Original drone footage
├── BRoll/
│   ├── Motion/           # Clips by camera movement
│   │   ├── Ascending/
│   │   ├── Descending/
│   │   ├── PushIns/
│   │   └── ...
│   └── Vibes/            # Clips by mood
│       ├── Calm/
│       ├── Epic/
│       └── ...
├── Projects/             # Kdenlive project files
├── Edits/                # Completed edits
├── proxy/                # Proxy files
├── archive/              # Archived footage
└── .thumbnails/          # Generated thumbnails
```

## License

MIT
