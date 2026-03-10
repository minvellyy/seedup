from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import yaml

@dataclass(frozen=True)
class BaseConfig:
    horizons: list[int]
    seed: int

def load_config(path: str = "configs/base.yaml") -> BaseConfig:
    with open(path, "r", encoding="utf-8") as f:
        d = yaml.safe_load(f)

    return BaseConfig(
        horizons=d["run"]["horizons"],
        seed=d["run"]["seed"],
    )

def load_yaml(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)