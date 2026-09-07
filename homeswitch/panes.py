from __future__ import annotations

import json
from pathlib import Path

from homeswitch.bus import PaneState
from homeswitch.paths import panes_dir, sockets_dir, ensure_dirs


def pane_file(pane_id: str) -> Path:
    return panes_dir() / f"{pane_id}.json"


def write_pane(state: PaneState) -> Path:
    ensure_dirs()
    path = pane_file(state.pane_id)
    path.write_text(json.dumps(state.to_dict(), indent=2) + "\n", encoding="utf-8")
    return path


def read_pane(pane_id: str) -> PaneState | None:
    path = pane_file(pane_id)
    if not path.is_file():
        return None
    return PaneState.from_dict(json.loads(path.read_text(encoding="utf-8")))


def remove_pane(pane_id: str) -> None:
    pane_file(pane_id).unlink(missing_ok=True)
    sock = sockets_dir() / f"{pane_id}.sock"
    sock.unlink(missing_ok=True)


def list_panes() -> list[PaneState]:
    ensure_dirs()
    out: list[PaneState] = []
    for path in sorted(panes_dir().glob("*.json")):
        try:
            state = PaneState.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError, KeyError):
            continue
        live = sockets_dir().joinpath(f"{state.pane_id}.sock").exists()
        if live:
            out.append(state)
    return out
