"""SQLite state for tracking listings and run history."""
from __future__ import annotations

import math
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Iterator


SCHEMA = """
CREATE TABLE IF NOT EXISTS listings (
    item_id TEXT PRIMARY KEY,
    title TEXT,
    original_price INTEGER NOT NULL,
    current_price INTEGER NOT NULL,
    floor_price INTEGER NOT NULL,
    last_lowered_at TEXT,
    last_seen_at TEXT NOT NULL,
    status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS run_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ran_at TEXT NOT NULL,
    item_id TEXT NOT NULL,
    title TEXT,
    before_price INTEGER,
    after_price INTEGER,
    result TEXT NOT NULL,
    message TEXT
);

CREATE INDEX IF NOT EXISTS idx_run_log_ran_at ON run_log(ran_at);
"""


@dataclass
class Listing:
    item_id: str
    title: str
    original_price: int
    current_price: int
    floor_price: int
    last_lowered_at: str | None
    last_seen_at: str
    status: str


@dataclass
class RunLogEntry:
    ran_at: str
    item_id: str
    title: str | None
    before_price: int | None
    after_price: int | None
    result: str
    message: str | None


def compute_floor(original_price: int, floor_ratio: float, mercari_min: int) -> int:
    return max(math.floor(original_price * floor_ratio), mercari_min)


class StateDB:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "StateDB":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        try:
            yield self._conn
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    def upsert_observed(
        self,
        item_id: str,
        title: str,
        observed_price: int,
        floor_ratio: float,
        mercari_min: int,
        now_iso: str,
    ) -> Listing:
        """Record an observed listing.

        On first observation, original_price is set to the observed price and
        floor_price is computed. On subsequent observations, only current_price,
        last_seen_at and status are refreshed.
        """
        existing = self.get(item_id)
        with self._tx() as conn:
            if existing is None:
                floor_price = compute_floor(observed_price, floor_ratio, mercari_min)
                conn.execute(
                    """
                    INSERT INTO listings (item_id, title, original_price, current_price,
                                          floor_price, last_lowered_at, last_seen_at, status)
                    VALUES (?, ?, ?, ?, ?, NULL, ?, 'on_sale')
                    """,
                    (item_id, title, observed_price, observed_price, floor_price, now_iso),
                )
            else:
                conn.execute(
                    """
                    UPDATE listings
                    SET title = ?, current_price = ?, last_seen_at = ?, status = 'on_sale'
                    WHERE item_id = ?
                    """,
                    (title, observed_price, now_iso, item_id),
                )
        result = self.get(item_id)
        assert result is not None
        return result

    def get(self, item_id: str) -> Listing | None:
        row = self._conn.execute(
            "SELECT * FROM listings WHERE item_id = ?", (item_id,)
        ).fetchone()
        return _row_to_listing(row) if row else None

    def all_active(self) -> list[Listing]:
        rows = self._conn.execute(
            "SELECT * FROM listings WHERE status = 'on_sale'"
        ).fetchall()
        return [_row_to_listing(r) for r in rows]

    def mark_lowered(self, item_id: str, new_price: int, now_iso: str) -> None:
        with self._tx() as conn:
            conn.execute(
                "UPDATE listings SET current_price = ?, last_lowered_at = ? WHERE item_id = ?",
                (new_price, now_iso, item_id),
            )

    def mark_missing(self, item_ids_seen: Iterable[str], now_iso: str) -> list[str]:
        """Mark listings that were not in the observed set as 'gone'.

        Returns the list of item_ids whose status changed to 'gone'.
        """
        seen = set(item_ids_seen)
        rows = self._conn.execute(
            "SELECT item_id FROM listings WHERE status = 'on_sale'"
        ).fetchall()
        gone: list[str] = []
        with self._tx() as conn:
            for r in rows:
                if r["item_id"] not in seen:
                    conn.execute(
                        "UPDATE listings SET status = 'gone', last_seen_at = ? WHERE item_id = ?",
                        (now_iso, r["item_id"]),
                    )
                    gone.append(r["item_id"])
        return gone

    def log_run(
        self,
        ran_at: str,
        item_id: str,
        title: str | None,
        before_price: int | None,
        after_price: int | None,
        result: str,
        message: str | None = None,
    ) -> None:
        with self._tx() as conn:
            conn.execute(
                """
                INSERT INTO run_log (ran_at, item_id, title, before_price, after_price, result, message)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (ran_at, item_id, title, before_price, after_price, result, message),
            )

    def recent_run_log(self, since_iso: str) -> list[RunLogEntry]:
        rows = self._conn.execute(
            "SELECT * FROM run_log WHERE ran_at >= ? ORDER BY id ASC", (since_iso,)
        ).fetchall()
        return [
            RunLogEntry(
                ran_at=r["ran_at"],
                item_id=r["item_id"],
                title=r["title"],
                before_price=r["before_price"],
                after_price=r["after_price"],
                result=r["result"],
                message=r["message"],
            )
            for r in rows
        ]


def _row_to_listing(row: sqlite3.Row) -> Listing:
    return Listing(
        item_id=row["item_id"],
        title=row["title"],
        original_price=row["original_price"],
        current_price=row["current_price"],
        floor_price=row["floor_price"],
        last_lowered_at=row["last_lowered_at"],
        last_seen_at=row["last_seen_at"],
        status=row["status"],
    )


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")
