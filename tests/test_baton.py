from __future__ import annotations

import json
from pathlib import Path

import pytest

from baton.catalog import CLAUDE_BUILT_IN, HARNESS_CLAUDE, resolve, models_from_dicts
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
from baton.txcript_pin import TXCRIPT_GIT, TXCRIPT_REV, install_cmd


def test_txcript_pin_matches_readme_and_ci():
    root = Path(__file__).resolve().parents[1]
    readme = (root / "README.md").read_text(encoding="utf-8")
    ci = (root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert TXCRIPT_REV in readme
    assert TXCRIPT_REV in ci
    assert TXCRIPT_GIT in readme
    assert TXCRIPT_GIT in ci
    assert TXCRIPT_REV in install_cmd()


def test_package_versions_match():
    import re
    import tomllib

    root = Path(__file__).resolve().parents[1]
    npm = json.loads((root / "package.json").read_text(encoding="utf-8"))["version"]
    py = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "version"
    ]
    init = (root / "baton" / "__init__.py").read_text(encoding="utf-8")
    found = re.search(r'^__version__ = "([^"]+)"$', init, re.M)
    assert found, "baton/__init__.py must set __version__"
    assert npm == py == found.group(1)


def test_npm_publish_only_on_semver_release_tags():
    root = Path(__file__).resolve().parents[1]
    yml = (root / ".github/workflows/npm-publish.yml").read_text(encoding="utf-8")
    assert "Mvp2o-ai/baton" in yml
    assert r"^v[0-9]+\.[0-9]+\.[0-9]+$" in yml
    assert "needs.guard.outputs.should_publish" in yml


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
    models = list(CLAUDE_BUILT_IN)
    assert resolve(models, "OPUS").harness == HARNESS_CLAUDE
    assert resolve(models, "claude_code:sonnet").provider_model == "sonnet"


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


def test_init_exits_without_prompt(monkeypatch, tmp_path):
    monkeypatch.setenv("BATON_HOME", str(tmp_path / "hs"))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex"))
    monkeypatch.setattr("baton.slash_install.cursor_user_home", lambda: tmp_path / "cursor")
    monkeypatch.setattr("baton.slash_install.agents_home", lambda: tmp_path / "agents")
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)

    def boom(*_a, **_k):
        raise AssertionError("init must not open the clis prompt")

    monkeypatch.setattr("baton.cli._interactive_clis", boom)
    from baton.cli import main

    assert main(["init", "--no-attach"]) == 0
    assert (tmp_path / "claude" / "commands" / "baton.md").is_file()
    assert (tmp_path / "codex" / "hooks.json").is_file()
    assert (tmp_path / "cursor" / "commands" / "baton.md").is_file()


def test_set_aliases_parse():
    from baton.cli import build_parser, cmd_attach, cmd_set
    from baton.catalog import HARNESS_CLAUDE, HARNESS_CODEX, HARNESS_CURSOR

    parser = build_parser()
    for name in ("set", "list", "select", "sidecar"):
        args = parser.parse_args([name])
        assert args.func is cmd_set
    bare = parser.parse_args([])
    assert bare.func is cmd_attach
    assert bare.harness is None
    homes = {
        "claude": HARNESS_CLAUDE,
        "claude_code": HARNESS_CLAUDE,
        "codex": HARNESS_CODEX,
        "agent": HARNESS_CURSOR,
        "cursor": HARNESS_CURSOR,
        "agentx": HARNESS_CURSOR,
    }
    for name, harness in homes.items():
        args = parser.parse_args([name])
        assert args.func is cmd_attach
        assert args.harness == harness


def test_cli_models_json(monkeypatch, tmp_path):
    monkeypatch.setenv("BATON_HOME", str(tmp_path / "hs"))
    monkeypatch.setattr("baton.cli.collect_catalog", lambda clis: ([], []))
    from baton.cli import main

    assert main(["models", "--json"]) == 0


def test_parse_agent_models():
    from baton.provider_models import parse_agent_models

    text = (
        "Available models\n\n"
        "auto - Auto (default)\n"
        "composer-2.5 - Composer 2.5\n"
        "composer-2.5-fast - Composer 2.5 Fast\n"
    )
    rows = parse_agent_models(text)
    assert [m.provider_model for m in rows] == ["auto", "composer-2.5", "composer-2.5-fast"]
    assert rows[1].harness == "cursor"
    assert rows[1].label == "Composer 2.5"


def test_cursor_home_models_keeps_composer_and_grok():
    from baton.catalog import make_model
    from baton.provider_models import cursor_home_models, is_cursor_home_model

    rows = [
        make_model("cursor", "auto", "Auto"),
        make_model("cursor", "composer-2.5", "Composer 2.5"),
        make_model("cursor", "composer-2.5-fast", "Composer 2.5 Fast"),
        make_model("cursor", "grok-4.6", "Grok 4.6"),
        make_model("cursor", "grok-4.6-high", "Grok 4.6 High"),
        make_model("cursor", "gpt-5.4", "GPT-5.4"),
        make_model("cursor", "claude-opus-4.1", "Opus"),
    ]
    kept = [m.provider_model for m in cursor_home_models(rows)]
    assert kept == ["composer-2.5", "composer-2.5-fast", "grok-4.6", "grok-4.6-high"]
    assert is_cursor_home_model("composer-2")
    assert is_cursor_home_model("grok-4")
    assert not is_cursor_home_model("auto")
    assert not is_cursor_home_model("gpt-5")


def test_parse_codex_catalog_keeps_hide_skips_none():
    from baton.provider_models import parse_codex_catalog

    rows = parse_codex_catalog(
        {
            "models": [
                {"slug": "gpt-5.6-sol", "display_name": "GPT-5.6-Sol", "visibility": "list", "priority": 6},
                {"slug": "gpt-5.4", "display_name": "GPT-5.4", "visibility": "hide", "priority": 16},
                {"slug": "internal", "display_name": "Internal", "visibility": "none", "priority": 1},
            ]
        }
    )
    assert [m.provider_model for m in rows] == ["gpt-5.6-sol", "gpt-5.4"]
    assert rows[0].harness == "codex"


def test_merge_codex_catalogs_keeps_bundled_when_live_is_thin():
    from baton.provider_models import merge_codex_catalogs

    bundled = {
        "models": [
            {"slug": "gpt-6-astra", "display_name": "GPT-6-Astra", "visibility": "list", "priority": 1},
            {"slug": "gpt-5.6-sol", "display_name": "GPT-5.6-Sol", "visibility": "list", "priority": 6},
            {"slug": "gpt-5.2", "display_name": "GPT-5.2", "visibility": "list", "priority": 29},
        ]
    }
    live = {
        "models": [
            {"slug": "gpt-5.6-luna", "display_name": "GPT-5.6-Luna", "visibility": "list", "priority": 8},
            {"slug": "gpt-5.6-sol", "display_name": "Sol (account)", "visibility": "list", "priority": 6},
        ]
    }
    rows = merge_codex_catalogs([bundled, live])
    slugs = [m.provider_model for m in rows]
    assert slugs == ["gpt-6-astra", "gpt-5.6-sol", "gpt-5.6-luna", "gpt-5.2"]
    assert rows[1].label == "Sol (account)"


def test_claude_allowlist(monkeypatch, tmp_path):
    from baton.provider_models import fetch_claude

    settings = tmp_path / "settings.json"
    settings.write_text('{"availableModels": ["sonnet", "haiku"]}\n')
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    rows = fetch_claude()
    ids = {m.provider_model for m in rows}
    assert "sonnet" in ids
    assert "haiku" in ids
    assert "opus" not in ids


def test_hook_pick_failure_is_instructional(monkeypatch):
    from baton.hook import handle_payload

    def boom():
        raise RuntimeError("Nothing is attached.\nrun baton attach")

    monkeypatch.setattr("baton.hook.request_pick", boom)
    out = handle_payload({"prompt": "/baton"}, vendor="cursor")
    assert out["continue"] is False
    assert "/baton could not open the model picker." in out["user_message"]
    assert "Nothing is attached." in out["user_message"]
    assert "run baton attach" in out["user_message"]


def test_baton_slash_prompt_match():
    from baton.hook import is_baton_invocation, prompt_is_baton, reply_json

    assert prompt_is_baton("/baton list")
    assert prompt_is_baton("/baton")
    assert prompt_is_baton("$baton")
    assert prompt_is_baton("/prompts:baton")
    assert not prompt_is_baton("please baton list the files")
    assert not prompt_is_baton("list")
    assert is_baton_invocation({"command_name": "baton-list", "prompt": "hello"})
    assert reply_json("cursor", blocked=True, reason="x") == {
        "continue": False,
        "user_message": "x",
    }
    assert reply_json("codex", blocked=True, reason="x")["decision"] == "block"


def test_slash_install_skips_user_owned_files(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex"))
    monkeypatch.setattr("baton.slash_install.cursor_user_home", lambda: tmp_path / "cursor")
    monkeypatch.setattr("baton.slash_install.agents_home", lambda: tmp_path / "agents")
    owned = tmp_path / "claude" / "commands" / "baton.md"
    owned.parent.mkdir(parents=True)
    owned.write_text("# my command\n")
    from baton.slash_install import ensure_codex_hooks_feature, install

    install()
    assert owned.read_text() == "# my command\n"
    install()
    import json

    settings = json.loads((tmp_path / "claude" / "settings.json").read_text())
    assert len(settings["hooks"]["UserPromptSubmit"]) == 1
    assert len(settings["hooks"]["UserPromptExpansion"]) == 2
    text = ensure_codex_hooks_feature("[other]\nx = 1\n")
    assert "codex_hooks = true" in text
    again = ensure_codex_hooks_feature(text)
    assert again.count("codex_hooks") == 1


def test_line_tracker_picks_baton_enter():
    from baton.ptyctl import LineTracker

    t = LineTracker()
    forwarded, pick = t.feed(b"/baton\r")
    assert forwarded == b"/baton"
    assert pick is True

    t = LineTracker()
    forwarded, pick = t.feed(b"hello\r")
    assert forwarded == b"hello\r"
    assert pick is False

    t = LineTracker()
    t.feed(b"/bat")
    forwarded, pick = t.feed(b"on\n")
    assert forwarded == b"on"
    assert pick is True

    t = LineTracker()
    forwarded, pick = t.feed(b"$baton\r")
    assert pick is True
    assert forwarded == b"$baton"


def test_style_respects_no_color(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    monkeypatch.delenv("CLICOLOR_FORCE", raising=False)
    from baton.style import LOGO_PLAIN, gold, logo, wordmark

    assert logo() == "\n".join(LOGO_PLAIN)
    assert "BATON" in logo()
    assert gold("BATON") == "BATON"
    assert wordmark() == "●════● BATON"
    assert "\x1b" not in logo()
    assert "\x1b" not in wordmark()


def test_style_force_color(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("FORCE_COLOR", "1")
    from baton.style import GOLD, gold, logo, magenta, wordmark

    colored = logo()
    assert "BATON" in colored
    assert "\x1b[38;5;171m" in colored
    assert "\x1b[38;5;220m" in colored
    assert gold("x") == f"\x1b[1m\x1b[38;5;{GOLD}mx\x1b[0m"
    assert magenta("baton").startswith("\x1b")
    assert "BATON" in wordmark()
    assert "\x1b" in wordmark()


def _pane(pane_id: str, cwd: Path):
    from baton.bus import PaneState

    return PaneState(
        pane_id=pane_id,
        thread_id=f"thread-{pane_id}",
        cwd=str(cwd),
        model_id="codex:gpt-5",
        harness="codex",
        session_id=None,
        idle=False,
        pid=1,
    )


def test_default_pane_id_prefers_cwd_when_several_are_live(monkeypatch, tmp_path):
    here = tmp_path / "here"
    other = tmp_path / "other"
    here.mkdir()
    other.mkdir()
    panes = [_pane("aaaa1111", other), _pane("bbbb2222", here)]
    monkeypatch.setattr("baton.sidecar.list_panes", lambda: panes)
    from baton.sidecar import default_pane_id

    assert default_pane_id(here) == "bbbb2222"


def test_default_pane_id_errors_when_cwd_is_not_attached(monkeypatch, tmp_path):
    live = tmp_path / "live"
    other = tmp_path / "other"
    live.mkdir()
    other.mkdir()
    panes = [_pane("aaaa1111", live), _pane("cccc3333", other)]
    monkeypatch.setattr("baton.sidecar.list_panes", lambda: panes)
    from baton.sidecar import default_pane_id

    with pytest.raises(RuntimeError, match="This directory is not attached"):
        default_pane_id(tmp_path)


def test_format_catalog_plain_without_tty(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    from baton.catalog import CLAUDE_BUILT_IN
    from baton.picker import format_catalog

    text = format_catalog(list(CLAUDE_BUILT_IN)[:2])
    assert "Claude Code" in text
    assert "opus" in text
    assert "\x1b" not in text


def _proto_varint(value: int) -> bytes:
    out = bytearray()
    while value >= 0x80:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    out.append(value)
    return bytes(out)


def _cursor_root_without_tz(started_ms: int = 1_788_873_499_237) -> bytes:
    # field 8 (turns) + field 10 (mode) + field 26 (started ms) — txcript shape
    turn = b"\x00" * 32
    body = bytearray()
    body.extend(_proto_varint((8 << 3) | 2))
    body.extend(_proto_varint(len(turn)))
    body.extend(turn)
    body.extend(_proto_varint((10 << 3) | 0))
    body.extend(_proto_varint(1))
    body.extend(_proto_varint((26 << 3) | 0))
    body.extend(_proto_varint(started_ms))
    return bytes(body)


def test_iana_timezone_prefers_tz_env(monkeypatch):
    monkeypatch.setenv("TZ", "America/Chicago")
    from baton.cursor_resume import iana_timezone

    assert iana_timezone() == "America/Chicago"


def test_iana_timezone_from_macos_tzdata_path():
    from baton.cursor_resume import iana_timezone_from_path

    assert (
        iana_timezone_from_path(
            "/private/var/db/timezone/tz/2026c.1.0/zoneinfo/America/New_York"
        )
        == "America/New_York"
    )
    assert iana_timezone_from_path("/usr/share/zoneinfo/Europe/Paris") == "Europe/Paris"
    assert iana_timezone_from_path("/etc/localtime") == "UTC"


def test_seal_imported_cursor_session_appends_timezone(monkeypatch, tmp_path):
    import hashlib
    import json
    import sqlite3

    from baton.cursor_resume import _top_level_fields, seal_imported_cursor_session
    from baton.dirs import cursor_workspace_hash

    cwd = tmp_path / "proj"
    cwd.mkdir()
    monkeypatch.setenv("CURSOR_STORE_ROOT", str(tmp_path / "cursor"))
    monkeypatch.setenv("TZ", "America/New_York")
    sid = "3ae1c3d5-25e6-41a4-ae27-bcf41d9a61f3"
    session_dir = tmp_path / "cursor" / "chats" / cursor_workspace_hash(cwd) / sid
    session_dir.mkdir(parents=True)
    root = _cursor_root_without_tz()
    root_id = hashlib.sha256(root).hexdigest()
    meta = {
        "agentId": sid,
        "latestRootBlobId": root_id,
        "name": "Imported Session",
        "createdAt": 1788873499237,
    }
    db = session_dir / "store.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE blobs (id TEXT PRIMARY KEY, data BLOB)")
    conn.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
    conn.execute("INSERT INTO blobs (id, data) VALUES (?, ?)", (root_id, root))
    conn.execute(
        "INSERT INTO meta (key, value) VALUES ('0', ?)",
        (json.dumps(meta, separators=(",", ":")).encode().hex(),),
    )
    conn.commit()
    conn.close()

    assert seal_imported_cursor_session(sid, cwd) is True
    conn = sqlite3.connect(str(db))
    value = conn.execute("SELECT value FROM meta WHERE key = '0'").fetchone()[0]
    updated = json.loads(bytes.fromhex(value).decode())
    new_id = updated["latestRootBlobId"]
    assert new_id != root_id
    patched = conn.execute("SELECT data FROM blobs WHERE id = ?", (new_id,)).fetchone()[0]
    conn.close()
    fields = _top_level_fields(patched)
    assert 26 in fields and 27 in fields
    assert patched.endswith(b"America/New_York")


def test_seal_imported_cursor_session_skips_when_timezone_present(monkeypatch, tmp_path):
    import hashlib
    import json
    import sqlite3

    from baton.cursor_resume import _len_field, seal_imported_cursor_session
    from baton.dirs import cursor_workspace_hash

    cwd = tmp_path / "proj"
    cwd.mkdir()
    monkeypatch.setenv("CURSOR_STORE_ROOT", str(tmp_path / "cursor"))
    sid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    session_dir = tmp_path / "cursor" / "chats" / cursor_workspace_hash(cwd) / sid
    session_dir.mkdir(parents=True)
    root = _cursor_root_without_tz() + _len_field(27, b"America/New_York")
    root_id = hashlib.sha256(root).hexdigest()
    db = session_dir / "store.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE blobs (id TEXT PRIMARY KEY, data BLOB)")
    conn.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
    conn.execute("INSERT INTO blobs (id, data) VALUES (?, ?)", (root_id, root))
    conn.execute(
        "INSERT INTO meta (key, value) VALUES ('0', ?)",
        (json.dumps({"latestRootBlobId": root_id}).encode().hex(),),
    )
    conn.commit()
    conn.close()
    assert seal_imported_cursor_session(sid, cwd) is False


def _skill_homes(monkeypatch, tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(home / ".claude"))
    monkeypatch.setenv("CODEX_HOME", str(home / ".codex"))
    return home


def _write_skill(root, name, body="# skill\n"):
    folder = root / name
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text(body, encoding="utf-8")
    return folder


def test_cursor_skill_needs_claude_and_codex_links(monkeypatch, tmp_path):
    from baton.dirs import agents_user_skills_dir, claude_user_skills_dir, cursor_user_skills_dir
    from baton.skill_bridge import missing_links

    _skill_homes(monkeypatch, tmp_path)
    source = _write_skill(cursor_user_skills_dir(), "complete-releases")
    claude = missing_links("claude_code")
    assert [(x.name, x.source, x.dest) for x in claude] == [
        ("complete-releases", source.resolve(), claude_user_skills_dir() / "complete-releases")
    ]
    codex = missing_links("codex")
    assert [(x.name, x.source, x.dest) for x in codex] == [
        ("complete-releases", source.resolve(), agents_user_skills_dir() / "complete-releases")
    ]
    assert missing_links("cursor") == []


def test_claude_and_agents_skills_already_visible_to_cursor(monkeypatch, tmp_path):
    from baton.dirs import agents_user_skills_dir, claude_user_skills_dir
    from baton.skill_bridge import missing_links

    _skill_homes(monkeypatch, tmp_path)
    _write_skill(claude_user_skills_dir(), "catch-up-on-previous-thread")
    _write_skill(agents_user_skills_dir(), "agent-messages")
    assert missing_links("cursor") == []
    claude = missing_links("claude_code")
    assert [x.name for x in claude] == ["agent-messages"]
    assert claude[0].source == (agents_user_skills_dir() / "agent-messages").resolve()
    assert missing_links("codex")[0].name == "catch-up-on-previous-thread"


def test_deprecated_codex_skill_is_visible_to_cursor_not_claude(monkeypatch, tmp_path):
    from baton.dirs import claude_user_skills_dir, codex_deprecated_user_skills_dir
    from baton.skill_bridge import missing_links

    _skill_homes(monkeypatch, tmp_path)
    source = _write_skill(codex_deprecated_user_skills_dir(), "from-codex-home")
    assert missing_links("cursor") == []
    assert missing_links("codex") == []
    claude = missing_links("claude_code")
    assert len(claude) == 1
    assert claude[0].source == source.resolve()
    assert claude[0].dest == claude_user_skills_dir() / "from-codex-home"


def test_reserved_and_owned_names_are_not_proposed(monkeypatch, tmp_path):
    from baton.dirs import claude_user_skills_dir, cursor_user_skills_dir
    from baton.skill_bridge import missing_links

    _skill_homes(monkeypatch, tmp_path)
    _write_skill(cursor_user_skills_dir(), "baton")
    _write_skill(cursor_user_skills_dir(), "synced")
    _write_skill(cursor_user_skills_dir(), "mine")
    owned = claude_user_skills_dir() / "mine"
    owned.mkdir(parents=True)
    (owned / "notes.txt").write_text("not a skill\n", encoding="utf-8")
    assert missing_links("claude_code") == []


def test_existing_symlink_to_same_target_is_not_proposed(monkeypatch, tmp_path):
    from baton.dirs import cursor_user_skills_dir
    from baton.skill_bridge import apply_links, missing_links

    _skill_homes(monkeypatch, tmp_path)
    source = _write_skill(cursor_user_skills_dir(), "complete-releases")
    proposed = missing_links("claude_code")
    created = apply_links(proposed)
    assert created[0].dest.is_symlink()
    assert created[0].dest.resolve() == source.resolve()
    assert missing_links("claude_code") == []


def test_name_collision_is_not_bridged(monkeypatch, tmp_path):
    from baton.dirs import claude_user_skills_dir, cursor_user_skills_dir
    from baton.skill_bridge import collect_user_skills, missing_links

    _skill_homes(monkeypatch, tmp_path)
    _write_skill(cursor_user_skills_dir(), "dup")
    _write_skill(claude_user_skills_dir(), "dup")
    assert "dup" not in collect_user_skills()
    assert missing_links("codex") == []


def test_cursor_symlink_codex_link_points_at_canonical(monkeypatch, tmp_path):
    from baton.dirs import agents_user_skills_dir, claude_user_skills_dir, cursor_user_skills_dir
    from baton.skill_bridge import apply_links, missing_links

    _skill_homes(monkeypatch, tmp_path)
    canonical = _write_skill(claude_user_skills_dir(), "complete-releases")
    cursor_dir = cursor_user_skills_dir()
    cursor_dir.mkdir(parents=True)
    (cursor_dir / "complete-releases").symlink_to(canonical)
    proposed = missing_links("codex")
    assert len(proposed) == 1
    assert proposed[0].source == canonical.resolve()
    assert proposed[0].dest == agents_user_skills_dir() / "complete-releases"
    apply_links(proposed)
    assert (agents_user_skills_dir() / "complete-releases").resolve() == canonical.resolve()


def test_offer_skips_without_tty_and_links_on_yes(monkeypatch, tmp_path):
    from baton.dirs import claude_user_skills_dir, cursor_user_skills_dir
    from baton.skill_bridge import offer_user_skill_links

    _skill_homes(monkeypatch, tmp_path)
    _write_skill(cursor_user_skills_dir(), "complete-releases")
    dest = claude_user_skills_dir() / "complete-releases"
    assert offer_user_skill_links("claude_code", interactive=False) == []
    assert not dest.exists()
    monkeypatch.setattr("builtins.input", lambda: "")
    created = offer_user_skill_links("claude_code", interactive=True)
    assert len(created) == 1
    assert dest.is_symlink()
    monkeypatch.setattr("builtins.input", lambda: "n")
    _write_skill(cursor_user_skills_dir(), "another")
    assert offer_user_skill_links("claude_code", interactive=True) == []
    assert not (claude_user_skills_dir() / "another").exists()


def test_doctor_lists_skill_roots(monkeypatch, tmp_path):
    from baton.doctor import collect_doctor

    _skill_homes(monkeypatch, tmp_path)
    monkeypatch.setenv("BATON_HOME", str(tmp_path / "baton-home"))
    report = collect_doctor(cwd=tmp_path)
    paths = {row["path"] for row in report["skill_roots"]}
    home = tmp_path / "home"
    assert str(home / ".claude" / "skills") in paths
    assert str(home / ".cursor" / "skills") in paths
    assert str(home / ".agents" / "skills") in paths
    assert str(home / ".codex" / "skills") in paths

