# kdv - Kdenlive Video Workflow Toolkit

A Python CLI tool for automating drone footage workflows with Kdenlive.

## Features

- **Ingest** - Import footage from SD cards with auto-rename and organization
- **Convert** - Batch convert 60fps to 30fps with quality presets
- **Proxy** - Generate lightweight editing proxies (540p/720p)
- **Metadata** - Extract and catalog video metadata to JSON
- **Catalog** - Browse, rate, tag, and classify your clips
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

### Catalog - Browse and Annotate Clips

The catalog lets you organize your footage with ratings, tags, motion types, and vibes.

#### View Catalog Summary

```bash
kdv catalog
```

Shows statistics: total clips, duration, how many are rated/tagged/classified.

#### Quick-Tag Workflow (Recommended)

The fastest way to annotate your clips. **Prerequisite:** Generate thumbnails first so you have something to preview:

```bash
# Generate thumbnails and contact sheets (do this first!)
kdv thumbs --all --contact-sheet
```

Then start the quick-tag workflow:

```bash
kdv catalog --quick              # Opens thumbnail for each clip
kdv catalog --quick -p video     # Opens video in QuickTime
kdv catalog --quick -p none      # No preview (text only)
```

**Preview modes:**
- `thumb` (default) - Opens the thumbnail image in Preview.app. Contact sheets (4x4 grid of frames) are especially useful for seeing camera motion at a glance.
- `video` - Opens the actual video file in QuickTime Player. Good for reviewing audio or subtle motion.
- `none` - No preview, just text info in terminal.

This walks through each unrated clip and lets you annotate with single keystrokes:

```
(1/46) HOVER_X1PROMAX_0061.mp4
  Duration: 1:03.96 | Size: 449.4 MB
  > 4 i e +sunset
  ✓ ★4 | PushIn | Epic | +sunset
```

**Quick-tag commands (combine them!):**

| Key | Action | Key | Action |
|-----|--------|-----|--------|
| `1-5` | Rate 1-5 stars | `+word` | Add tag |
| `a` | Ascending | `c` | Calm |
| `d` | Descending | `e` | Epic |
| `i` | PushIn | `n` | Energetic |
| `u` | PullOut | `l` | Lonely |
| `o` | Orbit | `m` | Mysterious |
| `r` | Reveal | `g` | Nostalgic |
| `t` | Rotation | `x` | Mark unusable |
| `s` | Strafing | Enter | Skip clip |
| `k` | Tracking | `q` | Quit |

**Example inputs:**
- `5 i e` → 5 stars, PushIn motion, Epic vibe
- `3 d c +forest +morning` → 3 stars, Descending, Calm, tags: forest, morning
- `x` → mark as unusable and move on

#### Annotate Individual Clips

```bash
# Rate a clip (partial filename match works)
kdv catalog 0065 --rate 5

# Add tags
kdv catalog 0065 -t sunset -t golden-hour

# Set motion type
kdv catalog 0065 --motion PushIn

# Set vibe/mood
kdv catalog 0065 --vibe Epic

# Add notes
kdv catalog 0065 --note "Great establishing shot"

# Combine options
kdv catalog 0065 --rate 4 -t hero --motion PushIn --vibe Epic
```

#### Batch Annotate Multiple Clips

```bash
# Tag all 30fps converted clips
kdv catalog --batch 30fps -t converted

# Rate all clips from a session
kdv catalog --batch 007 --rate 3 --motion Orbit
```

#### Interactive Browser

```bash
kdv catalog --browse
```

Paginated view with editing support.

### Generate Thumbnails

Creates preview images for your clips, saved to `.thumbnails/` folder.

```bash
# Generate single thumbnail per clip (frame at 3 seconds)
kdv thumbs --all

# Include contact sheets (recommended!)
kdv thumbs --all --contact-sheet
```

**What gets generated:**
- `HOVER_X1PROMAX_0065.jpg` - Single frame thumbnail
- `HOVER_X1PROMAX_0065_contact.jpg` - 4x4 grid showing 16 frames throughout the clip

Contact sheets are invaluable for the quick-tag workflow - you can see the entire clip's motion and content in one image without opening the video.

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

## Typical Workflow

Here's a recommended workflow for processing new drone footage:

```bash
# 1. Import footage from SD card
kdv ingest /Volumes/HOVERAIR

# 2. Extract metadata and generate thumbnails
kdv meta --all
kdv thumbs --all --contact-sheet

# 3. Review and annotate your clips (the fun part!)
kdv catalog --quick

# 4. Convert good clips to 30fps for editing
kdv convert --all

# 5. Generate proxies for smooth editing (optional)
kdv proxy --all

# 6. Check your progress
kdv status
kdv catalog
```

After editing in Kdenlive:

```bash
# Extract B-roll clips from your project
kdv extract Projects/MyProject.kdenlive --interactive

# Export final video
kdv export Projects/MyProject.kdenlive --preset youtube-1080
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
