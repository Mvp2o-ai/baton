from __future__ import annotations

import json
import socket
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from baton.paths import sockets_dir


def socket_path(pane_id: str) -> Path:
    return sockets_dir() / f"{pane_id}.sock"


def is_pane_listening(pane_id: str, timeout: float = 0.2) -> bool:
    """True only if a supervisor answers. A leftover .sock is not live."""
    try:
        resp = send_request(pane_id, {"op": "status"}, timeout=timeout)
    except (FileNotFoundError, OSError, RuntimeError, json.JSONDecodeError, ValueError):
        return False
    return bool(resp.get("ok"))


def send_request(pane_id: str, payload: dict[str, Any], timeout: float = 5.0) -> dict[str, Any]:
    path = socket_path(pane_id)
    data = (json.dumps(payload) + "\n").encode("utf-8")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        deadline = time.monotonic() + timeout
        while True:
            sock.settimeout(max(0.001, deadline - time.monotonic()))
            try:
                sock.connect(str(path))
                break
            except (FileNotFoundError, ConnectionRefusedError):
                if time.monotonic() >= deadline:
                    raise
                time.sleep(min(0.05, max(0, deadline - time.monotonic())))
        # Retry only connection establishment. Once sent, a mutation may already
        # have happened even if its acknowledgement gets lost.
        sock.settimeout(max(0.001, deadline - time.monotonic()))
        sock.sendall(data)
        chunks: list[bytes] = []
        while True:
            piece = sock.recv(4096)
            if not piece:
                break
            chunks.append(piece)
            if b"\n" in piece:
                break
    raw = b"".join(chunks).decode("utf-8").strip()
    if not raw:
        raise RuntimeError("empty response from pane supervisor")
    return json.loads(raw.splitlines()[0])


@dataclass
class PaneState:
    pane_id: str
    thread_id: str
    cwd: str
    model_id: str
    harness: str
    session_id: str | None
    idle: bool
    pid: int | None = None
    supervisor_pid: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "pane_id": self.pane_id,
            "thread_id": self.thread_id,
            "cwd": self.cwd,
            "model_id": self.model_id,
            "harness": self.harness,
            "session_id": self.session_id,
            "idle": self.idle,
            "pid": self.pid,
            "supervisor_pid": self.supervisor_pid,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "PaneState":
        return cls(
            pane_id=str(raw["pane_id"]),
            thread_id=str(raw["thread_id"]),
            cwd=str(raw["cwd"]),
            model_id=str(raw["model_id"]),
            harness=str(raw["harness"]),
            session_id=raw.get("session_id"),
            idle=bool(raw.get("idle")),
            pid=raw.get("pid"),
            supervisor_pid=raw.get("supervisor_pid"),
        )
