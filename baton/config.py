from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from baton.catalog import Model, models_from_dicts, models_to_dicts
from baton.clis import CliRecord, records_from_config, records_to_config
from baton.paths import config_path, ensure_dirs


@dataclass
class Config:
    clis: dict[str, CliRecord] = field(default_factory=dict)
    models: list[Model] = field(default_factory=list)
    txcript_bin: str = "txcript"

    def to_dict(self) -> dict[str, Any]:
        return {
            "txcript_bin": self.txcript_bin,
            "clis": records_to_config(self.clis),
            "models": models_to_dicts(self.models),
        }


def load_config(path: Path | None = None) -> Config:
    ensure_dirs()
    cfg_path = path or config_path()
    if not cfg_path.is_file():
        cfg = Config()
        cfg.clis = records_from_config({})
        cfg.models = models_from_dicts(None)
        save_config(cfg, cfg_path)
        return cfg
    raw = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg = Config(
        txcript_bin=str(raw.get("txcript_bin") or "txcript"),
        clis=records_from_config(raw),
        models=models_from_dicts(raw.get("models")),
    )
    return cfg


def save_config(cfg: Config, path: Path | None = None) -> Path:
    ensure_dirs()
    cfg_path = path or config_path()
    cfg_path.write_text(json.dumps(cfg.to_dict(), indent=2) + "\n", encoding="utf-8")
    return cfg_path
