"""Load the model lineup each home CLI actually offers.

Cursor: ``agent models`` (official).
Codex: ``codex debug models`` JSON catalog (official).
Claude Code: documented ``/model`` aliases plus user ``settings.json``
``availableModels`` / ``modelPicker`` — there is no non-interactive list command.
"""

from __future__ import annotations

import json
import subprocess

from baton.catalog import (
    CLAUDE_BUILT_IN,
    HARNESS_CLAUDE,
    HARNESS_CODEX,
    HARNESS_CURSOR,
    Model,
    make_model,
)
from baton.clis import CliRecord
from baton.dirs import claude_config_dir


class CatalogError(RuntimeError):
    pass


def collect_catalog(clis: dict[str, CliRecord]) -> tuple[list[Model], list[str]]:
    """Return (models, per-harness error strings). Enabled CLIs only."""
    models: list[Model] = []
    errors: list[str] = []
    for harness, rec in clis.items():
        if not rec.enabled or not rec.found:
            continue
        try:
            models.extend(fetch_harness(rec))
        except (CatalogError, OSError, subprocess.TimeoutExpired) as exc:
            errors.append(f"{harness}: {exc}")
    return models, errors


def fetch_harness(rec: CliRecord) -> list[Model]:
    if rec.harness == HARNESS_CLAUDE:
        return fetch_claude(rec)
    if rec.harness == HARNESS_CODEX:
        return fetch_codex(rec)
    if rec.harness == HARNESS_CURSOR:
        return fetch_cursor(rec)
    raise CatalogError(f"unsupported harness {rec.harness}")


def fetch_claude(_rec: CliRecord | None = None) -> list[Model]:
    settings = _read_claude_user_settings()
    allow = _available_models(settings)
    picker = settings.get("modelPicker") if isinstance(settings.get("modelPicker"), dict) else {}
    extra_rows = picker.get("options") if isinstance(picker, dict) else None
    replace = bool(picker.get("replaceBuiltInOptions")) if isinstance(picker, dict) else False

    built = list(CLAUDE_BUILT_IN)
    if replace and extra_rows:
        built = []
    out: list[Model] = []
    seen: set[str] = set()
    for model in built:
        if allow is not None and not _allow_claude(model.provider_model, allow):
            continue
        out.append(model)
        seen.add(model.provider_model.lower())
    if isinstance(extra_rows, list):
        for row in extra_rows:
            if not isinstance(row, dict):
                continue
            provider = str(row.get("model") or "").strip()
            if not provider or provider.lower() in seen:
                continue
            if allow is not None and not _allow_claude(provider, allow):
                continue
            label = str(row.get("label") or provider)
            out.append(make_model(HARNESS_CLAUDE, provider, label))
            seen.add(provider.lower())
    return out


def fetch_codex(rec: CliRecord) -> list[Model]:
    if not rec.bin:
        raise CatalogError("codex binary missing")
    raw = _run_json(rec.bin, ["debug", "models"], timeout=12)
    if raw is None:
        raw = _run_json(rec.bin, ["debug", "models", "--bundled"], timeout=8)
    if raw is None:
        raise CatalogError("codex debug models returned no JSON")
    return parse_codex_catalog(raw)


def fetch_cursor(rec: CliRecord) -> list[Model]:
    if not rec.bin:
        raise CatalogError("agent binary missing")
    proc = _run(rec.bin, ["models"], timeout=20)
    if proc.returncode != 0:
        raise CatalogError((proc.stderr or proc.stdout or "agent models failed").strip()[:300])
    rows = parse_agent_models(proc.stdout or "")
    if not rows:
        raise CatalogError("agent models printed no rows")
    return rows


def parse_codex_catalog(raw: dict) -> list[Model]:
    items = raw.get("models")
    if not isinstance(items, list):
        raise CatalogError("codex catalog missing models[]")
    out: list[Model] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if str(item.get("visibility") or "list") != "list":
            continue
        slug = str(item.get("slug") or "").strip()
        if not slug:
            continue
        label = str(item.get("display_name") or slug)
        out.append(make_model(HARNESS_CODEX, slug, label))
    if not out:
        raise CatalogError("codex catalog had no listed models")
    return out


def parse_agent_models(text: str) -> list[Model]:
    out: list[Model] = []
    seen: set[str] = set()
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.lower().startswith("available model"):
            continue
        if " - " not in stripped:
            continue
        slug, label = stripped.split(" - ", 1)
        slug = slug.strip()
        label = label.strip()
        if not slug or slug in seen:
            continue
        seen.add(slug)
        out.append(make_model(HARNESS_CURSOR, slug, label))
    return out


def _read_claude_user_settings() -> dict:
    path = claude_config_dir() / "settings.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _available_models(settings: dict) -> list[str] | None:
    raw = settings.get("availableModels")
    if not isinstance(raw, list) or not raw:
        return None
    return [str(item) for item in raw if isinstance(item, str) and item.strip()]


def _allow_claude(model: str, allow: list[str]) -> bool:
    needle = model.lower()
    for entry in allow:
        token = entry.lower()
        if needle == token or needle.startswith(token) or token.startswith(needle):
            return True
    return False


def _run(bin_path: str, args: list[str], *, timeout: float) -> subprocess.CompletedProcess:
    return subprocess.run(
        [bin_path, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _run_json(bin_path: str, args: list[str], *, timeout: float) -> dict | None:
    proc = _run(bin_path, args, timeout=timeout)
    blob = (proc.stdout or "").strip()
    if proc.returncode != 0 or not blob:
        return None
    try:
        data = json.loads(blob)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None
