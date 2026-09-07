from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from homeswitch.catalog import HARNESS_CLAUDE, HARNESS_CODEX, HARNESS_CURSOR
from homeswitch.dirs import (
    claude_project_dir,
    codex_archived_sessions_dir,
    codex_sessions_dir,
    cursor_workspace_chats_dir,
)


_CODEX_ROLLOUT_RE = re.compile(
    r"rollout-.*-([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})"
)


@dataclass(frozen=True)
class NativeSession:
    harness: str
    session_id: str
    path: Path
    mtime: float


def list_sessions(harness: str, cwd: str | Path) -> list[NativeSession]:
    work = Path(cwd).resolve()
    if harness == HARNESS_CLAUDE:
        found = _claude_sessions(work)
    elif harness == HARNESS_CODEX:
        found = _codex_sessions()
    elif harness == HARNESS_CURSOR:
        found = _cursor_sessions(work)
    else:
        raise KeyError(f"unknown harness {harness!r}")
    found.sort(key=lambda item: item.mtime, reverse=True)
    return found


def latest_session(harness: str, cwd: str | Path) -> NativeSession | None:
    items = list_sessions(harness, cwd)
    return items[0] if items else None


def _claude_sessions(cwd: Path) -> list[NativeSession]:
    root = claude_project_dir(cwd)
    if not root.is_dir():
        return []
    out: list[NativeSession] = []
    for path in root.rglob("*.jsonl"):
        if path.name.startswith("agent-"):
            continue
        session_id = path.stem
        out.append(
            NativeSession(
                harness=HARNESS_CLAUDE,
                session_id=session_id,
                path=path,
                mtime=path.stat().st_mtime,
            )
        )
    return out


def _codex_sessions() -> list[NativeSession]:
    out: list[NativeSession] = []
    for root in (codex_sessions_dir(), codex_archived_sessions_dir()):
        if not root.is_dir():
            continue
        for path in root.rglob("rollout-*.jsonl"):
            session_id = _codex_id_from_name(path.name)
            if not session_id:
                continue
            out.append(
                NativeSession(
                    harness=HARNESS_CODEX,
                    session_id=session_id,
                    path=path,
                    mtime=path.stat().st_mtime,
                )
            )
    return out


def _codex_id_from_name(name: str) -> str | None:
    match = _CODEX_ROLLOUT_RE.search(name)
    if match:
        return match.group(1)
    # Fallback: last token after the final hyphen before .jsonl when it looks like a uuid.
    stem = name.removesuffix(".jsonl")
    parts = stem.split("-")
    if len(parts) >= 5:
        maybe = "-".join(parts[-5:])
        if len(maybe) >= 32:
            return maybe
    return None


def _cursor_sessions(cwd: Path) -> list[NativeSession]:
    root = cursor_workspace_chats_dir(cwd)
    if not root.is_dir():
        return []
    out: list[NativeSession] = []
    for child in root.iterdir():
        if not child.is_dir():
            continue
        store = child / "store.db"
        meta = child / "meta.json"
        if not store.is_file() and not meta.is_file():
            continue
        stamp = store if store.is_file() else meta
        out.append(
            NativeSession(
                harness=HARNESS_CURSOR,
                session_id=child.name,
                path=store if store.is_file() else meta,
                mtime=stamp.stat().st_mtime,
            )
        )
    return out


def session_to_dict(item: NativeSession) -> dict:
    return {
        "harness": item.harness,
        "session_id": item.session_id,
        "path": str(item.path),
        "mtime": item.mtime,
    }


def try_read_cursor_title(session_dir: Path) -> str | None:
    meta = session_dir / "meta.json"
    if not meta.is_file():
        return None
    try:
        data = json.loads(meta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    title = data.get("title")
    return str(title) if title else None
