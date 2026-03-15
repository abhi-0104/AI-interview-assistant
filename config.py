"""
Application configuration and persistent settings management.
Stores config in ~/.interviewagent/config.json
"""

import os
import json

# Optional: macOS Keychain storage for the API key
try:
    import keyring
    _USE_KEYRING = True
except ImportError:
    _USE_KEYRING = False

KEYRING_SERVICE = "SystemManagementService"
OPENROUTER_KEYRING_USERNAME = "sys_token_or"

# Base data directory
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
# Obfuscated path in Library/Application Support
DATA_DIR = os.path.expanduser("~/Library/Application Support/com.apple.SystemManagementService")
DOCUMENTS_DIR = os.path.join(DATA_DIR, "docs")
DB_PATH = os.path.join(DATA_DIR, "data.db")
CONFIG_PATH = os.path.join(DATA_DIR, "settings.json")
ENV_PATH = os.path.join(PROJECT_DIR, ".env")

# Default configuration
DEFAULTS = {
    "openrouter_api_key": "",
    "whisper_model": "base.en",
    "window_width": 420,
    "window_height": 600,
    "window_opacity": 0.92,
    "window_x": 100,
    "window_y": 100,
    "sample_rate": 16000,
    "audio_chunk_seconds": 10,
    "silence_threshold": 0.005,
    "silence_duration": 1.5,
    "openrouter_model": "qwen/qwen3-coder:free",
    "max_context_tokens": 4000,
    "app_mode": "interview",  # "interview" or "assessment"
}


def ensure_dirs():
    """Create data directories if they don't exist."""
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(DOCUMENTS_DIR, exist_ok=True)


def _read_env_file() -> dict:
    """Read key-value pairs from the local .env file."""
    values = {}
    try:
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip('"').strip("'")
    except OSError:
        return {}
    return values


def _write_env_value(name: str, value: str):
    """Create or update a variable inside the local .env file, preserving other entries."""
    existing = _read_env_file()
    existing[name] = value.strip()

    lines = ["# Local secrets for InterviewAgent"]
    for k, v in existing.items():
        lines.append(f'{k}="{v}"')
    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


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


def get_openrouter_api_key() -> str:
    """Get the OpenRouter API key."""
    file_key = _read_env_file().get("OPENROUTER_API_KEY", "")
    if file_key:
        return file_key

    if _USE_KEYRING:
        try:
            key = keyring.get_password(KEYRING_SERVICE, OPENROUTER_KEYRING_USERNAME)
            if key:
                return key
        except Exception:
            pass

    config = load_config()
    return config.get("openrouter_api_key", "")


def set_openrouter_api_key(key: str):
    """Save the OpenRouter API key."""
    _write_env_value("OPENROUTER_API_KEY", key)

    cfg = load_config()
    if cfg.get("openrouter_api_key"):
        cfg["openrouter_api_key"] = ""
        save_config(cfg)

    if _USE_KEYRING:
        try:
            keyring.set_password(KEYRING_SERVICE, OPENROUTER_KEYRING_USERNAME, key)
        except Exception:
            pass


def get_api_key() -> str:
    """Backward-compatible alias for the OpenRouter API key."""
    return get_openrouter_api_key()


def set_api_key(key: str):
    """Backward-compatible alias for storing the OpenRouter API key."""
    set_openrouter_api_key(key)
