# Music Video Metadata Extractor

A Python script that extracts and organizes metadata from music video files.

## Features

- **Filename parsing**: Extracts artist and song title from various filename formats
- **Video analysis**: Uses `ffprobe` to extract technical metadata:
  - Resolution
  - Video/audio codecs
  - Bitrate
  - Framerate
  - File size
  - Duration
- **Smart classification**: Automatically categorizes videos as:
  - Music videos (< 45 min)
  - Live sets (full concerts/DJ sets)
  - Live performances (single live songs)
- **Release group detection**: Identifies and extracts scene release groups (e.g., `V1p0n3-nV`, `DVDRip-XviD-2006-SRP`)
- **Name cleanup**:
  - Removes underscores from artist/title names
  - Proper capitalization
  - Preserves apostrophes in contractions (e.g., "Ain't", "Goin'")

## Supported Filename Patterns

- `Artist - Title.ext`
- `Artist - Title [YouTube_ID].ext`
- `Artist - Title-YouTube_ID.ext`
- `Artist 'Album' Track-ID.ext`
- `Artist - Au Festival Year HDTV...` (live sets)
- Scene releases: `Artist-Title-DVDRip-XviD-Year-Group.ext`

## Requirements

- Python 3.8+
- `ffprobe` (part of FFmpeg)

## Installation

```bash
# Install FFmpeg (includes ffprobe)
# Fedora/RHEL
sudo dnf install ffmpeg

# Ubuntu/Debian
sudo apt install ffmpeg

# Arch
sudo pacman -S ffmpeg
```

## Usage

```bash
# Table output (default)
python extract_music_metadata.py /path/to/videos

# CSV output
python extract_music_metadata.py /path/to/videos -f csv -o metadata.csv

# JSON output
python extract_music_metadata.py /path/to/videos -f json

# Adjust live set threshold (default: 45 minutes)
python extract_music_metadata.py /path/to/videos -t 60
```

## Output Fields

| Field | Description |
|-------|-------------|
| filename | Original filename |
| artist | Extracted artist name |
| title | Extracted song/video title |
| duration | Formatted duration (MM:SS or HH:MM:SS) |
| duration_seconds | Duration in seconds |
| type | Classification (music_video, live_set, live_performance) |
| confidence | Parsing confidence (high, medium, low) |
| resolution | Video resolution (e.g., 1920x1080) |
| video_codec | Video codec (e.g., h264, vp9) |
| audio_codec | Audio codec (e.g., aac, opus) |
| bitrate | Overall bitrate |
| framerate | Video framerate |
| filesize | Human-readable file size |
| file_date | File modification date |
| release_group | Detected scene release group |

## License

MIT
