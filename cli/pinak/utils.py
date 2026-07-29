import os
import re
import sys
import webbrowser
from pathlib import Path

# ANSI Color Codes
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
RESET = "\033[0m"
BOLD = "\033[1m"

def script_dir():
    """Returns the cli/ root directory where ffmpeg.exe / ffprobe.exe are stored.

    Search order (first directory that contains ffmpeg.exe wins):
      1. The directory of *this* file's package parent (cli/)
      2. The directory of *this* file (cli/pinak/) — edge case
      3. The current working directory
    Falls back gracefully to PATH lookup.
    """
    pkg_dir = os.path.dirname(os.path.abspath(__file__))   # …/cli/pinak
    cli_dir = os.path.dirname(pkg_dir)                     # …/cli
    for candidate in (cli_dir, pkg_dir, os.getcwd()):
        if os.path.exists(os.path.join(candidate, "ffmpeg.exe")):
            return candidate
    return cli_dir  # best guess even if binary not found there

def get_ffmpeg_path():
    """Return absolute path to ffmpeg.exe, or just 'ffmpeg' for PATH fallback."""
    path = os.path.join(script_dir(), "ffmpeg.exe")
    if os.path.exists(path):
        return path
    import shutil
    found = shutil.which("ffmpeg")
    return found if found else "ffmpeg"

def get_ffprobe_path():
    """Return absolute path to ffprobe.exe, or just 'ffprobe' for PATH fallback."""
    path = os.path.join(script_dir(), "ffprobe.exe")
    if os.path.exists(path):
        return path
    import shutil
    found = shutil.which("ffprobe")
    return found if found else "ffprobe"

def human_duration(seconds):
    try:
        seconds = int(seconds)
    except (TypeError, ValueError):
        return "unknown"
    mins, secs = divmod(seconds, 60)
    hours, mins = divmod(mins, 60)
    if hours:
        return f"{hours}h {mins}m {secs}s"
    if mins:
        return f"{mins}m {secs}s"
    return f"{secs}s"

def human_size(bytes_sz):
    try:
        bytes_sz = float(bytes_sz or 0)
    except (TypeError, ValueError):
        return "unknown"
    if bytes_sz == 0:
        return "0 B"
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_sz < 1024.0:
            return f"{bytes_sz:.1f} {unit}"
        bytes_sz /= 1024.0
    return f"{bytes_sz:.1f} TB"

def get_all_files(folder):
    files = {}
    for root, _, filenames in os.walk(folder):
        for f in filenames:
            full_path = os.path.join(root, f)
            try:
                files[full_path] = os.path.getmtime(full_path)
            except OSError:
                pass
    return files

def get_file_snapshot(folder):
    if not os.path.exists(folder):
        return {}
    return get_all_files(folder)

def changed_files(before, after):
    files = []
    for path, state in after.items():
        if before.get(path) != state:
            files.append(path)
    return sorted(files)

def has_embedded_thumbnail(file_path):
    ffprobe = get_ffprobe_path()
    if not os.path.exists(ffprobe) or not os.path.exists(file_path):
        return False
    import subprocess
    cmd = [
        ffprobe, "-v", "error", "-select_streams", "v",
        "-show_streams", "-of", "json", file_path
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        import json
        data = json.loads(res.stdout)
        if "streams" in data:
            for stream in data["streams"]:
                disposition = stream.get("disposition", {})
                if str(disposition.get("attached_pic", 0)) == "1":
                    return True
    except Exception:
        pass
    return False

def has_embedded_subtitle(file_path):
    ffprobe = get_ffprobe_path()
    if not os.path.exists(ffprobe) or not os.path.exists(file_path):
        return False
    import subprocess
    cmd = [
        ffprobe, "-v", "error", "-select_streams", "s",
        "-show_entries", "stream=codec_type", "-of", "json", file_path
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        import json
        data = json.loads(res.stdout)
        if data.get("programs") or data.get("streams"):
            return True
    except Exception:
        pass
    return False

def get_clipboard_text():
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        text = root.clipboard_get()
        root.destroy()
        return text.strip()
    except Exception:
        return ""

def is_online():
    import urllib.request
    try:
        urllib.request.urlopen("https://www.google.com", timeout=3).close()
        return True
    except Exception:
        return False

def get_platform(url):
    try:

        import yt_dlp
        extractors = yt_dlp.extractor.gen_extractors()
        for ie in extractors:
            if ie.suitable(url) and ie.IE_NAME != 'generic':
                return ie.IE_NAME.split(':')[0].capitalize()
    except Exception:
        pass
    return "Unknown"

def normalize_quality(value):
    value = (value or "best").strip().lower()
    aliases = {"audio": "audio", "mp3": "audio", "best": "best", "worst": "worst"}
    if value in aliases:
        return aliases[value]
    match = re.fullmatch(r"(\d{3,4})p?", value)
    if match:
        return f"{match.group(1)}p"
    return None

def video_format_for_quality(quality):
    quality = normalize_quality(quality) or "best"
    if quality == "worst":
        return "worst"
    if quality.endswith("p"):
        height = quality[:-1]
        return f"bestvideo[height<={height}]+bestaudio/best[height<={height}]/best"
    return "bestvideo+bestaudio/best"
