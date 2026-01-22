#!/usr/bin/env python3
"""
Music Video Metadata Extractor

Extracts metadata from music video files including:
- Artist and song name from filename
- Video duration
- Classification (music video vs live set)
"""

import os
import re
import subprocess
import json
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

# Video extensions to process
VIDEO_EXTENSIONS = {'.mp4', '.mkv', '.webm', '.avi', '.mpg', '.mpeg', '.mov', '.wmv', '.flv'}

# Duration threshold in seconds (45 minutes = likely a live set)
LIVE_SET_THRESHOLD = 45 * 60

# Known release groups and rippers (case-insensitive matching)
KNOWN_RELEASE_GROUPS = {
    'v1p0n3', 'jaded', 'typeoserv', 'cubert', 'cutthroat', 'mud', 'blag',
    'dike1999', 'sts', 'milka', 'srp', 'vfi', 'mv4', 'rerip', 'crds',
    'nazty2005', 'pmd', 'hdp', 'ldv', 'apv', 'msz', 'ma42'
}

# Patterns that indicate release/rip info (to be removed from title)
RELEASE_PATTERNS = [
    # Group tags at end: -GroupName or -GroupName-nV
    r'-([a-zA-Z0-9_]+)(?:-[a-zA-Z]{2,3})?$',
    # DVDRip/WebRip style: -DVDRip-XviD-Group or similar
    r'[-_](?:DVD|WEB|HDTV|BD)?[Rr]ip[-_]?(?:XviD|x264|AVC)?[-_]?(\d{4})?[-_]?([a-zA-Z0-9_]+)?$',
    # SVCD/VCD style: -SVCD-Group
    r'[-_](?:SVCD|VCD)[-_]([a-zA-Z0-9_]+)$',
    # Ripped By text
    r'[-_]?[Rr]ipped?\s*[Bb]y\s*([a-zA-Z0-9_]+)[-_]?$',
    # Year and group: -2006-GroupName
    r'[-_](\d{4})[-_]([a-zA-Z0-9_]+)$',
    # Brackets with group: [GroupName] at end
    r'\[([a-zA-Z0-9_]+)\]$',
]


def extract_release_group(text: str) -> tuple[str, Optional[str]]:
    """
    Extract release group from text and return cleaned text and group name.
    Returns (cleaned_text, release_group)
    """
    original = text
    release_group = None

    # First check for "Ripped By" pattern
    ripped_match = re.search(r'[-_\s]*[Rr]ipped?\s*[Bb]y\s*([a-zA-Z0-9_]+)[-_\s]*', text)
    if ripped_match:
        release_group = ripped_match.group(1)
        text = text[:ripped_match.start()] + text[ripped_match.end():]
        text = text.strip(' -_')

    # Pattern: XviD-Year-Group or DVDRip-XviD-Year-Group (common scene format)
    # e.g., "darkthrone-too_old_too_cold-dvdrip-xvid-2006-festis"
    # e.g., "Deftones-Hole_In_The_Earth-XViD-2006-SRP"
    match = re.search(r'[-_](?:DVD[Rr]ip[-_]?)?(?:XviD|x264|AVC|MPEG4|DivX)[-_]?(\d{4})?[-_]?([a-zA-Z0-9_]+)?$', text, re.IGNORECASE)
    if match:
        if match.group(2):
            release_group = match.group(2)
        text = text[:match.start()]
        text = text.strip(' -_')

    # Pattern: DVDRip-XviD-RERiP-Year-Group (with rerip tag)
    match = re.search(r'[-_]DVD[Rr]i[Pp][-_]XviD[-_](?:RE[Rr]i[Pp][-_])?(\d{4})[-_]([a-zA-Z0-9_]+)$', text, re.IGNORECASE)
    if match:
        release_group = match.group(2)
        text = text[:match.start()]
        text = text.strip(' -_')

    # Pattern: -GroupName-nV or -GroupName-suffix at end (scene group with suffix)
    match = re.search(r'[-_]([a-zA-Z0-9_]+)[-_]([a-zA-Z]{2,3})$', text)
    if match:
        potential_group = match.group(1).lower()
        suffix = match.group(2).lower()

        # Check if it's a known group or has typical suffix (nv, hdp, apv, etc.)
        if potential_group in KNOWN_RELEASE_GROUPS or suffix in {'nv', 'hdp', 'apv', 'ldv', 'msz', 'ucv'}:
            release_group = match.group(1) + '-' + match.group(2)
            text = text[:match.start()]
            text = text.strip(' -_')

    # Pattern: -GroupName at end (known groups without suffix)
    if not release_group:
        match = re.search(r'[-_]([a-zA-Z0-9_]+)$', text)
        if match:
            potential_group = match.group(1).lower()
            if potential_group in KNOWN_RELEASE_GROUPS:
                release_group = match.group(1)
                text = text[:match.start()]
                text = text.strip(' -_')

    # Pattern: -SVCD-Group or -VCD-Group
    match = re.search(r'[-_](?:SVCD|VCD)[-_](\d{4})?[-_]?([a-zA-Z0-9_]+)?$', text, re.IGNORECASE)
    if match:
        if match.group(2) and not release_group:
            release_group = match.group(2)
        text = text[:match.start()]
        text = text.strip(' -_')

    # Pattern: .PDTV.XviD-Group (dotted format)
    match = re.search(r'\.(?:PDTV|HDTV|WEB)\.XviD[-_]([a-zA-Z0-9_]+)$', text, re.IGNORECASE)
    if match:
        if not release_group:
            release_group = match.group(1)
        text = text[:match.start()]
        text = text.strip(' -_.')

    # Clean up any remaining technical suffixes without group info
    text = re.sub(r'[-_.](?:SVCD|VCD|DVDRip|WEBRip|HDTV|PDTV|720p|1080p|AVC|MKV|x264|XviD|AC-3|AAC)[-_.]?(?:\d{4})?$', '', text, flags=re.IGNORECASE)
    text = text.strip(' -_.')

    return text, release_group


@dataclass
class VideoMetadata:
    filename: str
    artist: Optional[str]
    title: Optional[str]
    duration_seconds: float
    duration_formatted: str
    video_type: str  # "music_video", "live_set", "unknown"
    confidence: str  # "high", "medium", "low"
    raw_parse: dict
    # Video info
    resolution: str
    video_codec: str
    audio_codec: str
    bitrate: str
    framerate: str
    filesize: str
    file_date: str
    release_group: Optional[str]


@dataclass
class ProbeResult:
    duration: float
    resolution: str
    video_codec: str
    audio_codec: str
    bitrate: str
    framerate: str
    filesize: str


def format_filesize(size_bytes: int) -> str:
    """Format file size in human readable format."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"


def get_video_info(filepath: str) -> Optional[ProbeResult]:
    """Extract video information using ffprobe."""
    try:
        result = subprocess.run(
            [
                'ffprobe', '-v', 'quiet', '-print_format', 'json',
                '-show_format', '-show_streams', filepath
            ],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)

            # Get format info
            fmt = data.get('format', {})
            duration = float(fmt.get('duration', 0))
            bitrate = fmt.get('bit_rate', '')
            filesize = int(fmt.get('size', 0))

            # Format bitrate
            if bitrate:
                bitrate_kbps = int(bitrate) // 1000
                if bitrate_kbps >= 1000:
                    bitrate_str = f"{bitrate_kbps / 1000:.1f} Mbps"
                else:
                    bitrate_str = f"{bitrate_kbps} kbps"
            else:
                bitrate_str = "unknown"

            # Find video and audio streams
            video_codec = "unknown"
            audio_codec = "unknown"
            resolution = "unknown"
            framerate = "unknown"

            for stream in data.get('streams', []):
                codec_type = stream.get('codec_type', '')

                if codec_type == 'video':
                    video_codec = stream.get('codec_name', 'unknown')
                    width = stream.get('width', 0)
                    height = stream.get('height', 0)
                    if width and height:
                        resolution = f"{width}x{height}"

                    # Get framerate
                    fps_str = stream.get('r_frame_rate', '') or stream.get('avg_frame_rate', '')
                    if fps_str and '/' in fps_str:
                        num, den = fps_str.split('/')
                        if int(den) > 0:
                            fps = int(num) / int(den)
                            framerate = f"{fps:.2f} fps"

                elif codec_type == 'audio':
                    audio_codec = stream.get('codec_name', 'unknown')

            return ProbeResult(
                duration=duration,
                resolution=resolution,
                video_codec=video_codec,
                audio_codec=audio_codec,
                bitrate=bitrate_str,
                framerate=framerate,
                filesize=format_filesize(filesize)
            )
    except (subprocess.TimeoutExpired, json.JSONDecodeError, ValueError, KeyError, ZeroDivisionError):
        pass
    return None


def format_duration(seconds: float) -> str:
    """Format duration as HH:MM:SS or MM:SS."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)

    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def parse_filename(filename: str) -> dict:
    """
    Parse filename to extract artist and title.

    Handles patterns like:
    - "Artist - Title.ext"
    - "Artist - Title [YouTube_ID].ext"
    - "Artist - Title-YouTube_ID.ext"
    - "Artist - Title (info) [ID].ext"
    - "Artist 'Album/EP' Track-ID.ext"
    - Live sets with festival names
    """
    # Remove extension
    name = Path(filename).stem

    # Normalize different quote characters to standard single quotes
    # But first, protect apostrophes within words (like "Ain't", "Goin'") by temporarily replacing them
    # Apostrophe pattern: letter + quote + letter (mid-word) or letter + quote + space/end (trailing)
    import string

    # Replace curly quotes with straight quotes first
    name = name.replace('\u2018', "'").replace('\u2019', "'")  # Curly quotes
    name = name.replace('\u201c', '"').replace('\u201d', '"')  # Curly double quotes

    # Protect apostrophes in contractions (e.g., Ain't, Don't, Goin')
    # by replacing them with a placeholder (using \u2019 as temp marker since we already converted it)
    APOSTROPHE_PLACEHOLDER = '\u00b6'  # Pilcrow sign, unlikely in filenames
    protected_name = re.sub(r"(\w)'(\w)", r"\1" + APOSTROPHE_PLACEHOLDER + r"\2", name)  # mid-word: Ain't
    protected_name = re.sub(r"(\w)'(\s|$)", r"\1" + APOSTROPHE_PLACEHOLDER + r"\2", protected_name)  # trailing: Goin'
    protected_name = re.sub(r"(\s)'(\w)", r"\1" + APOSTROPHE_PLACEHOLDER + r"\2", protected_name)  # leading: 'cause

    result = {
        'artist': None,
        'title': None,
        'is_live_indicator': False,
        'pattern_matched': None,
        'release_group': None
    }

    # Check for live set indicators in filename (before cleaning)
    live_indicators = [
        r'\bhellfest\b', r'\blive\b', r'\bfestival\b', r'\bconcert\b',
        r'\bhdtv\b', r'\bweb\b.*\bavc\b', r'\bau\s+\w+\s+\d{4}\b'
    ]
    for indicator in live_indicators:
        if re.search(indicator, name, re.IGNORECASE):
            result['is_live_indicator'] = True
            break

    # Extract release group from the filename first
    name, release_group = extract_release_group(name)
    result['release_group'] = release_group

    # Use protected_name (with apostrophes replaced by \x00) for pattern matching
    # to avoid confusing apostrophes with quote delimiters
    name = protected_name
    name, _ = extract_release_group(name)  # Also clean protected version

    # Helper to restore apostrophes in final result
    def restore_apostrophes(s):
        return s.replace(APOSTROPHE_PLACEHOLDER, "'") if s else s

    # Helper to clean up names: remove underscores and capitalize properly
    def clean_name(s):
        if not s:
            return s
        # Replace underscores with spaces
        s = s.replace('_', ' ')
        # Remove multiple spaces
        s = re.sub(r'\s+', ' ', s).strip()
        # Capitalize each word (title case), but preserve all-caps abbreviations
        words = s.split()
        result = []
        for word in words:
            # Keep all-caps words (like "DJ", "MC", "NIN") or already capitalized
            if word.isupper() and len(word) <= 4:
                result.append(word)
            # Capitalize first letter of each word
            elif word and word[0].islower():
                result.append(word.capitalize())
            else:
                result.append(word)
        return ' '.join(result)

    # Pattern 1: YouTube download with brackets [ID]
    # e.g., "Artist - Title (info) [CsHiG-43Fzg]"
    match = re.match(r'^(.+?)\s*-\s*(.+?)\s*\[[a-zA-Z0-9_-]{11}\]$', name)
    if match:
        result['artist'] = clean_name(restore_apostrophes(match.group(1).strip()))
        result['title'] = clean_name(restore_apostrophes(match.group(2).strip()))
        result['pattern_matched'] = 'youtube_brackets'
        return result

    # Pattern 2: Artist 'Album/Series' Episode - Subtitle-ID (with subtitle)
    # e.g., "Charlotte de Witte 'New Form' II - Return To Nowhere-EiEFdnU6KWY"
    # Note: IV - Formula--G_nX3n_sog has double dash because YouTube ID starts with dash
    match = re.match(r"^(.+?)\s*'(.+?)'\s*([IVXLCDM]+)\s+-\s+(.+?)-{1,2}[a-zA-Z0-9_-]{10,11}$", name)
    if match:
        result['artist'] = clean_name(restore_apostrophes(match.group(1).strip()))
        series = clean_name(restore_apostrophes(match.group(2).strip()))
        episode = match.group(3).strip()
        subtitle = clean_name(restore_apostrophes(match.group(4).strip()))
        result['title'] = f"{series} {episode} - {subtitle}"
        result['pattern_matched'] = 'quoted_series_episode'
        return result

    # Pattern 2b: Artist 'Album/Series' Episode-ID (no subtitle)
    # e.g., "Charlotte de Witte 'New Form' I-3cOOu52n26c"
    match = re.match(r"^(.+?)\s*'(.+?)'\s*([IVXLCDM]+)-[a-zA-Z0-9_-]{11}$", name)
    if match:
        result['artist'] = clean_name(restore_apostrophes(match.group(1).strip()))
        series = clean_name(restore_apostrophes(match.group(2).strip()))
        episode = match.group(3).strip()
        result['title'] = f"{series} {episode}"
        result['pattern_matched'] = 'quoted_series_episode_no_subtitle'
        return result

    # Pattern 3: yt-dlp style with -ID at end (standard Artist - Title format)
    # e.g., "Artist - Title-oW0VovnyjPY"
    match = re.match(r'^(.+?)\s*-\s*(.+?)-[a-zA-Z0-9_-]{11}$', name)
    if match:
        result['artist'] = clean_name(restore_apostrophes(match.group(1).strip()))
        result['title'] = clean_name(restore_apostrophes(match.group(2).strip()))
        result['pattern_matched'] = 'ytdlp_dash'
        return result

    # Pattern 4: Artist 'Album/Title' Subtitle-ID (generic quoted)
    match = re.match(r"^(.+?)\s*'(.+?)'\s*(.+?)?(?:-[a-zA-Z0-9_-]{11})?$", name)
    if match:
        result['artist'] = clean_name(restore_apostrophes(match.group(1).strip()))
        album_or_title = clean_name(restore_apostrophes(match.group(2).strip()))
        subtitle = clean_name(restore_apostrophes(match.group(3).strip())) if match.group(3) else None
        if subtitle:
            # Remove YouTube ID suffix if present
            subtitle = re.sub(r'-[a-zA-Z0-9_-]{11}$', '', subtitle).strip()
            result['title'] = f"{album_or_title} - {subtitle}" if subtitle else album_or_title
        else:
            result['title'] = album_or_title
        result['pattern_matched'] = 'quoted_title'
        return result

    # Pattern 5: Dailymotion style [shortID]
    # e.g., "FBI - ON A LE STYLE QUI CLAQUE [x28l79]"
    match = re.match(r'^(.+?)\s*-\s*(.+?)\s*\[[a-zA-Z0-9]+\]$', name)
    if match:
        result['artist'] = clean_name(restore_apostrophes(match.group(1).strip()))
        result['title'] = clean_name(restore_apostrophes(match.group(2).strip()))
        result['pattern_matched'] = 'dailymotion_brackets'
        return result

    # Pattern 6: Live set "Artist - Au Festival Year HDTV..."
    match = re.match(r'^(.+?)\s*-\s*Au\s+(.+?)\s+(\d{4})\s+HDTV', name, re.IGNORECASE)
    if match:
        result['artist'] = clean_name(restore_apostrophes(match.group(1).strip()))
        result['title'] = f"Live at {match.group(2)} {match.group(3)}"
        result['is_live_indicator'] = True
        result['pattern_matched'] = 'live_au_festival'
        return result

    # Pattern 7: Dotted live format
    # e.g., "Napalm.Death.-.Live.Deathfist.Festival..."
    match = re.match(r'^([^.]+(?:\.[^.]+)*?)\.?-\.?Live\.(.+?)\.WEB', name, re.IGNORECASE)
    if match:
        result['artist'] = clean_name(restore_apostrophes(match.group(1).replace('.', ' ').strip()))
        result['title'] = f"Live - {clean_name(restore_apostrophes(match.group(2).replace('.', ' ').strip()))}"
        result['is_live_indicator'] = True
        result['pattern_matched'] = 'dotted_live'
        return result

    # Pattern 8: Simple "Artist - Title" (most common)
    match = re.match(r'^(.+?)\s*-\s*(.+)$', name)
    if match:
        result['artist'] = clean_name(restore_apostrophes(match.group(1).strip()))
        result['title'] = clean_name(restore_apostrophes(match.group(2).strip()))
        result['pattern_matched'] = 'simple_dash'
        return result

    # Pattern 9: No clear separator - try to find artist at start
    # Could be "ArtistName SongTitle" but this is unreliable
    result['pattern_matched'] = 'none'
    result['title'] = clean_name(restore_apostrophes(name))  # Use whole name as title

    return result


def classify_video(duration: float, parse_result: dict) -> tuple[str, str]:
    """
    Classify video as music_video, live_set, or unknown.
    Returns (type, confidence)
    """
    is_long = duration > LIVE_SET_THRESHOLD if duration else False
    has_live_indicator = parse_result.get('is_live_indicator', False)

    if is_long and has_live_indicator:
        return 'live_set', 'high'
    elif is_long:
        return 'live_set', 'medium'
    elif has_live_indicator and not is_long:
        # Has live indicator but short - might be a single live performance
        return 'live_performance', 'medium'
    elif duration and duration < LIVE_SET_THRESHOLD:
        return 'music_video', 'high' if duration < 15 * 60 else 'medium'
    else:
        return 'unknown', 'low'


def process_directory(directory: str) -> list[VideoMetadata]:
    """Process all video files in directory."""
    from datetime import datetime

    results = []
    dir_path = Path(directory)

    for filepath in sorted(dir_path.iterdir()):
        if not filepath.is_file():
            continue

        if filepath.suffix.lower() not in VIDEO_EXTENSIONS:
            continue

        # Get video info
        probe = get_video_info(str(filepath))
        duration = probe.duration if probe else 0
        duration_formatted = format_duration(duration) if duration else "unknown"

        # Get file modification date
        try:
            mtime = filepath.stat().st_mtime
            file_date = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d')
        except OSError:
            file_date = "unknown"

        # Parse filename
        parse_result = parse_filename(filepath.name)

        # Classify
        video_type, confidence = classify_video(duration or 0, parse_result)

        metadata = VideoMetadata(
            filename=filepath.name,
            artist=parse_result['artist'],
            title=parse_result['title'],
            duration_seconds=duration or 0,
            duration_formatted=duration_formatted,
            video_type=video_type,
            confidence=confidence,
            raw_parse=parse_result,
            resolution=probe.resolution if probe else "unknown",
            video_codec=probe.video_codec if probe else "unknown",
            audio_codec=probe.audio_codec if probe else "unknown",
            bitrate=probe.bitrate if probe else "unknown",
            framerate=probe.framerate if probe else "unknown",
            filesize=probe.filesize if probe else "unknown",
            file_date=file_date,
            release_group=parse_result.get('release_group')
        )
        results.append(metadata)

    return results


def print_results(results: list[VideoMetadata], output_format: str = 'table', output_file: str = None):
    """Print results in specified format."""

    if output_format == 'json':
        output = []
        for r in results:
            output.append({
                'filename': r.filename,
                'artist': r.artist,
                'title': r.title,
                'duration': r.duration_formatted,
                'duration_seconds': r.duration_seconds,
                'type': r.video_type,
                'confidence': r.confidence,
                'resolution': r.resolution,
                'video_codec': r.video_codec,
                'audio_codec': r.audio_codec,
                'bitrate': r.bitrate,
                'framerate': r.framerate,
                'filesize': r.filesize,
                'file_date': r.file_date,
                'release_group': r.release_group
            })
        print(json.dumps(output, indent=2))
        return

    if output_format == 'csv':
        import csv

        fieldnames = ['filename', 'artist', 'title', 'duration', 'duration_seconds', 'type', 'confidence',
                      'resolution', 'video_codec', 'audio_codec', 'bitrate', 'framerate', 'filesize', 'file_date', 'release_group']

        # Determine output destination
        if output_file:
            f = open(output_file, 'w', newline='', encoding='utf-8')
        else:
            f = sys.stdout

        try:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in results:
                writer.writerow({
                    'filename': r.filename,
                    'artist': r.artist or '',
                    'title': r.title or '',
                    'duration': r.duration_formatted,
                    'duration_seconds': r.duration_seconds,
                    'type': r.video_type,
                    'confidence': r.confidence,
                    'resolution': r.resolution,
                    'video_codec': r.video_codec,
                    'audio_codec': r.audio_codec,
                    'bitrate': r.bitrate,
                    'framerate': r.framerate,
                    'filesize': r.filesize,
                    'file_date': r.file_date,
                    'release_group': r.release_group or ''
                })
            if output_file:
                print(f"CSV saved to: {output_file}")
        finally:
            if output_file:
                f.close()
        return

    # Table format
    print("\n" + "=" * 170)
    print("MUSIC VIDEO METADATA EXTRACTION RESULTS")
    print("=" * 170)

    # Separate by type
    music_videos = [r for r in results if r.video_type == 'music_video']
    live_sets = [r for r in results if r.video_type == 'live_set']
    live_performances = [r for r in results if r.video_type == 'live_performance']
    unknown = [r for r in results if r.video_type == 'unknown']

    def print_section(title: str, items: list[VideoMetadata]):
        if not items:
            return
        print(f"\n{title} ({len(items)} files)")
        print("-" * 170)
        print(f"{'Artist':<25} {'Title':<32} {'Duration':<10} {'Resolution':<12} {'Video':<8} {'Audio':<8} {'Bitrate':<11} {'Size':<11} {'Date':<12}")
        print("-" * 170)
        for item in items:
            artist = (item.artist or "Unknown")[:24]
            title = (item.title or "Unknown")[:31]
            print(f"{artist:<25} {title:<32} {item.duration_formatted:<10} {item.resolution:<12} {item.video_codec:<8} {item.audio_codec:<8} {item.bitrate:<11} {item.filesize:<11} {item.file_date:<12}")

    print_section("MUSIC VIDEOS", music_videos)
    print_section("LIVE SETS (Full concerts/DJ sets)", live_sets)
    print_section("LIVE PERFORMANCES (Single songs)", live_performances)
    print_section("UNKNOWN/UNCLASSIFIED", unknown)

    print("\n" + "=" * 170)
    print(f"Total files processed: {len(results)}")
    print(f"  Music videos: {len(music_videos)}")
    print(f"  Live sets: {len(live_sets)}")
    print(f"  Live performances: {len(live_performances)}")
    print(f"  Unknown: {len(unknown)}")
    print("=" * 170 + "\n")


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='Extract metadata from music video files'
    )
    parser.add_argument(
        'directory',
        nargs='?',
        default='.',
        help='Directory containing music videos (default: current directory)'
    )
    parser.add_argument(
        '-f', '--format',
        choices=['table', 'json', 'csv'],
        default='table',
        help='Output format (default: table)'
    )
    parser.add_argument(
        '-o', '--output',
        type=str,
        help='Output file path (for csv/json). If not specified, prints to stdout'
    )
    parser.add_argument(
        '-t', '--threshold',
        type=int,
        default=45,
        help='Duration threshold in minutes for live set classification (default: 45)'
    )

    args = parser.parse_args()

    global LIVE_SET_THRESHOLD
    LIVE_SET_THRESHOLD = args.threshold * 60

    directory = args.directory
    if not os.path.isdir(directory):
        print(f"Error: '{directory}' is not a valid directory", file=sys.stderr)
        sys.exit(1)

    print(f"Processing videos in: {os.path.abspath(directory)}")
    print(f"Live set threshold: {args.threshold} minutes")

    results = process_directory(directory)

    if not results:
        print("No video files found.")
        sys.exit(0)

    print_results(results, args.format, args.output)


if __name__ == '__main__':
    main()
