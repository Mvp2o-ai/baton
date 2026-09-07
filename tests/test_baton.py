from __future__ import annotations

import json
from pathlib import Path

import pytest

from baton.catalog import HARNESS_CLAUDE, get_model, models_from_dicts
from baton.clis import discover, which_first
from baton.dirs import (
    claude_config_dir,
    claude_project_dir,
    codex_home,
    cursor_chats_dir,
    cursor_store_root,
    cursor_workspace_hash,
    encode_claude_project,
)
from baton.discover import _codex_id_from_name, list_sessions
from baton.launch import launch_argv
from baton.txcript_parse import parse_continue_output, strip_ansi


def test_encode_claude_project_replaces_non_alnum():
    encoded = encode_claude_project("/Users/ken/dev/mcp-code-execution")
    assert encoded == "-Users-ken-dev-mcp-code-execution"


def test_claude_config_dir_override(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    assert claude_config_dir() == tmp_path / "claude"
    assert claude_project_dir("/tmp/proj").parent == tmp_path / "claude" / "projects"


def test_codex_home_override(monkeypatch, tmp_path):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex"))
    assert codex_home() == tmp_path / "codex"


def test_cursor_store_xdg(monkeypatch, tmp_path):
    xdg = tmp_path / "xdg"
    (xdg / "cursor" / "chats").mkdir(parents=True)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
    monkeypatch.delenv("CURSOR_STORE_ROOT", raising=False)
    monkeypatch.delenv("CURSOR_DATA_PATH", raising=False)
    assert cursor_store_root() == xdg / "cursor"
    assert cursor_chats_dir() == xdg / "cursor" / "chats"


def test_cursor_store_explicit(monkeypatch, tmp_path):
    root = tmp_path / "store"
    root.mkdir()
    monkeypatch.setenv("CURSOR_STORE_ROOT", str(root))
    assert cursor_store_root() == root


def test_cursor_workspace_hash_stable():
    a = cursor_workspace_hash("/tmp/example-project")
    b = cursor_workspace_hash("/tmp/example-project")
    assert a == b
    assert len(a) == 32


def test_catalog_rejects_desktop_harness():
    with pytest.raises(ValueError):
        models_from_dicts(
            [{"id": "x", "provider_model": "y", "harness": "cursor_desktop"}]
        )


def test_get_model_lookup():
    models = models_from_dicts(None)
    assert get_model(models, "OPUS").harness == HARNESS_CLAUDE


def test_parse_txcript_resume_lines():
    stdout = (
        "\x1b[32mclaude_code\x1b[0m → codex /tmp/rollout.jsonl\n"
        " resume with: codex resume 019aaaaa-bbbb-7ccc-dddd-eeeeeeeeeeee\n"
    )
    session_id, argv = parse_continue_output(stdout)
    assert session_id == "019aaaaa-bbbb-7ccc-dddd-eeeeeeeeeeee"
    assert argv[0] == "codex"
    claude_out = " resume with: claude --resume abc-123\n"
    sid, argv = parse_continue_output(claude_out)
    assert sid == "abc-123"
    agent_out = " resume with: agent --resume=deadbeef-0000-0000-0000-000000000001\n"
    sid, argv = parse_continue_output(agent_out)
    assert sid == "deadbeef-0000-0000-0000-000000000001"


def test_strip_ansi():
    assert strip_ansi("\x1b[31mred\x1b[0m") == "red"


def test_codex_id_from_filename():
    name = "rollout-2026-09-07T09-15-01-019aaaaa-bbbb-7ccc-dddd-eeeeeeeeeeee.jsonl"
    assert _codex_id_from_name(name) == "019aaaaa-bbbb-7ccc-dddd-eeeeeeeeeeee"


def test_list_claude_and_cursor_sessions(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    monkeypatch.setenv("CURSOR_STORE_ROOT", str(tmp_path / "cursor"))
    cwd = tmp_path / "proj"
    cwd.mkdir()
    project = claude_project_dir(cwd)
    nested = project / "sessions"
    nested.mkdir(parents=True)
    (project / "flat-id.jsonl").write_text("{}\n")
    (nested / "nested-id.jsonl").write_text("{}\n")
    ws = cursor_chats_dir() / cursor_workspace_hash(cwd) / "sess-1"
    ws.mkdir(parents=True)
    (ws / "store.db").write_bytes(b"sqlite")
    claude = list_sessions("claude_code", cwd)
    ids = {item.session_id for item in claude}
    assert "flat-id" in ids
    assert "nested-id" in ids
    cursor = list_sessions("cursor", cwd)
    assert cursor[0].session_id == "sess-1"


def test_codex_sessions_filter_by_cwd(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex"))
    sessions = tmp_path / "codex" / "sessions" / "2026" / "09" / "07"
    sessions.mkdir(parents=True)
    mine = tmp_path / "proj"
    other = tmp_path / "other"
    mine.mkdir()
    other.mkdir()
    mine_id = "019aaaaa-bbbb-7ccc-dddd-eeeeeeeeeeee"
    other_id = "019bbbbb-cccc-7ddd-eeee-ffffffffffff"
    (sessions / f"rollout-2026-09-07T10-00-00-{mine_id}.jsonl").write_text(
        json.dumps(
            {
                "type": "session_meta",
                "payload": {"cwd": str(mine.resolve()), "id": mine_id},
            }
        )
        + "\n"
    )
    (sessions / f"rollout-2026-09-07T11-00-00-{other_id}.jsonl").write_text(
        json.dumps(
            {
                "type": "session_meta",
                "payload": {"cwd": str(other.resolve()), "id": other_id},
            }
        )
        + "\n"
    )
    found = list_sessions("codex", mine)
    assert [item.session_id for item in found] == [mine_id]


def test_which_first_uses_path(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "claude"
    fake.write_text("#!/bin/sh\n")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir))
    assert which_first(("claude",)) == str(fake)


def test_discover_finds_fake_claude(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "claude"
    fake.write_text("#!/bin/sh\n")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir))
    recs = discover()
    assert recs["claude_code"].found
    assert recs["claude_code"].enabled


def test_empty_config_enables_found_clis(tmp_path, monkeypatch):
    from baton.clis import records_from_config

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "codex"
    fake.write_text("#!/bin/sh\n")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir))
    recs = records_from_config({})
    assert recs["codex"].found
    assert recs["codex"].enabled


def test_saved_disabled_flag_is_preserved(tmp_path, monkeypatch):
    from baton.clis import records_from_config

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "codex"
    fake.write_text("#!/bin/sh\n")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir))
    recs = records_from_config(
        {"clis": {"codex": {"enabled": False, "bin": str(fake)}}}
    )
    assert recs["codex"].found
    assert recs["codex"].enabled is False


def test_launch_argv(tmp_path):
    from baton.catalog import Model
    from baton.clis import CliRecord

    rec = CliRecord("claude_code", ("claude",), True, str(tmp_path / "claude"))
    (tmp_path / "claude").write_text("x")
    model = Model("opus", "claude-opus-4-1", "claude_code")
    argv = launch_argv(rec, model, "sid")
    assert argv == [str(tmp_path / "claude"), "--resume", "sid", "--model", "claude-opus-4-1"]

    rec = CliRecord("codex", ("codex",), True, str(tmp_path / "codex"))
    (tmp_path / "codex").write_text("x")
    model = Model("gpt", "gpt-5", "codex")
    argv = launch_argv(rec, model, "sid")
    assert argv[:3] == [str(tmp_path / "codex"), "--model", "gpt-5"]
    assert argv[3:] == ["resume", "sid"]

    rec = CliRecord("cursor", ("agent",), True, str(tmp_path / "agent"))
    (tmp_path / "agent").write_text("x")
    model = Model("composer", "composer-2.5", "cursor")
    argv = launch_argv(rec, model, "sid")
    assert "--resume=sid" in argv
    assert "--model" in argv


def test_cli_models_json(monkeypatch, tmp_path):
    monkeypatch.setenv("BATON_HOME", str(tmp_path / "hs"))
    from baton.cli import main

    assert main(["models", "--json"]) == 0
