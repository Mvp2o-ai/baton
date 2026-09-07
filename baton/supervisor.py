from __future__ import annotations

import json
import signal
import socket
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

from baton.bus import PaneState, socket_path
from baton.catalog import get_model
from baton.clis import require_enabled
from baton.config import Config, load_config
from baton.launch import launch_argv
from baton.panes import remove_pane, write_pane
from baton.discover import latest_session
from baton.txcript_hop import TxcriptError, continue_session


class Supervisor:
    def __init__(
        self,
        *,
        cwd: Path,
        thread_id: str,
        model_id: str,
        session_id: str | None,
        cfg: Config,
        pane_id: str | None = None,
    ) -> None:
        self.cfg = cfg
        self.cwd = cwd.resolve()
        self.thread_id = thread_id
        self.model_id = model_id
        self.session_id = session_id
        self.pane_id = pane_id or uuid.uuid4().hex[:8]
        self.child: subprocess.Popen | None = None
        self.pending_model: str | None = None
        self.pending_range: str | None = None
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self._server: socket.socket | None = None

    @property
    def model(self):
        return get_model(self.cfg.models, self.model_id)

    def state(self, *, idle: bool) -> PaneState:
        model = self.model
        return PaneState(
            pane_id=self.pane_id,
            thread_id=self.thread_id,
            cwd=str(self.cwd),
            model_id=model.id,
            harness=model.harness,
            session_id=self.session_id,
            idle=idle,
            pid=self.child.pid if self.child and self.child.poll() is None else None,
        )

    def persist(self, *, idle: bool) -> None:
        write_pane(self.state(idle=idle))

    def refresh_session_id(self) -> None:
        """After a home CLI exits, pick up the newest native session for this cwd."""
        found = latest_session(self.model.harness, self.cwd)
        if found:
            self.session_id = found.session_id

    def apply_model(self, model_id: str, span: str | None = None) -> str:
        nxt = get_model(self.cfg.models, model_id)
        require_enabled(self.cfg.clis, nxt.harness)
        current = self.model
        if nxt.harness != current.harness:
            self.refresh_session_id()
            if not self.session_id:
                raise RuntimeError(
                    "no native session id yet; work in the current CLI once, or pass --session"
                )
            source_ref = self.session_id
            if span:
                source_ref = f"{self.session_id}#{span}"
            result = continue_session(
                session_id=source_ref,
                source_harness=current.harness,
                target_harness=nxt.harness,
                cwd=self.cwd,
                txcript_bin=self.cfg.txcript_bin,
            )
            self.session_id = result.session_id
        self.model_id = nxt.id
        return (
            f"now {nxt.id} @ {nxt.harness}"
            + (f"  session {self.session_id}" if self.session_id else "")
        )

    def _handle(self, req: dict) -> dict:
        op = req.get("op")
        if op == "ping":
            return {"ok": True, "state": self.state(idle=self.child is None or self.child.poll() is not None).to_dict()}
        if op == "status":
            idle = self.child is None or self.child.poll() is not None
            return {"ok": True, "state": self.state(idle=idle).to_dict()}
        if op == "set_model":
            model_id = str(req.get("model") or "")
            get_model(self.cfg.models, model_id)
            span = req.get("range")
            with self.lock:
                self.pending_model = model_id
                self.pending_range = str(span) if span else None
                child = self.child
            if child is not None and child.poll() is None:
                child.terminate()
            return {"ok": True, "queued": model_id, "pane_id": self.pane_id}
        if op == "detach":
            self.stop.set()
            if self.child is not None and self.child.poll() is None:
                self.child.terminate()
            return {"ok": True}
        return {"ok": False, "error": f"unknown op {op!r}"}

    def _serve(self) -> None:
        path = socket_path(self.pane_id)
        path.unlink(missing_ok=True)
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(path))
        server.listen(8)
        server.settimeout(0.4)
        self._server = server
        while not self.stop.is_set():
            try:
                conn, _ = server.accept()
            except TimeoutError:
                continue
            except OSError:
                break
            with conn:
                try:
                    raw = conn.recv(8192).decode("utf-8").strip()
                    req = json.loads(raw.splitlines()[0]) if raw else {}
                    resp = self._handle(req)
                except Exception as exc:  # noqa: BLE001 — socket handler must not die
                    resp = {"ok": False, "error": str(exc)}
                conn.sendall((json.dumps(resp) + "\n").encode("utf-8"))
        server.close()
        path.unlink(missing_ok=True)

    def _restore_tty(self) -> None:
        if not sys.stdin.isatty():
            return
        subprocess.run(["stty", "sane"], check=False)

    def _spawn(self) -> subprocess.Popen:
        model = self.model
        rec = require_enabled(self.cfg.clis, model.harness)
        argv = launch_argv(rec, model, self.session_id)
        print(f"baton: launching {' '.join(argv)}", file=sys.stderr)
        return subprocess.Popen(argv, cwd=str(self.cwd))

    def run(self) -> int:
        thread = threading.Thread(target=self._serve, name="baton-bus", daemon=True)
        thread.start()
        self.persist(idle=True)
        print(
            f"baton: pane {self.pane_id}  thread {self.thread_id}  "
            f"sidecar: baton model <id> --pane {self.pane_id}",
            file=sys.stderr,
        )
        try:
            while not self.stop.is_set():
                with self.lock:
                    pending = self.pending_model
                    span = self.pending_range
                    self.pending_model = None
                    self.pending_range = None
                if pending:
                    try:
                        msg = self.apply_model(pending, span)
                    except (TxcriptError, RuntimeError, KeyError) as exc:
                        print(f"baton: switch failed: {exc}", file=sys.stderr)
                        self.persist(idle=True)
                        time.sleep(0.2)
                        continue
                    print(f"baton: {msg}", file=sys.stderr)
                try:
                    self.child = self._spawn()
                except RuntimeError as exc:
                    print(f"baton: {exc}", file=sys.stderr)
                    return 1
                self.persist(idle=False)
                self.child.wait()
                self._restore_tty()
                self.child = None
                self.refresh_session_id()
                self.persist(idle=True)
                if self.stop.is_set():
                    break
                with self.lock:
                    has_pending = self.pending_model is not None
                if has_pending:
                    continue
                print(
                    "baton: operator exited. waiting for sidecar model switch, "
                    "or Ctrl-C to detach.",
                    file=sys.stderr,
                )
                while not self.stop.is_set():
                    time.sleep(0.2)
                    with self.lock:
                        if self.pending_model is not None:
                            break
        except KeyboardInterrupt:
            self.stop.set()
            if self.child is not None and self.child.poll() is None:
                self.child.terminate()
                try:
                    self.child.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.child.kill()
            self._restore_tty()
            print("baton: detached", file=sys.stderr)
            return 130
        finally:
            self.stop.set()
            if self._server is not None:
                try:
                    self._server.close()
                except OSError:
                    pass
            remove_pane(self.pane_id)
        return 0


def attach(
    *,
    cwd: Path | None = None,
    thread_id: str | None = None,
    model_id: str | None = None,
    session_id: str | None = None,
) -> int:
    cfg = load_config()
    workdir = (cwd or Path.cwd()).resolve()
    thread = thread_id or workdir.name
    start_model = model_id or cfg.models[0].id
    get_model(cfg.models, start_model)
    require_enabled(cfg.clis, get_model(cfg.models, start_model).harness)

    supervisor = Supervisor(
        cwd=workdir,
        thread_id=thread,
        model_id=start_model,
        session_id=session_id,
        cfg=cfg,
    )

    def _handle_term(_signum, _frame):
        supervisor.stop.set()
        if supervisor.child is not None and supervisor.child.poll() is None:
            supervisor.child.terminate()

    signal.signal(signal.SIGTERM, _handle_term)
    return supervisor.run()
