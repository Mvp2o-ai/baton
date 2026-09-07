from __future__ import annotations

import sys

from homeswitch.bus import send_request
from homeswitch.catalog import get_model
from homeswitch.config import load_config
from homeswitch.panes import list_panes


def default_pane_id() -> str:
    panes = list_panes()
    if len(panes) == 1:
        return panes[0].pane_id
    if not panes:
        raise RuntimeError("no attached panes. run `homeswitch attach` in the project terminal.")
    ids = ", ".join(p.pane_id for p in panes)
    raise RuntimeError(f"multiple panes attached ({ids}). pass --pane <id>.")


def set_model(
    model_id: str,
    pane_id: str | None = None,
    span: str | None = None,
) -> dict:
    cfg = load_config()
    get_model(cfg.models, model_id)
    pid = pane_id or default_pane_id()
    payload: dict = {"op": "set_model", "model": model_id}
    if span:
        payload["range"] = span
    resp = send_request(pid, payload, timeout=8.0)
    if not resp.get("ok"):
        raise RuntimeError(resp.get("error") or "set_model failed")
    return resp


def sidecar_loop() -> int:
    cfg = load_config()
    print("homeswitch sidecar — type a model id, ls, status, or q")
    print("models: " + ", ".join(f"{m.id} ({m.harness})" for m in cfg.models))
    while True:
        panes = list_panes()
        if panes:
            print()
            for pane in panes:
                print(
                    f"  {pane.pane_id}  {pane.thread_id}  {pane.model_id} @ {pane.harness}"
                    f"  {'idle' if pane.idle else 'live'}"
                )
        else:
            print("\n  (no attached panes)")
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not line:
            continue
        if line in {"q", "quit", "exit"}:
            return 0
        if line in {"ls", "list"}:
            continue
        if line.startswith("status"):
            parts = line.split()
            try:
                pid = parts[1] if len(parts) > 1 else default_pane_id()
                print(send_request(pid, {"op": "status"}))
            except Exception as exc:  # noqa: BLE001
                print(f"error: {exc}", file=sys.stderr)
            continue
        model_id = line.split()[0]
        try:
            get_model(cfg.models, model_id)
            resp = set_model(model_id)
            print(f"queued {model_id} → pane {resp.get('pane_id') or default_pane_id()}")
        except Exception as exc:  # noqa: BLE001
            print(f"error: {exc}", file=sys.stderr)
