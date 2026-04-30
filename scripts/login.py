"""Open a headed Chromium for the user to log in to Mercari, then save storage state.

Run once before the first scheduled run, and again whenever the saved session
expires (Mercari will redirect to the login page in that case).
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright

# Make `mercari_auto` importable when run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from mercari_auto.config import load_config  # noqa: E402

LOGIN_URL = "https://jp.mercari.com/login"
MYPAGE_URL_FRAGMENT = "/mypage"


async def main() -> None:
    cfg = load_config()
    storage_path = Path(cfg.browser.storage_state_path)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        ctx = await browser.new_context(locale="ja-JP")
        page = await ctx.new_page()
        await page.goto(LOGIN_URL)

        print("ブラウザでログインしてください(SMS認証/CAPTCHAも完了させる)。")
        print("マイページに遷移したら自動で保存して終了します。タイムアウト: 10分。")

        try:
            await page.wait_for_url(lambda url: MYPAGE_URL_FRAGMENT in url, timeout=10 * 60_000)
        except Exception:
            print("タイムアウトしました。手動でマイページに遷移できたら Ctrl+C で中断してください。", file=sys.stderr)
            raise

        await ctx.storage_state(path=str(storage_path))
        print(f"ログイン情報を {storage_path} に保存しました。")
        await ctx.close()


if __name__ == "__main__":
    asyncio.run(main())
