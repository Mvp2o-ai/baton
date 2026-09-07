from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from homeswitch.txcript_parse import parse_continue_output


class TxcriptError(RuntimeError):
    pass


@dataclass
class ContinueResult:
    session_id: str
    resume_argv: list[str]
    stdout: str
    stderr: str


def find_txcript(configured: str = "txcript") -> str | None:
    if configured and Path(configured).expanduser().is_file():
        return str(Path(configured).expanduser())
    return shutil.which(configured) or shutil.which("txcript")


def continue_session(
    *,
    session_id: str,
    source_harness: str,
    target_harness: str,
    cwd: str | Path,
    txcript_bin: str = "txcript",
    extra_args: list[str] | None = None,
) -> ContinueResult:
    binary = find_txcript(txcript_bin)
    if not binary:
        raise TxcriptError(
            "txcript is not on PATH. Install with: "
            "cargo install --git https://github.com/skillsynchq/txcript txcript-cli"
        )
    if source_harness == target_harness:
        raise TxcriptError("same-harness model changes must not call txcript continue")

    cmd = [
        binary,
        "continue",
        session_id,
        "--from",
        source_harness,
        "--with",
        target_harness,
        "--no-resume",
    ]
    if extra_args:
        cmd.extend(extra_args)

    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        check=False,
        capture_output=True,
        text=True,
    )
    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    if proc.returncode != 0:
        raise TxcriptError(
            f"txcript continue failed ({proc.returncode}):\n{stdout}\n{stderr}".strip()
        )
    new_id, resume_argv = parse_continue_output(stdout, stderr)
    if not new_id:
        raise TxcriptError(
            "txcript continue succeeded but no session id was parsed from:\n"
            f"{stdout}\n{stderr}".strip()
        )
    return ContinueResult(
        session_id=new_id,
        resume_argv=resume_argv,
        stdout=stdout,
        stderr=stderr,
    )
