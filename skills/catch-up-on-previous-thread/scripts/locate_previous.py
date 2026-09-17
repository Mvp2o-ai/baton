#!/usr/bin/env python3
"""List JSONL sessions for this cwd from Cursor IDE, Claude Code, and Codex.

Stdlib only. Does not import Baton. Path rules match docs/directories.md.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path


def _home() -> Path:
    return Path.home()


def encode_claude_project(cwd: Path) -> str:
    raw = str(cwd.resolve())
    encoded = re.sub(r"[^A-Za-z0-9]", "-", raw)
    if len(encoded) <= 200:
        return encoded
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:10]
    return f"{encoded[:189]}-{digest}"


def cursor_ide_slug(cwd: Path) -> str:
    return str(cwd.resolve()).replace("/", "-").lstrip("-")


def claude_config_dir() -> Path:
    override = os.environ.get("CLAUDE_CONFIG_DIR")
    if override:
        return Path(override).expanduser()
    return _home() / ".claude"


def codex_home() -> Path:
    override = os.environ.get("CODEX_HOME")
    if override:
        return Path(override).expanduser()
    return _home() / ".codex"


def cursor_project_roots() -> list[Path]:
    roots: list[Path] = []
    store = os.environ.get("CURSOR_STORE_ROOT")
    if store:
        roots.append(Path(store).expanduser() / "projects")
    data = os.environ.get("CURSOR_DATA_PATH")
    if data:
        candidate = Path(data).expanduser()
        if candidate.name == "projects":
            roots.append(candidate)
        else:
            roots.append(candidate / "projects")
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        roots.append(Path(xdg).expanduser() / "cursor" / "projects")
    roots.append(_home() / ".cursor" / "projects")
    seen: set[Path] = set()
    out: list[Path] = []
    for root in roots:
        resolved = root
        try:
            resolved = root.resolve()
        except OSError:
            pass
        if resolved in seen:
            continue
        seen.add(resolved)
        out.append(root)
    return out


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _iso(mtime: float) -> str:
    return datetime.fromtimestamp(mtime, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def collect_cursor_ide(cwd: Path) -> list[tuple[str, float, Path]]:
    slug = cursor_ide_slug(cwd)
    found: list[tuple[str, float, Path]] = []
    seen: set[Path] = set()
    for root in cursor_project_roots():
        transcripts = root / slug / "agent-transcripts"
        if not transcripts.is_dir():
            continue
        for path in transcripts.rglob("*.jsonl"):
            try:
                resolved = path.resolve()
            except OSError:
                continue
            if resolved in seen:
                continue
            seen.add(resolved)
            found.append(("cursor_ide", _mtime(path), path))
    return found


def collect_claude(cwd: Path) -> list[tuple[str, float, Path]]:
    root = claude_config_dir() / "projects" / encode_claude_project(cwd)
    if not root.is_dir():
        return []
    found: list[tuple[str, float, Path]] = []
    for path in root.rglob("*.jsonl"):
        if path.name.startswith("agent-"):
            continue
        found.append(("claude", _mtime(path), path))
    return found


def _codex_cwd(path: Path) -> str | None:
    try:
        with path.open(encoding="utf-8") as handle:
            line = handle.readline()
    except OSError:
        return None
    if not line:
        return None
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        return None
    if obj.get("type") != "session_meta":
        return None
    payload = obj.get("payload")
    if not isinstance(payload, dict):
        return None
    recorded = payload.get("cwd")
    return recorded if isinstance(recorded, str) and recorded else None


def collect_codex(cwd: Path) -> list[tuple[str, float, Path]]:
    want = cwd.resolve()
    found: list[tuple[str, float, Path]] = []
    for folder in (codex_home() / "sessions", codex_home() / "archived_sessions"):
        if not folder.is_dir():
            continue
        for path in folder.rglob("rollout-*.jsonl"):
            recorded = _codex_cwd(path)
            if not recorded:
                continue
            try:
                if Path(recorded).expanduser().resolve() != want:
                    continue
            except OSError:
                continue
            found.append(("codex", _mtime(path), path))
    return found


def locate(cwd: Path) -> list[tuple[str, float, Path]]:
    rows = collect_cursor_ide(cwd) + collect_claude(cwd) + collect_codex(cwd)
    rows.sort(key=lambda item: item[1], reverse=True)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cwd", default=None, help="Project directory (default: current directory)")
    parser.add_argument("-n", type=int, default=15, help="Max rows (default 15)")
    args = parser.parse_args()
    work = Path(args.cwd).expanduser().resolve() if args.cwd else Path.cwd()
    rows = locate(work)
    if not rows:
        print(f"No JSONL sessions for {work}", flush=True)
        return 1
    for harness, mtime, path in rows[: args.n]:
        print(f"{harness}\t{_iso(mtime)}\t{path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
