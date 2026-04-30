"""Playwright-based Mercari client.

This module navigates the seller pages and changes prices. Mercari does not
publish a seller API, so DOM selectors here may need adjustment over time.
The selectors below target stable hooks (data-testid, aria-label, accessible
text) where possible; if Mercari ships a UI change, update them in one place.
"""
from __future__ import annotations

import asyncio
import logging
import random
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Self

from playwright.async_api import (
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
    TimeoutError as PWTimeoutError,
)

from .config import BrowserConfig

log = logging.getLogger(__name__)

LISTINGS_URL = "https://jp.mercari.com/mypage/listings"
EDIT_URL_TEMPLATE = "https://jp.mercari.com/sell/edit/{item_id}"
ITEM_ID_RE = re.compile(r"/item/(m\d+)")


@dataclass(frozen=True)
class ObservedListing:
    item_id: str
    title: str
    price: int


class MercariClient:
    def __init__(self, browser_cfg: BrowserConfig, log_dir: Path):
        self.cfg = browser_cfg
        self.log_dir = log_dir
        self._pw: Playwright | None = None
        self._ctx: BrowserContext | None = None
        self._page: Page | None = None

    async def __aenter__(self) -> Self:
        storage = Path(self.cfg.storage_state_path)
        if not storage.exists():
            raise FileNotFoundError(
                f"{storage} not found. Run `python scripts/login.py` first to log in to Mercari."
            )
        self._pw = await async_playwright().start()
        browser = await self._pw.chromium.launch(headless=self.cfg.headless)
        self._ctx = await browser.new_context(
            storage_state=str(storage),
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            ),
            locale="ja-JP",
        )
        self._page = await self._ctx.new_page()
        return self

    async def __aexit__(self, *exc) -> None:
        try:
            if self._ctx is not None:
                await self._ctx.storage_state(path=self.cfg.storage_state_path)
                await self._ctx.close()
        finally:
            if self._pw is not None:
                await self._pw.stop()

    async def _wait(self) -> None:
        delay = random.uniform(self.cfg.action_delay_min, self.cfg.action_delay_max)
        await asyncio.sleep(delay)

    async def _screenshot(self, label: str) -> Path:
        assert self._page is not None
        self.log_dir.mkdir(parents=True, exist_ok=True)
        path = self.log_dir / f"{label}-{int(asyncio.get_event_loop().time())}.png"
        await self._page.screenshot(path=str(path), full_page=True)
        return path

    async def fetch_active_listings(self) -> list[ObservedListing]:
        """Scrape the seller's active listings, paginating until exhausted."""
        assert self._page is not None
        page = self._page
        await page.goto(LISTINGS_URL, wait_until="domcontentloaded")
        await self._wait()

        results: dict[str, ObservedListing] = {}
        seen_pages = 0
        while True:
            seen_pages += 1
            cards = await page.locator("a[href*='/item/m']").all()
            for card in cards:
                href = await card.get_attribute("href") or ""
                m = ITEM_ID_RE.search(href)
                if not m:
                    continue
                item_id = m.group(1)
                if item_id in results:
                    continue
                title = (await card.get_attribute("aria-label")) or (await card.inner_text())
                title = (title or "").strip().splitlines()[0][:200]
                price = await _extract_price_near(card)
                if price is None:
                    continue
                results[item_id] = ObservedListing(item_id=item_id, title=title, price=price)

            next_btn = page.get_by_role("button", name=re.compile("次へ|Next"))
            if await next_btn.count() == 0 or not await next_btn.first.is_enabled():
                break
            await next_btn.first.click()
            await self._wait()
            if seen_pages > 50:
                log.warning("Pagination guard hit at %d pages", seen_pages)
                break

        return list(results.values())

    async def update_price(self, item_id: str, new_price: int) -> None:
        """Open edit page for `item_id`, set price, save."""
        assert self._page is not None
        page = self._page
        await page.goto(EDIT_URL_TEMPLATE.format(item_id=item_id), wait_until="domcontentloaded")
        await self._wait()

        price_input = page.locator("input[name='price'], input[aria-label*='販売価格']").first
        try:
            await price_input.wait_for(state="visible", timeout=15_000)
        except PWTimeoutError:
            shot = await self._screenshot(f"price-input-missing-{item_id}")
            raise RuntimeError(f"Could not find price input for {item_id}; screenshot at {shot}")

        await price_input.click()
        await price_input.press("ControlOrMeta+A")
        await price_input.press("Backspace")
        await price_input.type(str(new_price), delay=random.uniform(40, 100))
        await self._wait()

        submit = page.get_by_role("button", name=re.compile("変更する|更新|保存|出品を編集"))
        try:
            await submit.first.click()
        except PWTimeoutError:
            shot = await self._screenshot(f"submit-missing-{item_id}")
            raise RuntimeError(f"Could not find submit button for {item_id}; screenshot at {shot}")

        try:
            await page.wait_for_url(re.compile(r"/item/m\d+"), timeout=30_000)
        except PWTimeoutError:
            shot = await self._screenshot(f"submit-no-redirect-{item_id}")
            raise RuntimeError(f"Edit submit did not redirect for {item_id}; screenshot at {shot}")
        await self._wait()


async def _extract_price_near(card) -> int | None:
    """Find a price-like number inside or near the listing card link."""
    text = await card.inner_text()
    m = re.search(r"¥\s*([\d,]+)|￥\s*([\d,]+)", text)
    if not m:
        m2 = re.search(r"([\d,]{3,})\s*円", text)
        if not m2:
            return None
        raw = m2.group(1)
    else:
        raw = m.group(1) or m.group(2)
    try:
        return int(raw.replace(",", ""))
    except ValueError:
        return None
