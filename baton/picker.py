"""Terminal picker: arrow keys / numbers, no typed model ids required."""

from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass

from baton.catalog import HARNESS_LABELS, Model, SUPPORTED_HARNESSES


REFRESH = object()


@dataclass
class PickResult:
    model: Model | None = None
    refresh: bool = False
    quit: bool = False


def format_catalog(models: list[Model], *, errors: list[str] | None = None) -> str:
    lines: list[str] = []
    grouped = _grouped(models)
    n = 1
    for harness in SUPPORTED_HARNESSES:
        rows = grouped.get(harness) or []
        if not rows:
            continue
        lines.append(HARNESS_LABELS.get(harness, harness))
        for model in rows:
            lines.append(f"  {n:>3}  {model.provider_model:<36} {model.display_label()}")
            n += 1
        lines.append("")
    if errors:
        lines.append("errors:")
        for err in errors:
            lines.append(f"  - {err}")
    if n == 1:
        lines.append("no models — enable a CLI with `baton clis`")
    return "\n".join(lines).rstrip()


def pick(
    models: list[Model],
    *,
    errors: list[str] | None = None,
    status_lines: list[str] | None = None,
) -> PickResult:
    rows = _flat(models)
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        return _pick_numbered(rows, errors=errors, status_lines=status_lines)
    return _pick_arrows(rows, errors=errors, status_lines=status_lines)


def _flat(models: list[Model]) -> list[Model]:
    grouped = _grouped(models)
    out: list[Model] = []
    for harness in SUPPORTED_HARNESSES:
        out.extend(grouped.get(harness) or [])
    return out


def _grouped(models: list[Model]) -> dict[str, list[Model]]:
    grouped: dict[str, list[Model]] = {h: [] for h in SUPPORTED_HARNESSES}
    for model in models:
        grouped.setdefault(model.harness, []).append(model)
    return grouped


def _pick_numbered(
    rows: list[Model],
    *,
    errors: list[str] | None,
    status_lines: list[str] | None,
) -> PickResult:
    if status_lines:
        print("\n".join(status_lines))
        print()
    print(format_catalog(rows, errors=errors))
    print()
    print("number to select, r refresh, q quit")
    try:
        line = input("> ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return PickResult(quit=True)
    if not line or line in {"q", "quit", "exit"}:
        return PickResult(quit=True)
    if line in {"r", "refresh"}:
        return PickResult(refresh=True)
    if line.isdigit():
        idx = int(line) - 1
        if 0 <= idx < len(rows):
            return PickResult(model=rows[idx])
    print("not a selection", file=sys.stderr)
    return PickResult()


def _pick_arrows(
    rows: list[Model],
    *,
    errors: list[str] | None,
    status_lines: list[str] | None,
) -> PickResult:
    import termios
    import tty

    index = 0
    scroll = 0
    query = ""
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        while True:
            visible = _filter(rows, query)
            height = max(8, shutil.get_terminal_size((80, 24)).lines - 10)
            if index >= len(visible):
                index = max(0, len(visible) - 1)
            if index < scroll:
                scroll = index
            if index >= scroll + height:
                scroll = index - height + 1
            _draw(visible, index, scroll, height, query, errors, status_lines)
            key = _read_key()
            if key in {"q", "\x03"} and not query:
                return PickResult(quit=True)
            if key == "r" and not query:
                return PickResult(refresh=True)
            if key in {"\r", "\n"}:
                if visible:
                    return PickResult(model=visible[index])
            if key == "up":
                index = max(0, index - 1)
            elif key == "down":
                index = min(max(0, len(visible) - 1), index + 1)
            elif key == "backspace":
                query = query[:-1]
                index = 0
            elif key == "esc":
                if query:
                    query = ""
                    index = 0
                else:
                    return PickResult(quit=True)
            elif len(key) == 1 and key.isprintable() and key not in {"\r", "\n"}:
                query += key
                index = 0
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        sys.stdout.write("\x1b[0m\n")
        sys.stdout.flush()


def _filter(rows: list[Model], query: str) -> list[Model]:
    q = query.strip().lower()
    if not q:
        return rows
    return [
        m
        for m in rows
        if q in m.provider_model.lower()
        or q in m.display_label().lower()
        or q in m.harness.lower()
    ]


def _draw(
    rows: list[Model],
    index: int,
    scroll: int,
    height: int,
    query: str,
    errors: list[str] | None,
    status_lines: list[str] | None,
) -> None:
    sys.stdout.write("\x1b[H\x1b[2J")
    lines: list[str] = ["baton set — ↑↓ enter to switch  type to filter  r refresh  q quit", ""]
    if status_lines:
        lines.extend(status_lines)
        lines.append("")
    if query:
        lines.append(f"filter: {query}")
        lines.append("")
    last_harness = None
    window = rows[scroll : scroll + height]
    for offset, model in enumerate(window):
        abs_i = scroll + offset
        if model.harness != last_harness:
            last_harness = model.harness
            lines.append(HARNESS_LABELS.get(model.harness, model.harness))
        mark = ">" if abs_i == index else " "
        lines.append(f" {mark} {model.provider_model:<36} {model.display_label()}")
    if not rows:
        lines.append("  (no models match)")
    if errors:
        lines.append("")
        for err in errors:
            lines.append(f"  ! {err}")
    sys.stdout.write("\n".join(lines) + "\n")
    sys.stdout.flush()


def _read_key() -> str:
    ch = sys.stdin.read(1)
    if ch == "\x1b":
        nxt = sys.stdin.read(1)
        if nxt == "[":
            arrow = sys.stdin.read(1)
            return {"A": "up", "B": "down"}.get(arrow, "esc")
        return "esc"
    if ch in {"\x7f", "\b"}:
        return "backspace"
    return ch
