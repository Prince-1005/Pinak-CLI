import time
import json
import urllib.request
import threading
import importlib.metadata
from .config import config, save_config

UPDATE_AVAILABLE = None
UPDATE_PACKAGE = "yt-dlp"

def _check_update_thread():
    global UPDATE_AVAILABLE
    try:
        last_check = float(config.get("last_update_check", 0.0))
        current_time = time.time()
        
        # Check at most once every 24 hours (86400 seconds)
        if current_time - last_check < 86400:
            return
            
        req = urllib.request.Request(f"https://pypi.org/pypi/{UPDATE_PACKAGE}/json", headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode('utf-8'))
            
        latest_version_str = data.get("info", {}).get("version")
        if not latest_version_str:
            return
            
        try:
            current_version_str = importlib.metadata.version(UPDATE_PACKAGE)
        except importlib.metadata.PackageNotFoundError:
            return
            
        # Compare versions (yt-dlp versions are usually like "2023.11.16")
        def parse_version(v):
            return tuple(int(p) for p in v.split('.') if p.isdigit())
            
        if parse_version(latest_version_str) > parse_version(current_version_str):
            UPDATE_AVAILABLE = latest_version_str
            
        config["last_update_check"] = current_time
        save_config()
    except Exception:
        # Silently fail, it's a background daemon task
        pass

def start_background_update_check():
    t = threading.Thread(target=_check_update_thread, daemon=True)
    t.start()
