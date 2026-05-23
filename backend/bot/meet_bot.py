"""Playwright-driven Google Meet bot.

The bot joins a Meet as a guest, screenshots periodically, and can post chat
messages and reactions. It does NOT inject audio — audio is intentionally out
of scope for this demo (see plan).

The host of the Meet must manually admit the bot (Google's anti-bot queue,
March 2026). The bot waits up to 60s for admission.

Usage from CLI (smoke test):
    python -m backend.bot.meet_bot --url https://meet.google.com/abc-defg-hij --name "AI Assistant"
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path

from playwright.async_api import Browser, BrowserContext, Page, async_playwright, expect

from backend.bot import selectors

log = logging.getLogger("meet_bot")

ADMISSION_TIMEOUT_MS = 60_000
ACTION_TIMEOUT_MS = 15_000


class MeetBot:
    """A Playwright wrapper around one Meet tab. Single-use (don't reuse across meetings)."""

    def __init__(self, meet_url: str, display_name: str = "AI Assistant") -> None:
        self.meet_url = meet_url
        self.display_name = display_name
        self._pw = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._joined = False

    async def start(self) -> None:
        """Launch Chromium and open a fresh context with media permissions granted."""
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(
            headless=False,
            args=[
                "--use-fake-ui-for-media-stream",
                "--use-fake-device-for-media-stream",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        self._context = await self._browser.new_context(
            permissions=["microphone", "camera"],
            viewport={"width": 1280, "height": 800},
        )
        self._page = await self._context.new_page()

    async def join(self) -> None:
        """Navigate to the Meet URL, fill in the guest name, mute, click Ask to join,
        and wait for the host to admit us. Raises TimeoutError if admission times out."""
        if self._page is None:
            raise RuntimeError("call start() before join()")

        log.info("navigating to %s", self.meet_url)
        await self._page.goto(self.meet_url)
        await self._page.wait_for_load_state("networkidle")

        try:
            name_field = selectors.name_input(self._page)
            await expect(name_field).to_be_visible(timeout=ACTION_TIMEOUT_MS)
            await name_field.fill(self.display_name)
            log.info("filled guest name: %s", self.display_name)
        except Exception:
            log.warning("name input not found — likely signed-in flow or already past prompt")

        for toggle in (selectors.mic_toggle, selectors.camera_toggle):
            try:
                btn = toggle(self._page)
                if await btn.get_attribute("data-is-muted") != "true":
                    await btn.click(timeout=3_000)
            except Exception:
                pass

        ask_button = selectors.ask_to_join_button(self._page)
        await expect(ask_button).to_be_visible(timeout=ACTION_TIMEOUT_MS)
        await ask_button.click()
        log.info("clicked Ask to join, waiting for host admission (up to %ss)", ADMISSION_TIMEOUT_MS // 1000)

        leave = selectors.leave_call_button(self._page)
        await expect(leave).to_be_visible(timeout=ADMISSION_TIMEOUT_MS)
        self._joined = True
        log.info("admitted to meeting")

    async def take_screenshot(self, save_to: Path | None = None) -> bytes:
        if self._page is None:
            raise RuntimeError("bot not started")
        png = await self._page.screenshot(full_page=False)
        if save_to is not None:
            save_to.parent.mkdir(parents=True, exist_ok=True)
            save_to.write_bytes(png)
        return png

    async def get_chat_messages(self) -> list[dict[str, str]]:
        """Return all chat messages currently visible in the side panel.

        Best-effort: probes a few likely shapes of Meet's chat DOM. Returns a list of
        {id, sender, text}. The bot must already have the chat panel open
        (`send_chat` opens it as a side effect; otherwise this returns []).
        """
        if self._page is None or not self._joined:
            return []
        try:
            return await self._page.evaluate(
                """() => {
                    const out = [];
                    // Modern Meet structure: nested divs with data attributes or aria-labels.
                    const rows = document.querySelectorAll(
                        '[data-message-id], [data-message-text], div[role="listitem"]'
                    );
                    rows.forEach((row, idx) => {
                        const id = row.getAttribute('data-message-id')
                            || row.getAttribute('id')
                            || `msg-${idx}`;
                        const senderEl = row.querySelector(
                            '[data-sender-name], [class*="sender"], [class*="author"]'
                        );
                        const sender = senderEl ? senderEl.textContent.trim() : '';
                        // Try the longest leaf text node as the message body
                        const textEl = row.querySelector('[data-message-text]')
                            || row.querySelector('div:not(:has(*))')
                            || row;
                        const text = textEl ? textEl.textContent.trim() : '';
                        if (text) out.push({id: String(id), sender, text});
                    });
                    return out;
                }"""
            )
        except Exception:
            return []

    async def _open_chat_panel(self) -> None:
        """Open the chat side panel if it isn't already open."""
        if self._page is None:
            return
        try:
            chat_input = selectors.chat_input(self._page)
            if await chat_input.is_visible():
                return
        except Exception:
            pass
        toggle = selectors.chat_panel_toggle(self._page)
        await expect(toggle).to_be_visible(timeout=ACTION_TIMEOUT_MS)
        await toggle.click()
        await expect(selectors.chat_input(self._page)).to_be_visible(timeout=ACTION_TIMEOUT_MS)

    async def send_chat(self, message: str) -> None:
        if not self._joined:
            raise RuntimeError("bot has not been admitted to the meeting yet")
        assert self._page is not None
        await self._open_chat_panel()
        chat_input = selectors.chat_input(self._page)
        await chat_input.fill(message)
        await chat_input.press("Enter")
        log.info("sent chat: %s", message[:80])

    async def send_reaction(self, emoji: str) -> None:
        if not self._joined:
            raise RuntimeError("bot has not been admitted to the meeting yet")
        assert self._page is not None
        react_btn = selectors.reaction_button(self._page)
        await expect(react_btn).to_be_visible(timeout=ACTION_TIMEOUT_MS)
        await react_btn.click()
        emoji_btn = selectors.reaction_emoji_button(self._page, emoji)
        await expect(emoji_btn).to_be_visible(timeout=5_000)
        await emoji_btn.click()
        log.info("sent reaction: %s", emoji)

    async def leave(self) -> None:
        if self._page is None:
            return
        try:
            leave_btn = selectors.leave_call_button(self._page)
            if await leave_btn.is_visible():
                await leave_btn.click()
                log.info("left meeting")
        except Exception as e:
            log.warning("leave button click failed: %s", e)

    async def stop(self) -> None:
        if self._context is not None:
            await self._context.close()
        if self._browser is not None:
            await self._browser.close()
        if self._pw is not None:
            await self._pw.stop()


async def _smoke_test(meet_url: str, display_name: str) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s: %(message)s")
    bot = MeetBot(meet_url, display_name)
    try:
        await bot.start()
        await bot.join()
        await asyncio.sleep(2)
        await bot.take_screenshot(Path("./out/screen.png"))
        log.info("screenshot saved to ./out/screen.png")
        await bot.send_chat("hello from bot")
        await asyncio.sleep(2)
        await bot.send_reaction("👍")
        await asyncio.sleep(3)
        await bot.leave()
    finally:
        await bot.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True, help="Google Meet URL")
    parser.add_argument("--name", default="AI Assistant", help="Display name for the bot")
    args = parser.parse_args()
    asyncio.run(_smoke_test(args.url, args.name))
