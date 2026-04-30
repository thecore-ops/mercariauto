"""Decide whether and how to lower the price for a listing."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class PriceDecision:
    new_price: int | None  # None => do not change
    reason: str            # "lowered" / "skipped_recent" / "skipped_floor" / "skipped_no_change"


def decide_new_price(
    current_price: int,
    floor_price: int,
    last_lowered_at: str | None,
    step_yen: int,
    interval_days: int,
    mercari_min_price: int,
    now: datetime,
) -> PriceDecision:
    """Pure function: figure out what the next price should be.

    Rules:
    - If `last_lowered_at` is within `interval_days` of `now` -> skipped_recent.
    - If already at floor (or below) -> skipped_floor.
    - Candidate = current_price - step_yen, clamped up to max(floor_price, mercari_min_price).
    - If candidate == current_price -> skipped_no_change.
    - Otherwise -> lower to candidate.
    """
    floor = max(floor_price, mercari_min_price)

    if current_price <= floor:
        return PriceDecision(new_price=None, reason="skipped_floor")

    if last_lowered_at is not None:
        last = datetime.fromisoformat(last_lowered_at)
        if last.tzinfo is None:
            last = last.astimezone()
        if now - last < timedelta(days=interval_days):
            return PriceDecision(new_price=None, reason="skipped_recent")

    candidate = max(current_price - step_yen, floor)
    if candidate >= current_price:
        return PriceDecision(new_price=None, reason="skipped_no_change")

    return PriceDecision(new_price=candidate, reason="lowered")
