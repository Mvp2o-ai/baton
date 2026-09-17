from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from baton import __version__
from baton.dirs import encode_claude_project, cursor_workspace_hash


ROOT = Path(__file__).resolve().parents[1]
LOCATOR = ROOT / "skills" / "catch-up-on-previous-thread" / "scripts" / "locate_previous.py"
SKILL = ROOT / "skills" / "catch-up-on-previous-thread" / "SKILL.md"


def test_versions_match():
    pkg = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert pkg["version"] == __version__
    assert f'version = "{__version__}"' in pyproject


def test_catch_up_skill_documents_all_jsonl_trees():
    text = SKILL.read_text(encoding="utf-8")
    assert "agent-transcripts" in text
    assert "rollout-" in text
    assert "session_meta" in text
    assert "store.db" in text
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Catch up without hopping" in readme
    assert "skills/catch-up-on-previous-thread" in readme


def _env_for(home: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["CLAUDE_CONFIG_DIR"] = str(home / ".claude")
    env["CODEX_HOME"] = str(home / ".codex")
    env.pop("CURSOR_STORE_ROOT", None)
    env.pop("CURSOR_DATA_PATH", None)
    env.pop("XDG_CONFIG_HOME", None)
    return env


def test_locate_previous_lists_cursor_claude_and_codex(tmp_path):
    home = tmp_path / "home"
    cwd = tmp_path / "proj"
    cwd.mkdir(parents=True)
    work = cwd.resolve()

    slug = str(work).replace("/", "-").lstrip("-")
    cursor_jsonl = (
        home / ".cursor" / "projects" / slug / "agent-transcripts" / "aaa" / "aaa.jsonl"
    )
    cursor_jsonl.parent.mkdir(parents=True)
    cursor_jsonl.write_text(
        json.dumps({"role": "user", "message": {"content": [{"type": "text", "text": "cursor"}]}})
        + "\n",
        encoding="utf-8",
    )

    claude_jsonl = (
        home / ".claude" / "projects" / encode_claude_project(work) / "sid.jsonl"
    )
    claude_jsonl.parent.mkdir(parents=True)
    claude_jsonl.write_text(
        json.dumps({"type": "user", "cwd": str(work), "message": {"content": "claude"}})
        + "\n",
        encoding="utf-8",
    )

    other_id = "019aaaaa-bbbb-7ccc-dddd-eeeeeeeeeeee"
    other = (
        home
        / ".codex"
        / "sessions"
        / "2026"
        / "09"
        / "17"
        / f"rollout-2026-09-17T12-00-00-{other_id}.jsonl"
    )
    mine_id = "019bbbbb-cccc-7ddd-eeee-ffffffffffff"
    mine = (
        home
        / ".codex"
        / "sessions"
        / "2026"
        / "09"
        / "17"
        / f"rollout-2026-09-17T13-00-00-{mine_id}.jsonl"
    )
    mine.parent.mkdir(parents=True)
    other.write_text(
        json.dumps(
            {
                "type": "session_meta",
                "payload": {"cwd": "/somewhere/else", "id": other_id},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    mine.write_text(
        json.dumps(
            {"type": "session_meta", "payload": {"cwd": str(work), "id": mine_id}}
        )
        + "\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(LOCATOR), "--cwd", str(work)],
        env=_env_for(home),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    harnesses = {line.split("\t")[0] for line in lines}
    assert harnesses == {"cursor_ide", "claude", "codex"}
    assert str(cursor_jsonl) in result.stdout
    assert str(claude_jsonl) in result.stdout
    assert str(mine) in result.stdout
    assert str(other) not in result.stdout
    # store.db is not this skill
    assert cursor_workspace_hash(work)
    assert "store.db" not in result.stdout
