"""PTY shim so `/baton` is caught even when a TUI swallows slash commands."""

from __future__ import annotations

import os
import pty
import select
import signal
import sys
import termios
import tty
from typing import TYPE_CHECKING

from baton.hook import prompt_is_baton

if TYPE_CHECKING:
    import subprocess
    import threading

PICK = "pick"
EXIT = "exit"


class LineTracker:
    """Follow the in-progress input line. Enter on `/baton` is a pick, not submit."""

    def __init__(self) -> None:
        self.line = bytearray()
        self.state = "ground"

    def feed(self, chunk: bytes) -> tuple[bytes, bool]:
        out = bytearray()
        pick = False
        for b in chunk:
            if pick:
                break
            if self._is_pick_enter(b):
                pick = True
                break
            self._note(b)
            out.append(b)
        return bytes(out), pick

    def _is_pick_enter(self, b: int) -> bool:
        if self.state != "ground" or b not in {10, 13}:
            return False
        try:
            text = self.line.decode("utf-8")
        except UnicodeDecodeError:
            text = self.line.decode("latin-1")
        return prompt_is_baton(text)

    def _note(self, b: int) -> None:
        if self.state == "esc":
            self.state = "csi" if b == 0x5B else "ground"
            if self.state == "ground":
                self.line.clear()
            return
        if self.state == "csi":
            if 0x40 <= b <= 0x7E:
                self.state = "ground"
            return
        if b == 0x1B:
            self.state = "esc"
            return
        if b in {10, 13}:
            self.line.clear()
            return
        if b in {8, 0x7F}:
            if self.line:
                self.line.pop()
            return
        if b == 0x15:
            self.line.clear()
            return
        if b == 3:
            self.line.clear()
            return
        if 32 <= b < 127:
            self.line.append(b)


def _copy_winsize(src_fd: int, dst_fd: int) -> None:
    import fcntl
    import struct

    try:
        raw = fcntl.ioctl(src_fd, termios.TIOCGWINSZ, b"\x00" * 8)
        fcntl.ioctl(dst_fd, termios.TIOCSWINSZ, raw)
    except OSError:
        rows, cols = 24, 80
        packed = struct.pack("HHHH", rows, cols, 0, 0)
        try:
            fcntl.ioctl(dst_fd, termios.TIOCSWINSZ, packed)
        except OSError:
            pass


def spawn_with_pty(argv: list[str], cwd: str) -> tuple[subprocess.Popen, int | None]:
    import subprocess

    if not sys.stdin.isatty() or not sys.stdout.isatty():
        return subprocess.Popen(argv, cwd=cwd), None
    master, slave = pty.openpty()
    _copy_winsize(sys.stdin.fileno(), slave)
    try:
        child = subprocess.Popen(
            argv,
            cwd=cwd,
            stdin=slave,
            stdout=slave,
            stderr=slave,
            start_new_session=True,
        )
    except Exception:
        os.close(master)
        os.close(slave)
        raise
    os.close(slave)
    return child, master


def pump(
    child: subprocess.Popen,
    master: int,
    stop: threading.Event,
) -> str:
    stdin_fd = sys.stdin.fileno()
    old = termios.tcgetattr(stdin_fd)
    tracker = LineTracker()
    previous_winch = signal.getsignal(signal.SIGWINCH)

    def _winch(_signum, _frame):
        _copy_winsize(stdin_fd, master)

    try:
        tty.setraw(stdin_fd)
        signal.signal(signal.SIGWINCH, _winch)
        _copy_winsize(stdin_fd, master)
        while child.poll() is None and not stop.is_set():
            try:
                readable, _, _ = select.select([stdin_fd, master], [], [], 0.2)
            except (InterruptedError, ValueError):
                continue
            if stdin_fd in readable:
                try:
                    data = os.read(stdin_fd, 1024)
                except OSError:
                    data = b""
                if not data:
                    break
                forwarded, pick = tracker.feed(data)
                if forwarded:
                    os.write(master, forwarded)
                if pick:
                    try:
                        os.write(master, b"\x1b\x15")
                    except OSError:
                        pass
                    return PICK
            if master in readable:
                try:
                    data = os.read(master, 4096)
                except OSError:
                    data = b""
                if not data:
                    break
                os.write(sys.stdout.fileno(), data)
        return EXIT
    finally:
        signal.signal(signal.SIGWINCH, previous_winch)
        termios.tcsetattr(stdin_fd, termios.TCSADRAIN, old)
