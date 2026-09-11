from __future__ import annotations

import re


_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_RESUME_LINE_RE = re.compile(r"resume with:\s*(.+)\s*$", re.IGNORECASE)


def strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def parse_continue_output(stdout: str, stderr: str = "") -> tuple[str | None, list[str]]:
    """Return (session_id, resume_argv) from `txcript continue --no-resume` text.

    txcript prints a conversion line, then `resume with: <bin> <args…>`.
    """
    blob = strip_ansi(stdout + "\n" + stderr)
    resume_argv: list[str] = []
    session_id: str | None = None
    for line in blob.splitlines():
        match = _RESUME_LINE_RE.search(line.strip())
        if not match:
            continue
        resume_argv = _split_cmd(match.group(1).strip())
        session_id = _id_from_argv(resume_argv)
        break
    return session_id, resume_argv


def _split_cmd(cmd: str) -> list[str]:
    # txcript's printed command is space-joined argv, not a shell string.
    return [part for part in cmd.split() if part]


def session_id_from_argv(argv: list[str]) -> str | None:
    """Read a native resume id from Claude/Codex/Cursor-style argv."""
    return _id_from_argv(argv)


def _id_from_argv(argv: list[str]) -> str | None:
    if not argv:
        return None
    for i, token in enumerate(argv):
        if token == "--resume" and i + 1 < len(argv):
            return argv[i + 1]
        if token == "resume" and i + 1 < len(argv):
            return argv[i + 1]
        if token.startswith("--resume="):
            return token.split("=", 1)[1]
        if token.startswith("--session=") or token.startswith("--conversation="):
            return token.split("=", 1)[1]
        if token in {"--session"} and i + 1 < len(argv):
            return argv[i + 1]
    return argv[-1] if len(argv) >= 2 else None
