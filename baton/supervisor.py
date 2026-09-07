from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

from baton.bus import PaneState, socket_path
from baton.catalog import Model, make_model, resolve
from baton.clis import require_enabled
from baton.config import Config, load_config
from baton.launch import launch_argv
from baton.panes import remove_pane, write_pane
from baton.discover import latest_session
from baton.provider_models import collect_catalog
from baton.style import log, print_logo
from baton.txcript_hop import TxcriptError, continue_session


class Supervisor:
    def __init__(
        self,
        *,
        cwd: Path,
        thread_id: str,
        model: Model,
        session_id: str | None,
        cfg: Config,
        pane_id: str | None = None,
    ) -> None:
        self.cfg = cfg
        self.cwd = cwd.resolve()
        self.thread_id = thread_id
        self._model = model
        self.session_id = session_id
        self.pane_id = pane_id or uuid.uuid4().hex[:8]
        self.child: subprocess.Popen | None = None
        self.pending_model: Model | None = None
        self.pending_range: str | None = None
        self.pending_pick = False
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self._server: socket.socket | None = None
        self._pty_master: int | None = None

    @property
    def model(self) -> Model:
        return self._model

    def state(self, *, idle: bool) -> PaneState:
        model = self.model
        return PaneState(
            pane_id=self.pane_id,
            thread_id=self.thread_id,
            cwd=str(self.cwd),
            model_id=model.key,
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

    def apply_model(self, nxt: Model, span: str | None = None) -> str:
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
        self._model = nxt
        return (
            f"now {nxt.display_label()} @ {nxt.harness}"
            + (f"  session {self.session_id}" if self.session_id else "")
        )

    def _model_from_request(self, req: dict) -> Model:
        harness = str(req.get("harness") or "").strip()
        provider = str(req.get("provider_model") or "").strip()
        if harness and provider:
            return make_model(harness, provider, label=str(req.get("label") or ""))
        needle = str(req.get("model") or "").strip()
        catalog, errors = collect_catalog(self.cfg.clis)
        if not catalog:
            raise RuntimeError("; ".join(errors) or "no models from enabled CLIs")
        return resolve(catalog, needle)

    def _handle(self, req: dict) -> dict:
        op = req.get("op")
        if op == "ping":
            return {"ok": True, "state": self.state(idle=self.child is None or self.child.poll() is not None).to_dict()}
        if op == "status":
            idle = self.child is None or self.child.poll() is not None
            return {"ok": True, "state": self.state(idle=idle).to_dict()}
        if op == "set_model":
            nxt = self._model_from_request(req)
            span = req.get("range")
            with self.lock:
                self.pending_model = nxt
                self.pending_range = str(span) if span else None
                child = self.child
            if child is not None and child.poll() is None:
                child.terminate()
            return {"ok": True, "queued": nxt.key, "pane_id": self.pane_id}
        if op == "pick":
            with self.lock:
                self.pending_pick = True
                child = self.child
            if child is not None and child.poll() is None:
                timer = threading.Timer(0.4, self._terminate_child)
                timer.daemon = True
                timer.start()
            return {"ok": True, "queued": "pick", "pane_id": self.pane_id}
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

    def _terminate_child(self) -> None:
        child = self.child
        if child is not None and child.poll() is None:
            child.terminate()

    def _restore_tty(self) -> None:
        if not sys.stdin.isatty():
            return
        subprocess.run(["stty", "sane"], check=False)

    def _spawn(self) -> subprocess.Popen:
        from baton.ptyctl import spawn_with_pty

        model = self.model
        rec = require_enabled(self.cfg.clis, model.harness)
        argv = launch_argv(rec, model, self.session_id)
        log(f"launching {' '.join(argv)}")
        child, master = spawn_with_pty(argv, str(self.cwd))
        self._pty_master = master
        return child

    def _run_child(self) -> str:
        from baton.ptyctl import EXIT, PICK, pump

        child = self.child
        if child is None:
            return EXIT
        master = getattr(self, "_pty_master", None)
        if master is None:
            child.wait()
            return EXIT
        try:
            return pump(child, master, self.stop)
        finally:
            try:
                os.close(master)
            except OSError:
                pass
            self._pty_master = None

    def run(self) -> int:
        thread = threading.Thread(target=self._serve, name="baton-bus", daemon=True)
        thread.start()
        self.persist(idle=True)
        print_logo(tagline="hand off the thread  ·  /baton to switch models")
        log(f"pane {self.pane_id}  thread {self.thread_id}")
        try:
            while not self.stop.is_set():
                with self.lock:
                    pending = self.pending_model
                    span = self.pending_range
                    picking = self.pending_pick
                    self.pending_model = None
                    self.pending_range = None
                    self.pending_pick = False
                if pending:
                    try:
                        msg = self.apply_model(pending, span)
                    except (TxcriptError, RuntimeError, KeyError) as exc:
                        log(f"switch failed: {exc}", kind="error")
                        self.persist(idle=True)
                        time.sleep(0.2)
                        continue
                    log(msg, kind="ok")
                if picking:
                    self._restore_tty()
                    from baton.sidecar import choose_model

                    chosen = choose_model(
                        status_lines=[
                            "switch model — enter to hop, q keeps the current CLI",
                        ]
                    )
                    if chosen is not None:
                        try:
                            msg = self.apply_model(chosen)
                            log(msg, kind="ok")
                        except (TxcriptError, RuntimeError, KeyError) as exc:
                            log(f"switch failed: {exc}", kind="error")
                try:
                    self.child = self._spawn()
                except RuntimeError as exc:
                    log(str(exc), kind="error")
                    return 1
                self.persist(idle=False)
                from baton.ptyctl import PICK

                reason = self._run_child()
                if reason == PICK:
                    with self.lock:
                        self.pending_pick = True
                    self._terminate_child()
                    if self.child is not None:
                        try:
                            self.child.wait(timeout=3)
                        except subprocess.TimeoutExpired:
                            self.child.kill()
                            self.child.wait()
                self._restore_tty()
                self.child = None
                self.refresh_session_id()
                self.persist(idle=True)
                if self.stop.is_set():
                    break
                with self.lock:
                    has_pending = self.pending_model is not None or self.pending_pick
                if has_pending:
                    continue
                log("operator exited. /baton list, `baton set`, or Ctrl-C to detach.")
                while not self.stop.is_set():
                    time.sleep(0.2)
                    with self.lock:
                        if self.pending_model is not None or self.pending_pick:
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
            log("detached")
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
    harness: str | None = None,
) -> int:
    cfg = load_config()
    workdir = (cwd or Path.cwd()).resolve()
    thread = thread_id or workdir.name
    catalog, errors = collect_catalog(cfg.clis)
    if harness:
        catalog = [m for m in catalog if m.harness == harness]
    if not catalog:
        log(
            "; ".join(errors)
            or (
                f"no models for {harness} — enable it with `baton clis`"
                if harness
                else "no models — enable a CLI with `baton clis`"
            ),
            kind="error",
        )
        return 1
    if model_id:
        start = resolve(catalog, model_id)
    elif harness:
        start = catalog[0]
    elif sys.stdin.isatty():
        from baton.picker import pick

        result = pick(catalog, errors=errors, status_lines=["starting model:"])
        if result.quit or result.model is None:
            return 0
        start = result.model
    else:
        start = catalog[0]
    require_enabled(cfg.clis, start.harness)

    supervisor = Supervisor(
        cwd=workdir,
        thread_id=thread,
        model=start,
        session_id=session_id,
        cfg=cfg,
    )

    def _handle_term(_signum, _frame):
        supervisor.stop.set()
        if supervisor.child is not None and supervisor.child.poll() is None:
            supervisor.child.terminate()

    signal.signal(signal.SIGTERM, _handle_term)
    return supervisor.run()
