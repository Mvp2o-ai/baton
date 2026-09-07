from __future__ import annotations

from dataclasses import dataclass


HARNESS_CLAUDE = "claude_code"
HARNESS_CODEX = "codex"
HARNESS_CURSOR = "cursor"

SUPPORTED_HARNESSES = (HARNESS_CLAUDE, HARNESS_CODEX, HARNESS_CURSOR)


@dataclass(frozen=True)
class Model:
    """One row in the shared catalog: a picker id plus its home CLI harness."""

    id: str
    provider_model: str
    harness: str
    label: str = ""

    def display_label(self) -> str:
        return self.label or self.id


DEFAULT_MODELS: tuple[Model, ...] = (
    Model("opus", "claude-opus-4-1", HARNESS_CLAUDE, "Opus"),
    Model("sonnet", "claude-sonnet-4-5", HARNESS_CLAUDE, "Sonnet"),
    Model("haiku", "claude-haiku-4-5", HARNESS_CLAUDE, "Haiku"),
    Model("gpt", "gpt-5", HARNESS_CODEX, "GPT"),
    Model("codex", "gpt-5-codex", HARNESS_CODEX, "Codex"),
    Model("composer", "composer-2.5", HARNESS_CURSOR, "Composer"),
)


def models_from_dicts(rows: list[dict] | None) -> list[Model]:
    if not rows:
        return list(DEFAULT_MODELS)
    out: list[Model] = []
    for row in rows:
        harness = str(row["harness"])
        if harness not in SUPPORTED_HARNESSES:
            raise ValueError(f"unsupported harness {harness!r} for model {row.get('id')}")
        out.append(
            Model(
                id=str(row["id"]),
                provider_model=str(row["provider_model"]),
                harness=harness,
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


def get_model(models: list[Model], model_id: str) -> Model:
    needle = model_id.strip().lower()
    for model in models:
        if model.id.lower() == needle:
            return model
    known = ", ".join(m.id for m in models)
    raise KeyError(f"unknown model {model_id!r}. catalog: {known}")
