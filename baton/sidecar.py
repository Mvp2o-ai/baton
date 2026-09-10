from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from baton.bus import send_request
from baton.catalog import Model, resolve
from baton.config import load_config
from baton.dirs import agents_home, claude_config_dir, codex_home, cursor_user_home
from baton.panes import list_panes, panes_for_cwds, panes_for_transcript
from baton.paths import home_dir
from baton.picker import pick
from baton.provider_models import collect_catalog
from baton.style import err, ok

_ATTACH_HOWTO = (
    "In a project terminal run `baton claude`, `baton codex`, or `baton agent`, "
    "then type /baton in that same terminal or in an IDE chat for that project."
)


def default_pane_id(
    cwd: Path | str | Sequence[Path | str] | None = None,
    *,
    transcript_path: str | None = None,
) -> str:
    panes = list_panes()
    if not panes:
        raise RuntimeError(f"Nothing is attached.\n{_ATTACH_HOWTO}")
    candidates = _as_cwds(cwd)
    local = panes_for_cwds(candidates, panes)
    if not local and transcript_path:
        local = panes_for_transcript(transcript_path, panes)
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
    here = _described_cwd(candidates)
    live = "\n".join(f"  {p.pane_id}  {p.thread_id}  {p.cwd}" for p in panes)
    raise RuntimeError(
        f"This directory is not attached ({here}).\n"
        f"{_ATTACH_HOWTO}\n"
        f"Live panes in other projects:\n{live}"
    )


def request_pick(
    pane_id: str | None = None,
    cwd: Path | str | Sequence[Path | str] | None = None,
    transcript_path: str | None = None,
) -> dict:
    pid = pane_id or default_pane_id(cwd, transcript_path=transcript_path)
    resp = send_request(pid, {"op": "pick"}, timeout=3.0)
    if not resp.get("ok"):
        raise RuntimeError(resp.get("error") or "pick failed")
    return resp


def _as_cwds(cwd: Path | str | Sequence[Path | str] | None) -> list[Path]:
    if cwd is None:
        return [Path.cwd().resolve()]
    if isinstance(cwd, (str, Path)):
        return [Path(cwd).expanduser().resolve()]
    out = [Path(item).expanduser().resolve() for item in cwd]
    return out or [Path.cwd().resolve()]


def _described_cwd(candidates: list[Path]) -> Path:
    for path in candidates:
        if not _is_tooling_home(path):
            return path
    return candidates[0] if candidates else Path.cwd().resolve()


def _is_tooling_home(path: Path) -> bool:
    path = path.resolve()
    homes = (
        cursor_user_home(),
        claude_config_dir(),
        codex_home(),
        agents_home(),
        home_dir(),
    )
    for home in homes:
        root = home.resolve()
        if path == root or root in path.parents:
            return True
    return False


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
