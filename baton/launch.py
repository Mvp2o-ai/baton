from __future__ import annotations

from baton.catalog import HARNESS_CLAUDE, HARNESS_CODEX, HARNESS_CURSOR, Model
from baton.clis import CliRecord


def argv_has_resume(argv: list[str]) -> bool:
    for token in argv:
        if token in {"--resume", "resume"} or token.startswith("--resume="):
            return True
    return False


def launch_argv(
    record: CliRecord,
    model: Model,
    session_id: str | None,
    extra_args: list[str] | None = None,
) -> list[str]:
    """Interactive resume/start argv for a home CLI.

    Baton supplies the binary and ``--model``. Everything else the user typed
    after ``baton claude|codex|agent`` is the provider's and is appended as-is.
    """
    if not record.bin:
        raise RuntimeError(f"{record.harness} has no binary path")
    extra = list(extra_args or [])
    bin_path = record.bin
    provider = model.provider_model
    if record.harness == HARNESS_CLAUDE:
        cmd = [bin_path]
        if session_id and not argv_has_resume(extra):
            cmd.extend(["--resume", session_id])
        cmd.extend(["--model", provider])
        cmd.extend(extra)
        return cmd
    if record.harness == HARNESS_CODEX:
        cmd = [bin_path, "--model", provider]
        if session_id and not argv_has_resume(extra):
            cmd.extend(["resume", session_id])
        cmd.extend(extra)
        return cmd
    if record.harness == HARNESS_CURSOR:
        cmd = [bin_path, "--model", provider]
        if session_id and not argv_has_resume(extra):
            cmd.append(f"--resume={session_id}")
        cmd.extend(extra)
        return cmd
    raise RuntimeError(f"no launch template for {record.harness}")
