from __future__ import annotations

from pathlib import Path

from baton.bus import send_request
from baton.catalog import Model, resolve
from baton.config import load_config
from baton.panes import list_panes, panes_for_cwd
from baton.picker import pick
from baton.provider_models import collect_catalog
from baton.style import err, ok

_ATTACH_HOWTO = (
    "In a project terminal run `baton claude`, `baton codex`, or `baton agent`, "
    "then type /baton in that same terminal. An IDE chat tab is not an attach pane."
)


def default_pane_id(cwd: Path | None = None) -> str:
    panes = list_panes()
    if not panes:
        raise RuntimeError(f"Nothing is attached.\n{_ATTACH_HOWTO}")
    here = (cwd or Path.cwd()).resolve()
    local = panes_for_cwd(here, panes)
    if len(local) == 1:
        return local[0].pane_id
    if len(local) > 1:
        ids = ", ".join(p.pane_id for p in local)
        raise RuntimeError(
            f"This directory has more than one attach ({ids}).\n"
            f"From another terminal: baton detach --pane <id>"
        )
    if len(panes) == 1:
        return panes[0].pane_id
    live = "\n".join(f"  {p.pane_id}  {p.thread_id}  {p.cwd}" for p in panes)
    raise RuntimeError(
        f"This directory is not attached ({here}).\n"
        f"{_ATTACH_HOWTO}\n"
        f"Live panes in other projects:\n{live}"
    )


def request_pick(pane_id: str | None = None) -> dict:
    pid = pane_id or default_pane_id()
    resp = send_request(pid, {"op": "pick"}, timeout=3.0)
    if not resp.get("ok"):
        raise RuntimeError(resp.get("error") or "pick failed")
    return resp


def choose_model(*, status_lines: list[str] | None = None) -> Model | None:
    cfg = load_config()
    while True:
        models, errors = collect_catalog(cfg.clis)
        result = pick(models, errors=errors, status_lines=status_lines)
        if result.quit:
            return None
        if result.refresh or result.model is None:
            continue
        return result.model


def set_model(
    model: Model | str,
    pane_id: str | None = None,
    span: str | None = None,
    catalog: list[Model] | None = None,
) -> dict:
    if isinstance(model, str):
        if catalog is None:
            cfg = load_config()
            catalog, errors = collect_catalog(cfg.clis)
            if errors and not catalog:
                raise RuntimeError("; ".join(errors))
        model = resolve(catalog, model)
    pid = pane_id or default_pane_id()
    payload: dict = {
        "op": "set_model",
        "model": model.key,
        "harness": model.harness,
        "provider_model": model.provider_model,
        "label": model.label,
    }
    if span:
        payload["range"] = span
    resp = send_request(pid, payload, timeout=8.0)
    if not resp.get("ok"):
        raise RuntimeError(resp.get("error") or "set_model failed")
    return resp


def set_loop() -> int:
    cfg = load_config()
    while True:
        models, errors = collect_catalog(cfg.clis)
        status = _status_lines()
        result = pick(models, errors=errors, status_lines=status)
        if result.quit:
            return 0
        if result.refresh or result.model is None:
            continue
        try:
            resp = set_model(result.model)
            print(
                ok(
                    f"queued {result.model.display_label()} → {result.model.harness}  "
                    f"pane {resp.get('pane_id') or default_pane_id()}"
                )
            )
        except Exception as exc:  # noqa: BLE001
            print(err(f"error: {exc}", stream=sys.stderr), file=sys.stderr)


def _status_lines() -> list[str]:
    panes = list_panes()
    if not panes:
        return ["(no attached panes — run `baton attach` in the project terminal)"]
    return [
        f"{p.pane_id}  {p.thread_id}  {p.model_id} @ {p.harness}  "
        f"{'idle' if p.idle else 'live'}"
        for p in panes
    ]
