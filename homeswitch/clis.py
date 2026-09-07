from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from homeswitch.catalog import HARNESS_CLAUDE, HARNESS_CODEX, HARNESS_CURSOR, SUPPORTED_HARNESSES


# Official CLI binaries. Extra names are aliases we accept on PATH.
# Detection uses PATH lookup only — we never execute vendor CLIs to probe them.
CLI_SPECS: dict[str, tuple[str, ...]] = {
    HARNESS_CLAUDE: ("claude",),
    HARNESS_CODEX: ("codex",),
    HARNESS_CURSOR: ("agent", "cursor-agent"),
}


@dataclass
class CliRecord:
    harness: str
    names: tuple[str, ...]
    enabled: bool = False
    bin: str | None = None

    @property
    def found(self) -> bool:
        return bool(self.bin and Path(self.bin).is_file())


def which_first(names: tuple[str, ...], *, extra_path: str | None = None) -> str | None:
    search_path = extra_path if extra_path is not None else os.environ.get("PATH", "")
    for name in names:
        hit = shutil.which(name, path=search_path)
        if hit:
            return hit
    # Common install location Cursor documents; included even if not on PATH.
    home_local = Path.home() / ".local" / "bin"
    for name in names:
        candidate = home_local / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def discover(records: dict[str, CliRecord] | None = None) -> dict[str, CliRecord]:
    """Refresh binary paths. Enabled flags from `records` are preserved."""
    previous = records or {}
    out: dict[str, CliRecord] = {}
    for harness, names in CLI_SPECS.items():
        prev = previous.get(harness)
        found = None
        if prev and prev.bin and Path(prev.bin).is_file():
            found = prev.bin
        else:
            found = which_first(names)
        enabled = bool(prev.enabled) if prev else bool(found)
        out[harness] = CliRecord(
            harness=harness,
            names=names,
            enabled=enabled if found else False,
            bin=found,
        )
    return out


def records_from_config(raw: dict) -> dict[str, CliRecord]:
    clis = raw.get("clis") or {}
    base = {
        harness: CliRecord(harness=harness, names=CLI_SPECS[harness])
        for harness in SUPPORTED_HARNESSES
    }
    for harness, row in clis.items():
        if harness not in base:
            continue
        rec = base[harness]
        rec.enabled = bool(row.get("enabled"))
        bin_path = row.get("bin")
        rec.bin = str(bin_path) if bin_path else None
    return discover(base)


def records_to_config(records: dict[str, CliRecord]) -> dict:
    return {
        harness: {"enabled": rec.enabled, "bin": rec.bin}
        for harness, rec in records.items()
    }


def require_enabled(records: dict[str, CliRecord], harness: str) -> CliRecord:
    rec = records.get(harness)
    if rec is None:
        raise KeyError(f"unknown harness {harness!r}")
    if not rec.enabled:
        raise RuntimeError(
            f"{harness} is not enabled. Run `homeswitch clis` and enable it."
        )
    if not rec.found:
        names = " / ".join(rec.names)
        raise RuntimeError(
            f"{harness} is enabled but {names} was not found on PATH. "
            f"Install it, or `homeswitch clis set {harness} --bin /path/to/binary`."
        )
    return rec


def set_enabled(records: dict[str, CliRecord], harness: str, enabled: bool) -> CliRecord:
    if harness not in records:
        raise KeyError(f"unknown harness {harness!r}. known: {', '.join(SUPPORTED_HARNESSES)}")
    rec = records[harness]
    if enabled and not rec.found:
        rec.bin = which_first(rec.names)
    if enabled and not rec.found:
        names = " / ".join(rec.names)
        raise RuntimeError(f"cannot enable {harness}: {names} not found on PATH")
    rec.enabled = bool(enabled) and rec.found
    return rec


def set_bin(records: dict[str, CliRecord], harness: str, bin_path: str) -> CliRecord:
    if harness not in records:
        raise KeyError(f"unknown harness {harness!r}")
    path = Path(bin_path).expanduser()
    if not path.is_file():
        raise RuntimeError(f"not a file: {path}")
    rec = records[harness]
    rec.bin = str(path.resolve())
    rec.enabled = True
    return rec
