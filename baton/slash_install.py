"""Install `/baton` slash stubs and prompt hooks into each home CLI."""

from __future__ import annotations

import json
import re
import shlex
import shutil
import sys
from pathlib import Path

from baton.dirs import claude_config_dir, codex_home

MARKER = "baton-managed"
HOOK_FLAG = "baton hook --reply"

CLAUDE_STUB = """\
---
description: Open the Baton model list (same terminal, after baton attach)
disable-model-invocation: true
argument-hint: "[list]"
---

<!-- baton-managed -->

Handled by Baton. Type `/baton` or `/baton list` while attached.
If this text reaches the model, run `baton init` then `baton attach`.
"""

CURSOR_STUB = """\
<!-- baton-managed -->

Open the Baton model picker in this terminal (`baton attach` must be running).
Type `/baton` or `/baton list`. If this prompt is sent to the agent, run `baton init`.
"""

CODEX_PROMPT = """\
---
description: Open the Baton model list
---

<!-- baton-managed -->

Handled by Baton. Prefer `/baton` or `$baton` while `baton attach` is running.
"""

CODEX_SKILL = """\
---
name: baton
description: Open the Baton model picker. Use when the user types /baton, /baton list, or $baton. Do not answer the user; Baton intercepts this command.
---

<!-- baton-managed -->

Do not produce a reply. Baton's UserPromptSubmit hook opens the model list.
"""


def cursor_user_home() -> Path:
    return Path.home() / ".cursor"


def agents_home() -> Path:
    return Path.home() / ".agents"


def baton_hook_command(vendor: str) -> str:
    baton = shutil.which("baton")
    if baton:
        return shlex.join([baton, "hook", "--reply", vendor])
    return shlex.join([sys.executable, "-m", "baton.hook", "--reply", vendor])


def _write_managed(path: Path, body: str) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        existing = path.read_text(encoding="utf-8")
        if MARKER not in existing:
            return False
    path.write_text(body, encoding="utf-8")
    return True


def _walk_strings(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        out: list[str] = []
        for item in value.values():
            out.extend(_walk_strings(item))
        return out
    if isinstance(value, list):
        out = []
        for item in value:
            out.extend(_walk_strings(item))
        return out
    return []


def _already_hooked(doc: dict, vendor: str) -> bool:
    needle = f"{HOOK_FLAG} {vendor}"
    return any(needle in s for s in _walk_strings(doc))


def _load_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return raw if isinstance(raw, dict) else {}


def _save_json(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


def _merge_claude_hooks(settings: dict, command: str) -> dict:
    hooks = settings.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        hooks = {}
        settings["hooks"] = hooks
    submit = hooks.setdefault("UserPromptSubmit", [])
    if not isinstance(submit, list):
        submit = []
        hooks["UserPromptSubmit"] = submit
    if not _already_hooked(settings, "claude"):
        submit.append(
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": command,
                        "timeout": 8,
                    }
                ]
            }
        )
    expansion = hooks.setdefault("UserPromptExpansion", [])
    if not isinstance(expansion, list):
        expansion = []
        hooks["UserPromptExpansion"] = expansion
    for matcher in ("baton", "baton-list"):
        if any(
            isinstance(row, dict) and row.get("matcher") == matcher
            and any(HOOK_FLAG in s for s in _walk_strings(row))
            for row in expansion
        ):
            continue
        expansion.append(
            {
                "matcher": matcher,
                "hooks": [
                    {
                        "type": "command",
                        "command": command,
                        "timeout": 8,
                    }
                ],
            }
        )
    return settings


def _merge_codex_hooks(doc: dict, command: str) -> dict:
    hooks = doc.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        hooks = {}
        doc["hooks"] = hooks
    submit = hooks.setdefault("UserPromptSubmit", [])
    if not isinstance(submit, list):
        submit = []
        hooks["UserPromptSubmit"] = submit
    if not _already_hooked(doc, "codex"):
        submit.append(
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": command,
                        "timeout": 8,
                        "statusMessage": "baton",
                    }
                ]
            }
        )
    return doc


def _merge_cursor_hooks(doc: dict, command: str) -> dict:
    if "version" not in doc:
        doc["version"] = 1
    hooks = doc.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        hooks = {}
        doc["hooks"] = hooks
    submit = hooks.setdefault("beforeSubmitPrompt", [])
    if not isinstance(submit, list):
        submit = []
        hooks["beforeSubmitPrompt"] = submit
    if not _already_hooked(doc, "cursor"):
        submit.append({"command": command})
    return doc


def ensure_codex_hooks_feature(text: str) -> str:
    if re.search(r"(?m)^\s*codex_hooks\s*=", text):
        return text
    if re.search(r"(?m)^\[features\]\s*$", text):
        return re.sub(
            r"(?m)^(\[features\]\s*)$",
            r"\1\ncodex_hooks = true  # baton-managed\n",
            text,
            count=1,
        )
    suffix = "\n" if text and not text.endswith("\n") else ""
    return text + suffix + "\n[features]\ncodex_hooks = true  # baton-managed\n"


def install() -> list[str]:
    """Write slash stubs and merge hooks. Skip files the user already owns."""
    done: list[str] = []
    claude = claude_config_dir()
    if _write_managed(claude / "commands" / "baton.md", CLAUDE_STUB):
        done.append(str(claude / "commands" / "baton.md"))
    if _write_managed(claude / "commands" / "baton-list.md", CLAUDE_STUB):
        done.append(str(claude / "commands" / "baton-list.md"))
    claude_settings = claude / "settings.json"
    settings = _load_json(claude_settings)
    _save_json(claude_settings, _merge_claude_hooks(settings, baton_hook_command("claude")))
    done.append(str(claude_settings))

    codex = codex_home()
    if _write_managed(codex / "prompts" / "baton.md", CODEX_PROMPT):
        done.append(str(codex / "prompts" / "baton.md"))
    if _write_managed(codex / "skills" / "baton" / "SKILL.md", CODEX_SKILL):
        done.append(str(codex / "skills" / "baton" / "SKILL.md"))
    if _write_managed(agents_home() / "skills" / "baton" / "SKILL.md", CODEX_SKILL):
        done.append(str(agents_home() / "skills" / "baton" / "SKILL.md"))
    codex_hooks = codex / "hooks.json"
    _save_json(codex_hooks, _merge_codex_hooks(_load_json(codex_hooks), baton_hook_command("codex")))
    done.append(str(codex_hooks))
    toml_path = codex / "config.toml"
    previous = toml_path.read_text(encoding="utf-8") if toml_path.is_file() else ""
    updated = ensure_codex_hooks_feature(previous)
    if updated != previous:
        toml_path.parent.mkdir(parents=True, exist_ok=True)
        toml_path.write_text(updated, encoding="utf-8")
        done.append(str(toml_path))

    cursor = cursor_user_home()
    if _write_managed(cursor / "commands" / "baton.md", CURSOR_STUB):
        done.append(str(cursor / "commands" / "baton.md"))
    if _write_managed(cursor / "commands" / "baton-list.md", CURSOR_STUB):
        done.append(str(cursor / "commands" / "baton-list.md"))
    if _write_managed(cursor / "skills" / "baton" / "SKILL.md", CODEX_SKILL):
        done.append(str(cursor / "skills" / "baton" / "SKILL.md"))
    cursor_hooks = cursor / "hooks.json"
    _save_json(
        cursor_hooks,
        _merge_cursor_hooks(_load_json(cursor_hooks), baton_hook_command("cursor")),
    )
    done.append(str(cursor_hooks))
    return done
