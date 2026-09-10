"""Detect `/baton` slash invocations from Claude, Codex, and Cursor hooks."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

from baton.sidecar import request_pick

_PROMPT_RE = re.compile(
    r"""
    ^
    [/\$]+
    (?:prompts:|skills:)?
    baton
    (?:[\s_/-]+(?:list|set|select|models|pick))?
    $
    """,
    re.IGNORECASE | re.VERBOSE,
)

_COMMAND_NAMES = {"baton", "baton-list", "baton-set", "baton-select"}


def is_baton_invocation(payload: dict) -> bool:
    name = str(payload.get("command_name") or "").strip().lower()
    if name in _COMMAND_NAMES:
        return True
    prompt = str(
        payload.get("prompt")
        or os.environ.get("CLAUDE_PROMPT")
        or ""
    )
    return prompt_is_baton(prompt)


def prompt_is_baton(prompt: str) -> bool:
    text = " ".join(prompt.strip().split())
    if not text:
        return False
    return bool(_PROMPT_RE.match(text))


def payload_directories(payload: dict) -> list[Path]:
    """Project dirs from Claude/Codex ``cwd`` and Cursor ``workspace_roots``.

    Hook *process* cwd is not used here. Cursor IDE runs beforeSubmitPrompt
    with cwd ``~/.cursor``; Claude and Codex JSON include the session cwd.
    """
    found: list[Path] = []
    seen: set[Path] = set()

    def add(value: object) -> None:
        if not isinstance(value, str):
            return
        text = value.strip()
        if not text:
            return
        path = Path(text).expanduser()
        try:
            path = path.resolve()
        except OSError:
            return
        if path in seen:
            return
        seen.add(path)
        found.append(path)

    add(payload.get("cwd"))
    roots = payload.get("workspace_roots")
    if isinstance(roots, list):
        for item in roots:
            add(item)
    return found


def payload_transcript(payload: dict) -> str | None:
    raw = payload.get("transcript_path")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


def poke_pick(payload: dict | None = None) -> str | None:
    """Ask the attached supervisor to open the picker. None on success."""
    payload = payload or {}
    try:
        request_pick(
            cwd=payload_directories(payload) or None,
            transcript_path=payload_transcript(payload),
        )
        return None
    except Exception as exc:  # noqa: BLE001
        detail = str(exc).strip() or exc.__class__.__name__
        return f"/baton could not open the model picker.\n{detail}"


def reply_json(vendor: str, *, blocked: bool, reason: str) -> dict:
    if vendor == "cursor":
        if blocked:
            return {"continue": False, "user_message": reason}
        return {"continue": True}
    if vendor in {"claude", "codex"}:
        if blocked:
            return {"decision": "block", "reason": reason}
        return {}
    raise ValueError(f"unknown hook vendor {vendor}")


def handle_payload(payload: dict, *, vendor: str) -> dict:
    if not is_baton_invocation(payload):
        return reply_json(vendor, blocked=False, reason="")
    err = poke_pick(payload)
    if err:
        return reply_json(vendor, blocked=True, reason=err)
    return reply_json(
        vendor,
        blocked=True,
        reason="Opening the Baton model list in the attach pane.",
    )


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    vendor = "claude"
    if "--reply" in args:
        i = args.index("--reply")
        if i + 1 < len(args):
            vendor = args[i + 1]
    raw = sys.stdin.read()
    payload: dict = {}
    if raw.strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                payload = parsed
        except json.JSONDecodeError:
            payload = {"prompt": raw}
    out = handle_payload(payload, vendor=vendor)
    if out:
        sys.stdout.write(json.dumps(out) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
