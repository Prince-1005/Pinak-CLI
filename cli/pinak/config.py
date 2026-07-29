import os
import json
import shutil
import platformdirs
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

APP_NAME = "pinak-cli"
APP_AUTHOR = "pinak"

# Determine standard config directory
config_dir = platformdirs.user_config_dir(APP_NAME, APP_AUTHOR)
os.makedirs(config_dir, exist_ok=True)
CONFIG_FILE = os.path.join(config_dir, "config.json")
LOCAL_CONFIG = ".pinak_config.json"

class PinakSettings(BaseSettings):
    output_dir: str = Field(default="downloads", description="Directory to save downloaded files")
    quality: str = Field(default="best", description="Video quality preference")
    audio_quality: str = Field(default="192", description="Audio quality preference (kbps)")
    video_format: str = Field(default="mp4", description="Preferred video format")
    audio_format: str = Field(default="mp3", description="Preferred audio format")
    retry_count: int = Field(default=3, description="Number of retries for failed downloads")
    embed_subs: bool = Field(default=False, description="Whether to embed subtitles")
    auto_sort: bool = Field(default=False, description="Auto sort into platform folders")
    rate_limit_count: int = Field(default=5, description="Max downloads per rate limit window")
    rate_limit_hours: int = Field(default=1, description="Rate limit window in hours")
    force_rate_limit_count: int = Field(default=5, description="Max forced downloads per rate limit window")
    duplicate_action: str = Field(default="ask", description="Action to take for duplicate URLs")
    username: str = Field(default="", description="User's preferred name")
    greeting: str = Field(default="Har Har Mahadev 🔱", description="Greeting message")
    last_update_check: float = Field(default=0.0, description="Timestamp of the last update check")
    device_id: str = Field(default_factory=lambda: __import__('uuid').uuid4().hex, description="Unique device identifier")

    model_config = SettingsConfigDict(
        env_prefix="PINAK_", 
        env_file=".env", 
        env_file_encoding="utf-8",
        extra="ignore"
    )

# Legacy global dictionary for backward compatibility across modules
config = PinakSettings().model_dump()

def init_config():
    global config
    
    # Migrate legacy ~/.pinak_config.json if exists
    legacy_home_config = os.path.expanduser("~/.pinak_config.json")
    if not os.path.exists(CONFIG_FILE):
        if os.path.exists(legacy_home_config):
            shutil.copy(legacy_home_config, CONFIG_FILE)
        elif os.path.exists(LOCAL_CONFIG):
            shutil.copy(LOCAL_CONFIG, CONFIG_FILE)

    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            # Load with Pydantic for validation
            settings = PinakSettings(**data)
            config.update(settings.model_dump())
    except Exception:
        pass
        
    return config

def save_config(config_data=None):
    global config
    if config_data is not None:
        config.update(config_data)
        
    try:
        # Validate data before saving
        valid_settings = PinakSettings(**config)
        config.update(valid_settings.model_dump())
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            f.write(valid_settings.model_dump_json(indent=4))
        return True
    except Exception as e:
        print(f"\033[91m[X] Could not write {CONFIG_FILE}: {e}\033[0m")
        return False
