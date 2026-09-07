from __future__ import annotations

import os
from pathlib import Path


def home_dir() -> Path:
    override = os.environ.get("HOMESWITCH_HOME")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".homeswitch"


def config_path() -> Path:
    return home_dir() / "config.json"


def panes_dir() -> Path:
    return home_dir() / "panes"


def sockets_dir() -> Path:
    return home_dir() / "sockets"


def ensure_dirs() -> None:
    home_dir().mkdir(parents=True, exist_ok=True)
    panes_dir().mkdir(parents=True, exist_ok=True)
    sockets_dir().mkdir(parents=True, exist_ok=True)
