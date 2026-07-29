import sys
import os
import urllib.request
import yt_dlp
from rich.table import Table
from rich.console import Console

from .config import config, CONFIG_FILE
from .utils import get_ffmpeg_path, get_ffprobe_path, BOLD, RESET

console = Console()

def run_doctor():
    print(f"\n{BOLD}--- Pinak Doctor ---{RESET}")
    checks = []
    checks.append(("Python", sys.version.split()[0], True))
    checks.append(("yt-dlp", getattr(yt_dlp.version, "__version__", "installed"), True))
    checks.append(("ffmpeg.exe", get_ffmpeg_path(), os.path.exists(get_ffmpeg_path())))
    checks.append(("ffprobe.exe", get_ffprobe_path(), os.path.exists(get_ffprobe_path())))
    
    output_dir = config.get("output_dir", "downloads")
    try:
        os.makedirs(output_dir, exist_ok=True)
        test_file = os.path.join(output_dir, ".pinak_write_test")
        with open(test_file, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(test_file)
        output_ok = True
    except Exception:
        output_ok = False
    checks.append(("Output folder writable", os.path.abspath(output_dir), output_ok))
    
    config_detail = os.path.abspath(CONFIG_FILE) if os.path.exists(CONFIG_FILE) else "not found — run pinak to create it"
    checks.append(("Config file", config_detail, os.path.exists(CONFIG_FILE)))
    
    try:
        urllib.request.urlopen("https://www.google.com", timeout=5).close()
        internet_ok = True
    except Exception:
        internet_ok = False
    checks.append(("Internet Connection", "www.google.com accessible", internet_ok))
    
    table = Table(title="Pinak Doctor Diagnostics", style="blue")
    table.add_column("Check", style="cyan")
    table.add_column("Details", style="magenta")
    table.add_column("Status", justify="center")

    for name, detail, ok in checks:
        status_text = "[green]OK[/]" if ok else "[red]FAIL[/]"
        table.add_row(name, str(detail), status_text)
    
    console.print(table)
