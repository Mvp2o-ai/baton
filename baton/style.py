"""Terminal chrome so Baton is visually distinct from the home CLIs.

Claude leans orange, Codex green, Cursor blue. Baton is magenta + gold —
a relay stick — and that pairing is what marks a Baton command or overlay.
Respects NO_COLOR; FORCE_COLOR / CLICOLOR_FORCE turn color on even without a tty.
"""

from __future__ import annotations

import os
import sys
from typing import TextIO

# 256-color. Magenta chrome + gold wordmark.
GOLD = 220
BRASS = 178
MAGENTA = 171
CYAN = 81
DIM = 245
RED = 203
GREEN = 114
CREAM = 230
SEL_BG = 171
SEL_FG = 230

RESET = "\x1b[0m"
BOLD = "\x1b[1m"

LOGO_PLAIN = (
    "  ┌──●──┐",
    "  │BATON│",
    "  └──●──┘",
)


def color_enabled(stream: TextIO | None = None) -> bool:
    if os.environ.get("NO_COLOR", ""):
        return False
    if os.environ.get("FORCE_COLOR", "") or os.environ.get("CLICOLOR_FORCE", ""):
        return True
    target = stream if stream is not None else sys.stderr
    try:
        return bool(target.isatty())
    except Exception:
        return False


def fg(n: int) -> str:
    return f"\x1b[38;5;{n}m"


def bg(n: int) -> str:
    return f"\x1b[48;5;{n}m"


def paint(text: str, *parts: str, stream: TextIO | None = None) -> str:
    if not text or not color_enabled(stream):
        return text
    return "".join(parts) + text + RESET


def gold(text: str, *, stream: TextIO | None = None) -> str:
    return paint(text, BOLD, fg(GOLD), stream=stream)


def magenta(text: str, *, stream: TextIO | None = None) -> str:
    return paint(text, BOLD, fg(MAGENTA), stream=stream)


def brass(text: str, *, stream: TextIO | None = None) -> str:
    return paint(text, fg(BRASS), stream=stream)


def cyan(text: str, *, stream: TextIO | None = None) -> str:
    return paint(text, BOLD, fg(CYAN), stream=stream)


def dim(text: str, *, stream: TextIO | None = None) -> str:
    return paint(text, fg(DIM), stream=stream)


def ok(text: str, *, stream: TextIO | None = None) -> str:
    return paint(text, fg(GREEN), stream=stream)


def err(text: str, *, stream: TextIO | None = None) -> str:
    return paint(text, fg(RED), stream=stream)


def selected(text: str, *, stream: TextIO | None = None) -> str:
    return paint(text, BOLD, bg(SEL_BG), fg(SEL_FG), stream=stream)


def logo(*, stream: TextIO | None = None) -> str:
    """Three-line stick-with-caps. Shown once when Baton takes the terminal."""
    if not color_enabled(stream):
        return "\n".join(LOGO_PLAIN)
    m, g, r = fg(MAGENTA), fg(GOLD), RESET
    return "\n".join(
        (
            f"  {m}┌──{g}●{m}──┐{r}",
            f"  {m}│{g}BATON{m}│{r}",
            f"  {m}└──{g}●{m}──┘{r}",
        )
    )


def wordmark(*, stream: TextIO | None = None) -> str:
    """One-line mark for the picker overlay — enough to say this is Baton."""
    stick = paint("●════●", fg(MAGENTA), stream=stream)
    name = gold("BATON", stream=stream)
    return f"{stick} {name}"


def heading(text: str, *, stream: TextIO | None = None) -> str:
    return gold(text, stream=stream)


def log(message: str, *, file: TextIO | None = None, kind: str = "info") -> None:
    """stderr status: magenta `baton:` plus gold/red body."""
    file = file or sys.stderr
    tag = magenta("baton", stream=file)
    if kind == "error":
        body = err(message, stream=file)
    elif kind == "ok":
        body = gold(message, stream=file)
    else:
        body = brass(message, stream=file)
    print(f"{tag}: {body}", file=file)


def print_logo(*, file: TextIO | None = None, tagline: str | None = None) -> None:
    file = file or sys.stderr
    print(logo(stream=file), file=file)
    if tagline:
        print(dim(tagline, stream=file), file=file)


def print_interstitial(target_label: str, *, file: TextIO | None = None) -> None:
    """Full-screen hop screen shown while a switch is in flight.

    The txcript session hop plus the next CLI's own startup can take a
    couple of seconds with nothing on screen otherwise — this covers that
    gap instead of leaving the outgoing CLI's stale frame up. The next
    child's own output (or our `log()` lines) naturally overwrites it.
    """
    file = file or sys.stdout
    if color_enabled(file):
        file.write("\x1b[H\x1b[2J")
    print(logo(stream=file), file=file)
    print(dim(f"hopping to {target_label}…", stream=file), file=file)
    file.flush()
