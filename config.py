"""
Application configuration and persistent settings management.
Stores config in ~/.interviewagent/config.json
"""

import os
import json

# Base data directory
DATA_DIR = os.path.expanduser("~/.interviewagent")
DOCUMENTS_DIR = os.path.join(DATA_DIR, "documents")
DB_PATH = os.path.join(DATA_DIR, "chats.db")
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")

# Default configuration
DEFAULTS = {
    "groq_api_key": "",
    "whisper_model": "base.en",
    "window_width": 420,
    "window_height": 600,
    "window_opacity": 0.92,
    "window_x": 100,
    "window_y": 100,
    "sample_rate": 16000,
    "audio_chunk_seconds": 2,
    "silence_threshold": 0.01,
    "silence_duration": 2.0,
    "groq_model": "llama-3.3-70b-versatile",
    "max_context_tokens": 4000,
}


def ensure_dirs():
    """Create data directories if they don't exist."""
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(DOCUMENTS_DIR, exist_ok=True)


def load_config() -> dict:
    """Load configuration from disk, merging with defaults."""
    ensure_dirs()
    config = dict(DEFAULTS)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r") as f:
                saved = json.load(f)
            config.update(saved)
        except (json.JSONDecodeError, IOError):
            pass
    return config


def save_config(config: dict):
    """Save configuration to disk."""
    ensure_dirs()
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)


def get_api_key() -> str:
    """Get the Groq API key from config."""
    return load_config().get("groq_api_key", "")


def set_api_key(key: str):
    """Save the Groq API key."""
    config = load_config()
    config["groq_api_key"] = key
    save_config(config)
