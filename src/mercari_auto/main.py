"""Entrypoint: observe listings, lower prices that have aged past the interval, notify."""
from __future__ import annotations

import argparse
import asyncio
import logging
import random
import sys
from datetime import datetime
from pathlib import Path

from .config import Config, load_config
from .mercari import MercariClient
from .notifier import send_summary
from .pricing import decide_new_price
from .state import StateDB, now_iso


def _setup_logging(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"run-{datetime.now().strftime('%Y-%m-%d')}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(log_path, encoding="utf-8"), logging.StreamHandler(sys.stdout)],
    )


async def run(cfg: Config, dry_run: bool) -> int:
    log = logging.getLogger("mercari_auto")
    started_at = now_iso()
    state = StateDB(cfg.paths.state_db)

    try:
        async with MercariClient(cfg.browser, Path(cfg.paths.log_dir)) as client:
            log.info("Fetching active listings...")
            observed = await client.fetch_active_listings()
            log.info("Found %d active listings", len(observed))

            for ob in observed:
                state.upsert_observed(
                    item_id=ob.item_id,
                    title=ob.title,
                    observed_price=ob.price,
                    floor_ratio=cfg.pricing.floor_ratio,
                    mercari_min=cfg.pricing.mercari_min_price,
                    now_iso=started_at,
                )

            gone = state.mark_missing([o.item_id for o in observed], started_at)
            for gid in gone:
                log.info("Listing %s no longer active (sold/stopped)", gid)

            now_dt = datetime.fromisoformat(started_at)
            for ob in observed:
                listing = state.get(ob.item_id)
                assert listing is not None
                decision = decide_new_price(
                    current_price=listing.current_price,
                    floor_price=listing.floor_price,
                    last_lowered_at=listing.last_lowered_at,
                    step_yen=cfg.schedule.step_yen,
                    interval_days=cfg.schedule.interval_days,
                    mercari_min_price=cfg.pricing.mercari_min_price,
                    now=now_dt,
                )

                if decision.new_price is None:
                    log.info("Skip %s (%s): %s @%d円", ob.item_id, ob.title[:30], decision.reason, listing.current_price)
                    state.log_run(
                        ran_at=started_at,
                        item_id=ob.item_id,
                        title=ob.title,
                        before_price=listing.current_price,
                        after_price=None,
                        result=decision.reason,
                    )
                    continue

                log.info(
                    "Lowering %s (%s): %d → %d (dry_run=%s)",
                    ob.item_id, ob.title[:30], listing.current_price, decision.new_price, dry_run,
                )

                if dry_run:
                    state.log_run(
                        ran_at=started_at,
                        item_id=ob.item_id,
                        title=ob.title,
                        before_price=listing.current_price,
                        after_price=decision.new_price,
                        result="lowered",
                        message="dry-run",
                    )
                else:
                    try:
                        await client.update_price(ob.item_id, decision.new_price)
                    except Exception as e:
                        log.exception("Failed to update %s", ob.item_id)
                        state.log_run(
                            ran_at=started_at,
                            item_id=ob.item_id,
                            title=ob.title,
                            before_price=listing.current_price,
                            after_price=None,
                            result="error",
                            message=str(e)[:500],
                        )
                        continue
                    state.mark_lowered(ob.item_id, decision.new_price, now_iso())
                    state.log_run(
                        ran_at=started_at,
                        item_id=ob.item_id,
                        title=ob.title,
                        before_price=listing.current_price,
                        after_price=decision.new_price,
                        result="lowered",
                    )

                await asyncio.sleep(
                    random.uniform(cfg.browser.per_item_delay_min, cfg.browser.per_item_delay_max)
                )

        entries = state.recent_run_log(started_at)
        try:
            send_summary(cfg.notify, entries, dry_run=dry_run)
            log.info("Summary email sent.")
        except Exception:
            log.exception("Failed to send summary email")

        errors = sum(1 for e in entries if e.result.startswith("error"))
        return 1 if errors else 0
    finally:
        state.close()


def cli() -> None:
    parser = argparse.ArgumentParser(description="Lower Mercari listing prices on a schedule.")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    parser.add_argument("--dry-run", action="store_true", help="Do not actually edit prices")
    args = parser.parse_args()

    cfg = load_config(args.config)
    _setup_logging(Path(cfg.paths.log_dir))
    rc = asyncio.run(run(cfg, dry_run=args.dry_run))
    sys.exit(rc)


if __name__ == "__main__":
    cli()
