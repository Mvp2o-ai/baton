from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from baton.catalog import make_model
from baton.clis import CliRecord
from baton.config import Config
from baton.supervisor import Supervisor


def supervisor(tmp_path: Path) -> Supervisor:
    return Supervisor(
        cwd=tmp_path,
        thread_id="recovery",
        model=make_model("cursor", "composer-test"),
        session_id="original-thread",
        cfg=Config(clis={
            harness: CliRecord(harness, (sys.executable,), True, sys.executable)
            for harness in ("cursor", "codex")
        }),
        pane_id="recovery",
    )


@pytest.mark.parametrize("failed_source", ["bundled", "live", "both"])
def test_codex_timeout_preserves_other_sources(monkeypatch, failed_source):
    from baton.provider_models import fetch_codex

    def run(_binary, args, *, timeout):
        source = "bundled" if "--bundled" in args else "live"
        if failed_source in {source, "both"}:
            raise subprocess.TimeoutExpired(args, timeout)
        return {"models": [{"slug": f"gpt-5.6-{source}"}]}

    monkeypatch.setattr("baton.provider_models._run_json", run)
    monkeypatch.setattr("baton.provider_models._read_codex_models_cache", lambda: {
        "models": [{"slug": "gpt-5.6-cache"}],
    })
    rows = fetch_codex(CliRecord("codex", ("codex",), True, sys.executable))
    expected = {"bundled": "gpt-5.6-live", "live": "gpt-5.6-bundled", "both": "gpt-5.6-cache"}
    assert [row.provider_model for row in rows] == [expected[failed_source]]


def test_picker_reuses_catalog_and_refresh_failure_keeps_rows(monkeypatch):
    from baton.provider_models import collect_catalog

    monkeypatch.setattr("baton.provider_models._LAST_GOOD", {})
    model = make_model("cursor", "composer-test")
    calls = []

    def fetch(rec):
        calls.append(rec.harness)
        if len(calls) > 1:
            raise subprocess.TimeoutExpired("agent models", 20)
        return [model]

    monkeypatch.setattr("baton.provider_models.fetch_harness", fetch)
    clis = {"cursor": CliRecord("cursor", ("agent",), True, sys.executable)}
    assert collect_catalog(clis) == ([model], [])
    assert collect_catalog(clis, refresh=False) == ([model], [])
    assert len(calls) == 1
    rows, errors = collect_catalog(clis)
    assert rows == [model]
    assert "using last successful list" in errors[0]
    clis["cursor"].enabled = False
    assert collect_catalog(clis, refresh=False) == ([], [])


def test_catalog_process_cannot_consume_picker_input(monkeypatch):
    from baton.provider_models import _run

    seen = {}
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: seen.update(kwargs))
    _run("agent", ["models"], timeout=1)
    assert seen["stdin"] == subprocess.DEVNULL


def test_live_owner_survives_failed_health_check(monkeypatch, tmp_path):
    from baton.panes import list_panes, pane_file, write_pane

    monkeypatch.setenv("BATON_HOME", str(tmp_path))
    sup = supervisor(tmp_path)
    state = sup.state(idle=True)
    write_pane(state)
    monkeypatch.setattr("baton.panes.is_pane_listening", lambda _: False)
    assert list_panes() == [state]
    assert pane_file(sup.pane_id).exists()


@pytest.fixture
def live_bus(monkeypatch):
    from baton.bus import send_request

    # Unix socket addresses are limited to ~100 bytes, including pytest's path.
    with tempfile.TemporaryDirectory(prefix="br-", dir="/tmp") as directory:
        root = Path(directory)
        monkeypatch.setenv("BATON_HOME", directory)
        sup = supervisor(root)
        sup._ensure_bus()
        try:
            assert send_request(sup.pane_id, {"op": "ping"}, timeout=2)["ok"]
            yield sup
        finally:
            sup.abandon()
            sup._bus_thread.join(timeout=2)
            assert not sup._bus_thread.is_alive()


def test_bus_survives_disconnected_malformed_and_stalled_clients(live_bus):
    from baton.bus import send_request, socket_path

    path = str(socket_path(live_bus.pane_id))
    for payload in (b'{"op":"pick"}\n', b'[]\n', b'{broken}\n'):
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.connect(path)
            client.sendall(payload)
        assert send_request(live_bus.pane_id, {"op": "status"}, timeout=2)["ok"]
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as stalled:
        stalled.connect(path)
        stalled.sendall(b'{"op":')
        assert send_request(live_bus.pane_id, {"op": "status"}, timeout=2)["ok"]


def test_bus_recreates_removed_socket_and_pane(live_bus):
    from baton.bus import send_request, socket_path
    from baton.panes import pane_file

    socket_path(live_bus.pane_id).unlink()
    pane_file(live_bus.pane_id).unlink()
    response = send_request(live_bus.pane_id, {"op": "pick"}, timeout=2)
    assert response["ok"]
    assert response["queued"] == "pick"
    assert pane_file(live_bus.pane_id).exists()
    assert live_bus.pending_pick


def test_bus_restarts_after_listener_closes(live_bus):
    from baton.bus import send_request

    live_bus._server.close()
    assert send_request(live_bus.pane_id, {"op": "status"}, timeout=2)["ok"]


def test_delayed_stop_cannot_kill_replacement(monkeypatch, tmp_path):
    sup = supervisor(tmp_path)
    callbacks = []
    monkeypatch.setattr("baton.supervisor.threading.Timer", lambda delay, fn: SimpleNamespace(
        start=lambda: callbacks.append(fn), daemon=False,
    ))
    old = SimpleNamespace(poll=lambda: 0)
    sup.child = old
    sup._schedule_child_stop(old, delay=0.4)
    terminated = []
    sup.child = SimpleNamespace(poll=lambda: None, terminate=lambda: terminated.append(True))
    callbacks[0]()
    assert not terminated


def test_repeated_pick_is_coalesced(monkeypatch, tmp_path):
    sup = supervisor(tmp_path)
    sup.child = SimpleNamespace(poll=lambda: None)
    scheduled = []
    monkeypatch.setattr(sup, "_schedule_child_stop", lambda child, **kw: scheduled.append(child))
    assert sup._handle({"op": "pick"})["ok"]
    assert sup._handle({"op": "pick"})["ok"]
    assert len(scheduled) == 1


def test_failed_cursor_preparation_keeps_source_session(monkeypatch, tmp_path):
    sup = supervisor(tmp_path)
    sup._model = make_model("codex", "gpt-test")
    monkeypatch.setattr("baton.supervisor.continue_session", lambda **kw: SimpleNamespace(session_id="converted"))

    def fail(*args):
        raise OSError("store temporarily unavailable")

    monkeypatch.setattr("baton.supervisor.seal_imported_cursor_session", fail)
    with pytest.raises(OSError):
        sup.apply_model(make_model("cursor", "composer-test"))
    assert sup.model.harness == "codex"
    assert sup.session_id == "original-thread"


@pytest.mark.parametrize("failure", ["spawn", "early_exit"])
def test_failed_destination_resumes_source(monkeypatch, tmp_path, failure):
    sup = supervisor(tmp_path)
    sup.pending_model = make_model("codex", "gpt-test")
    monkeypatch.setattr("baton.supervisor.continue_session", lambda **kw: SimpleNamespace(session_id="converted"))
    monkeypatch.setattr("baton.supervisor.offer_user_skill_links", lambda _: None)
    _isolate_run(monkeypatch, sup)
    launched = []

    def spawn():
        launched.append((sup.model.harness, sup.session_id))
        if sup.model.harness == "codex":
            if failure == "spawn":
                raise FileNotFoundError("binary moved")
            return _exited_child(1)
        return _exited_child(0)

    monkeypatch.setattr(sup, "_spawn", spawn)
    monkeypatch.setattr(sup, "_run_child", lambda: "exit")
    assert sup.run() == 0
    assert launched == [("codex", "converted"), ("cursor", "original-thread")]


def test_crashes_retry_same_session_then_leave_controls_available(monkeypatch, tmp_path):
    sup = supervisor(tmp_path)
    _isolate_run(monkeypatch, sup)
    launched = []

    def spawn():
        launched.append(sup.session_id)
        return _exited_child(1)

    monkeypatch.setattr(sup, "_spawn", spawn)
    monkeypatch.setattr(sup, "_run_child", lambda: "exit")
    assert sup.run() == 0
    assert launched == ["original-thread"] * 3


def test_picker_error_resumes_current_cli(monkeypatch, tmp_path):
    sup = supervisor(tmp_path)
    sup.pending_pick = True
    _isolate_run(monkeypatch, sup)

    def fail(**kw):
        raise OSError("interrupted picker")

    monkeypatch.setattr("baton.sidecar.choose_model", fail)
    launched = []
    monkeypatch.setattr(sup, "_spawn", lambda: launched.append(sup.session_id) or _exited_child(0))
    monkeypatch.setattr(sup, "_run_child", lambda: "exit")
    assert sup.run() == 0
    assert launched == ["original-thread"]
    assert not sup._picking


def _exited_child(code):
    return SimpleNamespace(poll=lambda: code, wait=lambda **kw: code, returncode=code)


def _isolate_run(monkeypatch, sup):
    monkeypatch.setattr(sup, "_ensure_bus", lambda: None)
    monkeypatch.setattr(sup, "persist", lambda **kw: None)
    monkeypatch.setattr(sup, "_restore_tty", lambda: None)
    monkeypatch.setattr(sup, "abandon", lambda: None)
    monkeypatch.setattr(sup, "_wait_for_request", sup.stop.set)
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(isatty=lambda: True))


def test_transcript_timeout_is_recoverable(monkeypatch, tmp_path):
    from baton.txcript_hop import TxcriptError, continue_session

    monkeypatch.setattr("baton.txcript_hop.find_txcript", lambda _: "txcript")

    def timeout(*args, **kwargs):
        assert kwargs["timeout"] == 120
        assert kwargs["stdin"] == subprocess.DEVNULL
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", timeout)
    with pytest.raises(TxcriptError, match="handoff interrupted"):
        continue_session(session_id="original", source_harness="cursor", target_harness="codex", cwd=tmp_path)


@pytest.mark.parametrize("typed,expected", [(b"/baton\r", "pick"), (b"\r", "resume"), (b"\x04", "exit")])
def test_idle_terminal_accepts_inflight_recovery(monkeypatch, typed, expected):
    import pty
    from baton.ptyctl import wait_for_input

    master, slave = pty.openpty()
    stop = threading.Event()
    ready = threading.Event()
    with os.fdopen(slave, "r") as stdin:
        monkeypatch.setattr(sys, "stdin", stdin)

        def pending():
            ready.set()
            return False

        def write():
            if ready.wait(2):
                os.write(master, typed)

        writer = threading.Thread(target=write)
        writer.start()
        timer = threading.Timer(2, stop.set)
        timer.start()
        try:
            assert wait_for_input(stop, pending) == expected
        finally:
            timer.cancel()
            writer.join(timeout=2)
            os.close(master)


def test_escape_key_does_not_wait_for_another_key(monkeypatch):
    import pty
    import tty
    from baton.picker import _read_key

    master, slave = pty.openpty()
    with os.fdopen(slave, "r") as stdin:
        monkeypatch.setattr(sys, "stdin", stdin)
        tty.setcbreak(slave)
        os.write(master, b"\x1b")
        start = time.monotonic()
        try:
            assert _read_key() == "esc"
            assert time.monotonic() - start < 1
        finally:
            os.close(master)


def test_terminal_switch_failure_recovers_without_reattach(monkeypatch, tmp_path):
    """Run the real supervisor, picker, PTY pump and bus against local fake CLIs."""
    import pty
    import select
    from baton.bus import send_request, socket_path

    stub = tmp_path / "fake-cli"
    stub.write_text(f"#!{sys.executable}\n" + '''
import pathlib, sys
model = sys.argv[sys.argv.index('--model') + 1]
flag = pathlib.Path(__file__).with_name('failed-once')
if model == 'gpt-test' and not flag.exists():
    flag.touch()
    sys.exit(1)
print('READY ' + model, flush=True)
for line in sys.stdin:
    if line.strip() == '/exit':
        break
''')
    stub.chmod(0o755)
    driver = tmp_path / "driver.py"
    driver.write_text('''
import sys
from pathlib import Path
from types import SimpleNamespace
from baton.catalog import make_model
from baton.clis import CliRecord
from baton.config import Config
import baton.sidecar
import baton.supervisor

models = [make_model('cursor', 'composer-test'), make_model('codex', 'gpt-test')]
cfg = Config(clis={h: CliRecord(h, ('fake',), True, sys.argv[1]) for h in ('cursor', 'codex')})
baton.sidecar.load_config = lambda: cfg
baton.sidecar.collect_catalog = lambda *a, **kw: (models, [])
baton.supervisor.continue_session = lambda **kw: SimpleNamespace(session_id='converted-thread')
baton.supervisor.offer_user_skill_links = lambda _: None
sup = baton.supervisor.Supervisor(cwd=Path.cwd(), thread_id='test', model=models[0], session_id='source-thread', cfg=cfg, pane_id='terminal')
raise SystemExit(sup.run())
''')
    with tempfile.TemporaryDirectory(prefix="bt-", dir="/tmp") as home:
        monkeypatch.setenv("BATON_HOME", home)
        env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]), NO_COLOR="1")
        master, slave = pty.openpty()
        proc = subprocess.Popen([sys.executable, str(driver), str(stub)], cwd=tmp_path,
                                stdin=slave, stdout=slave, stderr=slave, env=env, start_new_session=True)
        os.close(slave)
        output = bytearray()

        def expect(needle):
            deadline = time.monotonic() + 8
            while needle not in output and time.monotonic() < deadline:
                if select.select([master], [], [], 0.1)[0]:
                    try:
                        chunk = os.read(master, 65536)
                    except OSError:
                        break
                    output.extend(chunk)
                if proc.poll() is not None:
                    break
            assert needle in output, output.decode(errors="replace")
            output.clear()

        try:
            expect(b"READY composer-test")
            os.write(master, b"/baton\r")
            expect(b"gpt-test")
            os.write(master, b"\r")
            expect(b"READY composer-test")  # Failed Codex startup rolled back.
            assert proc.poll() is None
            os.write(master, b"/baton\r")
            expect(b"gpt-test")
            os.write(master, b"\r")
            expect(b"READY gpt-test")
            socket_path("terminal").unlink()
            assert send_request("terminal", {"op": "pick"}, timeout=2)["ok"]
            expect(b"enter to switch")
            os.write(master, b"\x1b")
            expect(b"READY gpt-test")  # Escape alone cancels and resumes.
            os.write(master, b"/exit\r")
            expect(b"CLI stopped.")
            os.write(master, b"/baton\r")
            expect(b"enter to switch")  # Still interactive after normal exit.
            os.write(master, b"q")
            expect(b"READY gpt-test")
            assert send_request("terminal", {"op": "detach"}, timeout=2)["ok"]
            assert proc.wait(timeout=5) == 0
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=5)
            os.close(master)
