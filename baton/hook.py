"""Detect `/baton` slash invocations from Claude, Codex, and Cursor hooks."""

from __future__ import annotations

import json
import os
import re
import sys

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


def poke_pick() -> str | None:
    """Ask the attached supervisor to open the picker. None on success."""
    try:
        request_pick()
        return None
    except Exception as exc:  # noqa: BLE001
        return str(exc)


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
    err = poke_pick()
    if err:
        return reply_json(
            vendor,
            blocked=True,
            reason=f"baton: {err}",
        )
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
