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
from baton.catalog import HARNESS_CURSOR, Model, make_model, resolve
from baton.clis import require_enabled
from baton.config import Config, load_config
from baton.cursor_resume import seal_imported_cursor_session
from baton.launch import launch_argv
from baton.panes import remove_pane, write_pane
from baton.paths import ensure_dirs
from baton.discover import latest_session
from baton.provider_models import collect_catalog
from baton.skill_bridge import offer_user_skill_links
from baton.style import log, print_interstitial, print_logo
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
        extra_args: list[str] | None = None,
    ) -> None:
        self.cfg = cfg
        self.cwd = cwd.resolve()
        self.thread_id = thread_id
        self._model = model
        self.session_id = session_id
        self._provider_args = list(extra_args or [])
        self.pane_id = pane_id or uuid.uuid4().hex[:8]
        self.child: subprocess.Popen | None = None
        self.pending_model: Model | None = None
        self.pending_range: str | None = None
        self.pending_pick = False
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self._server: socket.socket | None = None
        self._pty_master: int | None = None
        self._abandoned = False
        self._picking = False
        self._bus_thread: threading.Thread | None = None
        self._rollback: tuple[Model, str | None] | None = None

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
            supervisor_pid=os.getpid(),
        )

    def persist(self, *, idle: bool) -> None:
        write_pane(self.state(idle=idle))

    def refresh_session_id(self) -> None:
        """Discover an initial native session; keep a known thread pinned on recovery."""
        if self.session_id:
            return
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
            if nxt.harness == HARNESS_CURSOR:
                seal_imported_cursor_session(result.session_id, self.cwd)
            self._restore_tty()
            try:
                offer_user_skill_links(nxt.harness)
            except OSError as exc:
                log(f"skill links: {exc}", kind="error")
            self._rollback = (current, self.session_id)
            self.session_id = result.session_id
        elif nxt != current:
            self._rollback = (current, self.session_id)
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
        catalog, errors = collect_catalog(self.cfg.clis, refresh=False)
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
                self._schedule_child_stop(child, delay=0)
            return {"ok": True, "queued": nxt.key, "pane_id": self.pane_id}
        if op == "pick":
            with self.lock:
                if self.pending_pick or self._picking:
                    return {"ok": True, "queued": "pick", "pane_id": self.pane_id}
                self.pending_pick = True
                child = self.child
            if child is not None and child.poll() is None:
                self._schedule_child_stop(child, delay=0.4)
            return {"ok": True, "queued": "pick", "pane_id": self.pane_id}
        if op == "detach":
            self.stop.set()
            if self.child is not None and self.child.poll() is None:
                self.child.terminate()
            return {"ok": True}
        return {"ok": False, "error": f"unknown op {op!r}"}

    def _serve(self) -> None:
        path = socket_path(self.pane_id)
        while not self.stop.is_set():
            server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                ensure_dirs()
                path.unlink(missing_ok=True)
                server.bind(str(path))
                server.listen(8)
                server.settimeout(0.2)
                self._server = server
                while not self.stop.is_set() and path.exists():
                    self.persist(idle=self.child is None or self.child.poll() is not None)
                    try:
                        conn, _ = server.accept()
                    except TimeoutError:
                        continue
                    with conn:
                        deadline = time.monotonic() + 0.2
                        try:
                            raw = bytearray()
                            while b"\n" not in raw and len(raw) <= 8192:
                                remaining = deadline - time.monotonic()
                                if remaining <= 0:
                                    raise TimeoutError("incomplete control request")
                                conn.settimeout(remaining)
                                piece = conn.recv(8192)
                                if not piece:
                                    break
                                raw.extend(piece)
                            if not raw:
                                continue
                            if len(raw) > 8192:
                                raise ValueError("request too large")
                            req = json.loads(raw.decode("utf-8").splitlines()[0])
                            if not isinstance(req, dict):
                                raise ValueError("request must be an object")
                            resp = self._handle(req)
                        except Exception as exc:  # noqa: BLE001 — isolate faulty clients
                            resp = {"ok": False, "error": str(exc)}
                        try:
                            conn.sendall((json.dumps(resp) + "\n").encode("utf-8"))
                        except OSError:
                            pass  # The hook may exit before reading its acknowledgement.
            except Exception as exc:  # noqa: BLE001 — rebuild failed control infrastructure
                if not self.stop.is_set():
                    log(f"reconnecting pane control: {exc}", kind="error")
                    self.stop.wait(0.2)
            finally:
                server.close()
                self._server = None
        remove_pane(self.pane_id)

    def _ensure_bus(self) -> None:
        if not self.stop.is_set() and (self._bus_thread is None or not self._bus_thread.is_alive()):
            self._bus_thread = threading.Thread(target=self._serve, name="baton-bus", daemon=True)
            self._bus_thread.start()

    def _schedule_child_stop(self, child: subprocess.Popen, *, delay: float) -> None:
        # Capture this child: a delayed hook must never terminate its replacement.
        def stop_child() -> None:
            if child.poll() is None:
                try:
                    child.terminate()
                    child.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
                except ProcessLookupError:
                    pass

        timer = threading.Timer(delay, stop_child)
        timer.daemon = True
        timer.start()

    def abandon(self) -> None:
        """Drop child and pane files. Safe from signals; must not wait for finally."""
        if self._abandoned:
            return
        self._abandoned = True
        self.stop.set()
        self._terminate_child()
        if self._server is not None:
            try:
                self._server.close()
            except OSError:
                pass
            self._server = None
        remove_pane(self.pane_id)

    def _terminate_child(self) -> None:
        child = self.child
        if child is not None and child.poll() is None:
            try:
                child.terminate()
            except ProcessLookupError:
                pass

    def _restore_tty(self) -> None:
        if not sys.stdin.isatty():
            return
        subprocess.run(["stty", "sane"], check=False)

    def _spawn(self) -> subprocess.Popen:
        from baton.ptyctl import spawn_with_pty

        model = self.model
        rec = require_enabled(self.cfg.clis, model.harness)
        extra = self._provider_args
        argv = launch_argv(rec, model, self.session_id, extra_args=extra)
        log(f"launching {' '.join(argv)}")
        child, master = spawn_with_pty(argv, str(self.cwd))
        self._provider_args = []
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
            return pump(child, master, self.stop, tick=self._ensure_bus)
        finally:
            try:
                os.close(master)
            except OSError:
                pass
            self._pty_master = None

    def run(self) -> int:
        self._ensure_bus()
        self.persist(idle=True)
        print_logo(tagline="hand off the thread  ·  /baton to switch models")
        log(f"pane {self.pane_id}  thread {self.thread_id}")
        failures = 0
        try:
            while not self.stop.is_set():
                self._ensure_bus()
                with self.lock:
                    pending = self.pending_model
                    span = self.pending_range
                    picking = self.pending_pick
                    self._picking = picking
                    self.pending_model = None
                    self.pending_range = None
                    self.pending_pick = False
                if pending:
                    print_interstitial(pending.display_label())
                    try:
                        msg = self.apply_model(pending, span)
                    except (TxcriptError, RuntimeError, KeyError, OSError) as exc:
                        log(f"switch failed: {exc}", kind="error")
                    else:
                        log(msg, kind="ok")
                if picking:
                    self._restore_tty()
                    from baton.sidecar import choose_model

                    log("loading model list…")
                    try:
                        chosen = choose_model(
                            status_lines=[
                                "switch model — enter to hop, q keeps the current CLI",
                            ]
                        )
                    except (RuntimeError, ValueError, OSError) as exc:
                        log(f"picker failed; resuming current CLI: {exc}", kind="error")
                        chosen = None
                    finally:
                        with self.lock:
                            self._picking = False
                    if chosen is not None:
                        print_interstitial(chosen.display_label())
                        try:
                            msg = self.apply_model(chosen)
                            log(msg, kind="ok")
                        except (TxcriptError, RuntimeError, KeyError, OSError) as exc:
                            log(f"switch failed: {exc}", kind="error")
                launched_at = time.monotonic()
                try:
                    self.child = self._spawn()
                except (RuntimeError, OSError, KeyError) as exc:
                    log(f"launch failed: {exc}", kind="error")
                    if self._rollback is not None:
                        self._model, self.session_id = self._rollback
                        self._rollback = None
                        log("resuming previous CLI")
                        continue
                    failures += 1
                    if failures <= 2:
                        self.stop.wait(0.5 * failures)
                        continue
                    self._wait_for_request()
                    failures = 0
                    continue
                self.persist(idle=False)
                from baton.ptyctl import PICK

                try:
                    reason = self._run_child()
                except OSError as exc:
                    log(f"terminal connection interrupted: {exc}", kind="error")
                    reason = "error"
                if reason == PICK:
                    with self.lock:
                        self.pending_pick = True
                # Always reap the old child, including an early PTY close.
                self._terminate_child()
                if self.child is not None:
                    try:
                        self.child.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        self.child.kill()
                        self.child.wait()
                returncode = self.child.returncode if self.child is not None else 0
                self._restore_tty()
                self.child = None
                self.refresh_session_id()
                self.persist(idle=True)
                if self.stop.is_set():
                    break
                if not sys.stdin.isatty():
                    log("tty closed, detaching")
                    break
                with self.lock:
                    has_pending = self.pending_model is not None or self.pending_pick
                if has_pending:
                    self._rollback = None
                    failures = 0
                    continue
                if returncode and time.monotonic() - launched_at < 5 and self._rollback:
                    self._model, self.session_id = self._rollback
                    self._rollback = None
                    log("new CLI exited during startup; resuming previous CLI", kind="error")
                    continue
                self._rollback = None
                if returncode or reason == "error":
                    failures = failures + 1 if time.monotonic() - launched_at < 30 else 1
                    if failures <= 2:
                        log("CLI interrupted; resuming saved session", kind="error")
                        self.stop.wait(0.5 * failures)
                        continue
                self._wait_for_request()
                failures = 0
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
            self.abandon()
        return 0

    def _wait_for_request(self) -> None:
        from baton.ptyctl import wait_for_input

        log("CLI stopped. /baton to switch, Enter to resume, Ctrl-C to detach.")

        def pending() -> bool:
            self._ensure_bus()
            with self.lock:
                return self.pending_model is not None or self.pending_pick

        reason = wait_for_input(self.stop, pending)
        if reason == "pick":
            with self.lock:
                self.pending_pick = True


def attach(
    *,
    cwd: Path | None = None,
    thread_id: str | None = None,
    model_id: str | None = None,
    session_id: str | None = None,
    harness: str | None = None,
    extra_args: list[str] | None = None,
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
        extra_args=extra_args,
    )

    _install_lifecycle_hooks(supervisor)
    return supervisor.run()


def _install_lifecycle_hooks(supervisor: Supervisor) -> None:
    """Unlink the pane on hangup/kill so a leftover .sock cannot trap the next attach.

    SIGHUP (closed terminal) otherwise terminates Python without ``finally``.
    """
    import atexit

    atexit.register(supervisor.abandon)

    def _on_signal(signum, _frame):
        supervisor.abandon()
        supervisor._restore_tty()
        if signum == signal.SIGINT:
            raise KeyboardInterrupt
        os._exit(128 + signum)

    for name in ("SIGHUP", "SIGTERM", "SIGQUIT"):
        sig = getattr(signal, name, None)
        if sig is None:
            continue
        try:
            signal.signal(sig, _on_signal)
        except (ValueError, OSError):
            continue
