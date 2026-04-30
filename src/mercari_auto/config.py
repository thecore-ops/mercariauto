"""Load and validate config.yaml."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class ScheduleConfig:
    interval_days: int
    step_yen: int


@dataclass(frozen=True)
class PricingConfig:
    floor_ratio: float
    mercari_min_price: int


@dataclass(frozen=True)
class NotifyConfig:
    enabled: bool
    gmail_user: str
    gmail_app_password: str
    to: str


@dataclass(frozen=True)
class BrowserConfig:
    headless: bool
    storage_state_path: str
    action_delay_min: float
    action_delay_max: float
    per_item_delay_min: float
    per_item_delay_max: float


@dataclass(frozen=True)
class PathsConfig:
    state_db: str
    log_dir: str


@dataclass(frozen=True)
class Config:
    schedule: ScheduleConfig
    pricing: PricingConfig
    notify: NotifyConfig
    browser: BrowserConfig
    paths: PathsConfig


def load_config(path: str | Path = "config.yaml") -> Config:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(
            f"{p} not found. Copy config.example.yaml to config.yaml and edit it."
        )
    with p.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    return Config(
        schedule=ScheduleConfig(**raw["schedule"]),
        pricing=PricingConfig(**raw["pricing"]),
        notify=NotifyConfig(**raw["notify"]),
        browser=BrowserConfig(**raw["browser"]),
        paths=PathsConfig(**raw["paths"]),
    )
