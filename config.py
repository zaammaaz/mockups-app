import json
import sys
from pathlib import Path


def get_config_path() -> Path:
    """Return path to config.json next to the exe (when frozen) or script."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent / "config.json"
    return Path(__file__).parent / "config.json"


def load_config() -> dict:
    """Load config from JSON file. Returns empty dict on any failure."""
    path = get_config_path()
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_config(data: dict) -> None:
    """Write config dict to JSON file."""
    path = get_config_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
