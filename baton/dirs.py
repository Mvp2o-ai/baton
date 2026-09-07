"""Canonical on-disk roots for Claude Code, Codex, and Cursor CLI.

Paths follow vendor docs and txcript store defaults (checked 2026-09).
Baton never writes into these trees itself — txcript and the home CLIs do.
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path


def _home() -> Path:
    return Path.home()


def claude_config_dir() -> Path:
    """Claude Code config root.

    Official: ``CLAUDE_CONFIG_DIR`` relocates every ``~/.claude`` path.
    Default: ``~/.claude``.
    """
    override = os.environ.get("CLAUDE_CONFIG_DIR")
    if override:
        return Path(override).expanduser()
    return _home() / ".claude"


def claude_projects_dir() -> Path:
    """Session transcripts live under ``<config>/projects/``.

    Official layout: ``~/.claude/projects/<encoded-cwd>/<session-id>.jsonl``
    Some installs also nest files in a ``sessions/`` subdirectory.
    """
    return claude_config_dir() / "projects"


def encode_claude_project(cwd: str | Path) -> str:
    """Encode an absolute cwd the way Claude Code names project folders.

    Non-alphanumeric characters become ``-``. Paths that would exceed 200
    characters are truncated and a short hash of the original path is appended.
    """
    raw = str(Path(cwd))
    encoded = re.sub(r"[^A-Za-z0-9]", "-", raw)
    if len(encoded) <= 200:
        return encoded
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:10]
    return f"{encoded[:189]}-{digest}"


def claude_project_dir(cwd: str | Path) -> Path:
    return claude_projects_dir() / encode_claude_project(Path(cwd).resolve())


def codex_home() -> Path:
    """Codex state root. Official default ``~/.codex`` via ``CODEX_HOME``.

    If ``CODEX_HOME`` is set, Codex requires that directory to already exist.
    """
    override = os.environ.get("CODEX_HOME")
    if override:
        return Path(override).expanduser()
    return _home() / ".codex"


def codex_sessions_dir() -> Path:
    """Rollouts: ``$CODEX_HOME/sessions/YYYY/MM/DD/rollout-<ts>-<uuid>.jsonl``."""
    return codex_home() / "sessions"


def codex_archived_sessions_dir() -> Path:
    return codex_home() / "archived_sessions"


def codex_sqlite_home() -> Path:
    """SQLite thread index (``state_*.sqlite``). ``CODEX_SQLITE_HOME`` or Codex home."""
    override = os.environ.get("CODEX_SQLITE_HOME")
    if override:
        return Path(override).expanduser()
    return codex_home()


def cursor_store_root() -> Path:
    """Cursor CLI *store stack* root (not the IDE ``state.vscdb`` tree).

    Resolution order, matching what txcript and Cursor-history tools observe:

    1. ``CURSOR_STORE_ROOT``
    2. ``CURSOR_DATA_PATH`` when it looks like a store tree
    3. ``$XDG_CONFIG_HOME/cursor`` when that tree exists (Linux XDG)
    4. ``~/.cursor``
    """
    store_root = os.environ.get("CURSOR_STORE_ROOT")
    if store_root:
        return Path(store_root).expanduser()

    data_path = os.environ.get("CURSOR_DATA_PATH")
    if data_path:
        candidate = Path(data_path).expanduser()
        resolved = _normalize_cursor_store(candidate)
        if resolved is not None:
            return resolved

    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        xdg_cursor = Path(xdg).expanduser() / "cursor"
        if (xdg_cursor / "chats").is_dir() or (xdg_cursor / "projects").is_dir():
            return xdg_cursor

    return _home() / ".cursor"


def _normalize_cursor_store(path: Path) -> Path | None:
    if not path.exists():
        return None
    name = path.name
    if name in {"chats", "projects", "acp-sessions"}:
        return path.parent
    if (path / "chats").exists() or (path / "projects").exists():
        return path
    return None


def cursor_chats_dir() -> Path:
    """CLI resumable chats: ``<store>/chats/<md5(abs-cwd)>/<session-uuid>/store.db``.

    This is the tree txcript's ``cursor`` harness reads and writes.
    It is **not** Cursor desktop ``state.vscdb``.
    """
    return cursor_store_root() / "chats"


def cursor_projects_dir() -> Path:
    """Optional JSONL transcripts: ``<store>/projects/<slug>/agent-transcripts/``."""
    return cursor_store_root() / "projects"


def cursor_workspace_hash(cwd: str | Path) -> str:
    """Lowercase hex MD5 of the absolute workspace path (txcript CursorStore)."""
    absolute = str(Path(cwd).resolve())
    return hashlib.md5(absolute.encode("utf-8"), usedforsecurity=False).hexdigest()


def cursor_workspace_chats_dir(cwd: str | Path) -> Path:
    return cursor_chats_dir() / cursor_workspace_hash(cwd)


@dataclass(frozen=True)
class HarnessDirs:
    harness: str
    config_or_home: Path
    sessions: Path
    notes: str


def describe_all(cwd: str | Path | None = None) -> list[HarnessDirs]:
    work = Path(cwd).resolve() if cwd else Path.cwd()
    return [
        HarnessDirs(
            harness="claude_code",
            config_or_home=claude_config_dir(),
            sessions=claude_project_dir(work),
            notes="JSONL; CLAUDE_CONFIG_DIR relocates ~/.claude",
        ),
        HarnessDirs(
            harness="codex",
            config_or_home=codex_home(),
            sessions=codex_sessions_dir(),
            notes="date-sharded rollouts; CODEX_HOME relocates ~/.codex",
        ),
        HarnessDirs(
            harness="cursor",
            config_or_home=cursor_store_root(),
            sessions=cursor_workspace_chats_dir(work),
            notes="store.db per session; CLI only — not Cursor desktop",
        ),
    ]
