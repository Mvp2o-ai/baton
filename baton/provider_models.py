"""Load the model lineup each home CLI actually offers.

Each harness is limited to its home families — never the other products' models.

Cursor: ``agent models``, then Composer + Grok flavors only.
Codex: union of ``codex debug models --bundled`` and the live catalog.
The live endpoint is entitlement-thinned; bundled is the CLI's full lineup.
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
from baton.dirs import claude_config_dir, codex_home


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
    # Bundled first: the CLI still accepts these via --model.
    # Live second: overlays account-specific slugs / display names.
    # Using live alone drops most of the shipped lineup (remote catalog is
    # an entitlement snapshot, not a merge).
    catalogs: list[dict] = []
    bundled = _run_json(rec.bin, ["debug", "models", "--bundled"], timeout=8)
    if bundled:
        catalogs.append(bundled)
    live = _run_json(rec.bin, ["debug", "models"], timeout=12)
    if live:
        catalogs.append(live)
    if not catalogs:
        cache = _read_codex_models_cache()
        if cache:
            catalogs.append(cache)
    if not catalogs:
        raise CatalogError("codex debug models returned no JSON")
    return merge_codex_catalogs(catalogs)


def fetch_cursor(rec: CliRecord) -> list[Model]:
    if not rec.bin:
        raise CatalogError("agent binary missing")
    proc = _run(rec.bin, ["models"], timeout=20)
    if proc.returncode != 0:
        raise CatalogError((proc.stderr or proc.stdout or "agent models failed").strip()[:300])
    rows = cursor_home_models(parse_agent_models(proc.stdout or ""))
    if not rows:
        raise CatalogError("agent models had no Composer/Grok rows")
    return rows


def parse_codex_catalog(raw: dict) -> list[Model]:
    return merge_codex_catalogs([raw])


def merge_codex_catalogs(catalogs: list[dict]) -> list[Model]:
    """Union catalogs by slug. Later catalogs overlay earlier ones.

    ``visibility: none`` is hidden from picker and APIs — skip those.
    ``hide`` is TUI-only; ``codex --model <slug>`` still works, so keep them.
    """
    ranked: dict[str, tuple[int, Model]] = {}
    saw_models_key = False
    for raw in catalogs:
        items = raw.get("models")
        if not isinstance(items, list):
            continue
        saw_models_key = True
        for item in items:
            parsed = _codex_item(item)
            if parsed is None:
                continue
            slug, priority, model = parsed
            ranked[slug] = (priority, model)
    if not saw_models_key:
        raise CatalogError("codex catalog missing models[]")
    if not ranked:
        raise CatalogError("codex catalog had no listed models")
    rows = [(priority, slug, model) for slug, (priority, model) in ranked.items()]
    rows.sort(key=lambda row: (row[0], row[1]))
    return [model for _, _, model in rows]


def _codex_item(item: object) -> tuple[str, int, Model] | None:
    if not isinstance(item, dict):
        return None
    vis = str(item.get("visibility") or "list").strip().lower()
    if vis == "none":
        return None
    slug = str(item.get("slug") or "").strip()
    if not slug:
        return None
    label = str(item.get("display_name") or slug)
    try:
        priority = int(item.get("priority") if item.get("priority") is not None else 99)
    except (TypeError, ValueError):
        priority = 99
    return slug, priority, make_model(HARNESS_CODEX, slug, label)


# Cursor's home families. ``agent models`` also lists GPT/Claude/etc.; those
# belong to Codex and Claude Code, not this harness.
CURSOR_HOME_FAMILIES = ("composer", "grok")


def is_cursor_home_model(slug: str) -> bool:
    for token in slug.lower().replace("_", "-").split("-"):
        if token.startswith(CURSOR_HOME_FAMILIES):
            return True
    return False


def cursor_home_models(rows: list[Model]) -> list[Model]:
    return [row for row in rows if is_cursor_home_model(row.provider_model)]


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


def _read_codex_models_cache() -> dict | None:
    path = codex_home() / "models_cache.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


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
