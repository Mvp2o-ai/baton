from __future__ import annotations

import re
from dataclasses import dataclass


HARNESS_CLAUDE = "claude_code"
HARNESS_CODEX = "codex"
HARNESS_CURSOR = "cursor"

SUPPORTED_HARNESSES = (HARNESS_CLAUDE, HARNESS_CODEX, HARNESS_CURSOR)

# CLI names that skip the starting picker and land on that home.
HOME_COMMANDS = {
    "claude": HARNESS_CLAUDE,
    "claude_code": HARNESS_CLAUDE,
    "codex": HARNESS_CODEX,
    "agent": HARNESS_CURSOR,
    "cursor": HARNESS_CURSOR,
    "agentx": HARNESS_CURSOR,
}

HARNESS_LABELS = {
    HARNESS_CLAUDE: "Claude Code",
    HARNESS_CODEX: "Codex",
    HARNESS_CURSOR: "Cursor CLI",
}


@dataclass(frozen=True)
class Model:
    """One picker row: the home CLI plus the id that CLI's ``--model`` accepts."""

    id: str
    provider_model: str
    harness: str
    label: str = ""

    def display_label(self) -> str:
        return self.label or self.provider_model or self.id

    @property
    def key(self) -> str:
        return f"{self.harness}:{self.provider_model}"


# Claude Code has no non-interactive list command. Aliases track the current
# family; versioned IDs pin recent snapshots (about three months). Older 4.x
# IDs stay off the picker — ``--model`` still accepts them if typed.
CLAUDE_BUILT_IN: tuple[Model, ...] = (
    Model("claude_code:opus", "opus", HARNESS_CLAUDE, "Opus"),
    Model("claude_code:sonnet", "sonnet", HARNESS_CLAUDE, "Sonnet"),
    Model("claude_code:haiku", "haiku", HARNESS_CLAUDE, "Haiku"),
    Model("claude_code:fable", "fable", HARNESS_CLAUDE, "Fable"),
    Model("claude_code:best", "best", HARNESS_CLAUDE, "Best"),
    Model("claude_code:sonnet[1m]", "sonnet[1m]", HARNESS_CLAUDE, "Sonnet 1M"),
    Model("claude_code:opus[1m]", "opus[1m]", HARNESS_CLAUDE, "Opus 1M"),
    Model("claude_code:fable[1m]", "fable[1m]", HARNESS_CLAUDE, "Fable 1M"),
    Model("claude_code:opusplan", "opusplan", HARNESS_CLAUDE, "Opus plan"),
    Model("claude_code:claude-fable-5-1", "claude-fable-5-1", HARNESS_CLAUDE, "Fable 5.1"),
    Model("claude_code:claude-opus-5", "claude-opus-5", HARNESS_CLAUDE, "Opus 5"),
    Model("claude_code:claude-sonnet-5", "claude-sonnet-5", HARNESS_CLAUDE, "Sonnet 5"),
    Model("claude_code:claude-fable-5", "claude-fable-5", HARNESS_CLAUDE, "Fable 5"),
)

# Codex picker: GPT-5.6 and newer only. Older slugs still work via ``codex --model``.
CODEX_MIN_GPT = (5, 6)
_CODEX_GPT_VERSION = re.compile(r"^gpt-(\d+)(?:\.(\d+))?", re.IGNORECASE)


def is_listed_codex_slug(slug: str) -> bool:
    match = _CODEX_GPT_VERSION.match(slug.strip())
    if not match:
        return False
    major = int(match.group(1))
    minor = int(match.group(2) or 0)
    return (major, minor) >= CODEX_MIN_GPT


def make_model(harness: str, provider_model: str, label: str = "") -> Model:
    if harness not in SUPPORTED_HARNESSES:
        raise ValueError(f"unsupported harness {harness!r}")
    provider = str(provider_model).strip()
    if not provider:
        raise ValueError("empty provider model")
    return Model(
        id=f"{harness}:{provider}",
        provider_model=provider,
        harness=harness,
        label=str(label or ""),
    )


def models_from_dicts(rows: list[dict] | None) -> list[Model]:
    if not rows:
        return []
    out: list[Model] = []
    for row in rows:
        harness = str(row["harness"])
        provider = str(row.get("provider_model") or row.get("id") or "")
        out.append(
            make_model(
                harness,
                provider,
                label=str(row.get("label") or ""),
            )
        )
    return out


def models_to_dicts(models: list[Model]) -> list[dict]:
    return [
        {
            "id": m.id,
            "provider_model": m.provider_model,
            "harness": m.harness,
            "label": m.label,
        }
        for m in models
    ]


def resolve(models: list[Model], needle: str) -> Model:
    text = needle.strip()
    if not text:
        raise KeyError("empty model id")
    lower = text.lower()
    exact_key = [m for m in models if m.key.lower() == lower or m.id.lower() == lower]
    if len(exact_key) == 1:
        return exact_key[0]
    if len(exact_key) > 1:
        raise KeyError(f"ambiguous model {needle!r}")
    by_provider = [m for m in models if m.provider_model.lower() == lower]
    if len(by_provider) == 1:
        return by_provider[0]
    if len(by_provider) > 1:
        homes = ", ".join(m.key for m in by_provider)
        raise KeyError(f"ambiguous model {needle!r}. pick one of: {homes}")
    known = ", ".join(m.key for m in models[:12])
    more = "" if len(models) <= 12 else f" … +{len(models) - 12}"
    raise KeyError(f"unknown model {needle!r}. catalog: {known}{more}")


def get_model(models: list[Model], model_id: str) -> Model:
    return resolve(models, model_id)
