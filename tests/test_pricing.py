from datetime import datetime, timedelta, timezone

import pytest

from mercari_auto.pricing import decide_new_price


JST = timezone(timedelta(hours=9))


def iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def test_first_run_lowers_by_step():
    now = datetime(2026, 4, 30, 10, 0, tzinfo=JST)
    d = decide_new_price(
        current_price=1500,
        floor_price=700,
        last_lowered_at=None,
        step_yen=100,
        interval_days=3,
        mercari_min_price=300,
        now=now,
    )
    assert d.reason == "lowered"
    assert d.new_price == 1400


def test_within_interval_skipped():
    now = datetime(2026, 4, 30, 10, 0, tzinfo=JST)
    last = now - timedelta(days=2)
    d = decide_new_price(
        current_price=1500,
        floor_price=700,
        last_lowered_at=iso(last),
        step_yen=100,
        interval_days=3,
        mercari_min_price=300,
        now=now,
    )
    assert d.reason == "skipped_recent"
    assert d.new_price is None


def test_exactly_interval_lowers():
    now = datetime(2026, 4, 30, 10, 0, tzinfo=JST)
    last = now - timedelta(days=3)
    d = decide_new_price(
        current_price=1500,
        floor_price=700,
        last_lowered_at=iso(last),
        step_yen=100,
        interval_days=3,
        mercari_min_price=300,
        now=now,
    )
    assert d.reason == "lowered"
    assert d.new_price == 1400


def test_at_floor_skipped():
    now = datetime(2026, 4, 30, 10, 0, tzinfo=JST)
    d = decide_new_price(
        current_price=700,
        floor_price=700,
        last_lowered_at=None,
        step_yen=100,
        interval_days=3,
        mercari_min_price=300,
        now=now,
    )
    assert d.reason == "skipped_floor"
    assert d.new_price is None


def test_step_clamped_to_floor():
    now = datetime(2026, 4, 30, 10, 0, tzinfo=JST)
    d = decide_new_price(
        current_price=750,
        floor_price=700,
        last_lowered_at=None,
        step_yen=100,
        interval_days=3,
        mercari_min_price=300,
        now=now,
    )
    assert d.reason == "lowered"
    assert d.new_price == 700


def test_step_clamped_to_mercari_min():
    now = datetime(2026, 4, 30, 10, 0, tzinfo=JST)
    d = decide_new_price(
        current_price=350,
        floor_price=200,  # below mercari_min, should be ignored
        last_lowered_at=None,
        step_yen=100,
        interval_days=3,
        mercari_min_price=300,
        now=now,
    )
    assert d.reason == "lowered"
    assert d.new_price == 300


def test_below_min_skipped():
    now = datetime(2026, 4, 30, 10, 0, tzinfo=JST)
    d = decide_new_price(
        current_price=300,
        floor_price=200,
        last_lowered_at=None,
        step_yen=100,
        interval_days=3,
        mercari_min_price=300,
        now=now,
    )
    assert d.reason == "skipped_floor"


def test_naive_iso_timestamp_handled():
    now = datetime(2026, 4, 30, 10, 0, tzinfo=JST)
    last_naive = (now - timedelta(days=2)).replace(tzinfo=None)
    d = decide_new_price(
        current_price=1500,
        floor_price=700,
        last_lowered_at=last_naive.isoformat(timespec="seconds"),
        step_yen=100,
        interval_days=3,
        mercari_min_price=300,
        now=now,
    )
    assert d.reason == "skipped_recent"
