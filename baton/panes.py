from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from baton.bus import PaneState, is_pane_listening
from baton.dirs import encode_claude_project
from baton.paths import panes_dir, sockets_dir, ensure_dirs


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
        if not is_pane_listening(state.pane_id):
            if sockets_dir().joinpath(f"{state.pane_id}.sock").exists():
                remove_pane(state.pane_id)
            continue
        out.append(state)
    return out


def panes_for_cwd(
    cwd: Path | None = None,
    panes: list[PaneState] | None = None,
) -> list[PaneState]:
    here = (cwd or Path.cwd()).resolve()
    if panes is None:
        panes = list_panes()
    return [p for p in panes if Path(p.cwd).resolve() == here]


def panes_for_cwds(
    cwds: Sequence[Path | str],
    panes: list[PaneState] | None = None,
) -> list[PaneState]:
    if panes is None:
        panes = list_panes()
    seen: set[str] = set()
    out: list[PaneState] = []
    for raw in cwds:
        for pane in panes_for_cwd(Path(raw), panes):
            if pane.pane_id in seen:
                continue
            seen.add(pane.pane_id)
            out.append(pane)
    return out


def panes_for_transcript(
    transcript_path: str,
    panes: list[PaneState] | None = None,
) -> list[PaneState]:
    """Match a pane whose project encoding appears in a vendor transcript path.

    Cursor IDE: ``~/.cursor/projects/<abs-cwd-with-slashes-as-dashes>/…``
    Claude Code: ``~/.claude/projects/<encode_claude_project(cwd)>/…``
    """
    if panes is None:
        panes = list_panes()
    text = transcript_path.replace("\\", "/")
    if not text:
        return []
    out: list[PaneState] = []
    seen: set[str] = set()
    for pane in panes:
        resolved = Path(pane.cwd).resolve()
        slugs = (
            str(resolved).lstrip("/").replace("/", "-"),
            encode_claude_project(resolved),
        )
        if not any(_project_slug_in_transcript(text, slug) for slug in slugs):
            continue
        if pane.pane_id in seen:
            continue
        seen.add(pane.pane_id)
        out.append(pane)
    return out


def _project_slug_in_transcript(text: str, slug: str) -> bool:
    if not slug:
        return False
    needle = f"/projects/{slug}"
    return needle + "/" in text or text.endswith(needle)
