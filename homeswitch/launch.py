from __future__ import annotations

from homeswitch.catalog import HARNESS_CLAUDE, HARNESS_CODEX, HARNESS_CURSOR, Model
from homeswitch.clis import CliRecord


def launch_argv(record: CliRecord, model: Model, session_id: str | None) -> list[str]:
    """Interactive resume/start argv for a home CLI.

    Uses the registered binary path. Model flag is ours; txcript's printed
    resume command does not include --model.
    """
    if not record.bin:
        raise RuntimeError(f"{record.harness} has no binary path")
    bin_path = record.bin
    provider = model.provider_model
    if record.harness == HARNESS_CLAUDE:
        cmd = [bin_path]
        if session_id:
            cmd.extend(["--resume", session_id])
        cmd.extend(["--model", provider])
        return cmd
    if record.harness == HARNESS_CODEX:
        cmd = [bin_path, "--model", provider]
        if session_id:
            cmd.extend(["resume", session_id])
        return cmd
    if record.harness == HARNESS_CURSOR:
        cmd = [bin_path, "--model", provider]
        if session_id:
            cmd.append(f"--resume={session_id}")
        return cmd
    raise RuntimeError(f"no launch template for {record.harness}")
