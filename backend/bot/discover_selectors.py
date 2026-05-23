"""One-off helper: open a Meet URL and dump every visible interactive element's
accessible role+name. Use this to populate `selectors.py` when Google changes the DOM.

Usage:
    python -m backend.bot.discover_selectors <meet-url>

The browser opens visible so you can manually progress through the join flow (name
prompt -> waiting room -> in-call) and re-run snapshots at each stage. Output is
written to ./out/selectors-dump-<timestamp>.txt.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime
from pathlib import Path

from playwright.async_api import Page, async_playwright

OUT_DIR = Path("./out")


async def snapshot(page: Page, label: str) -> str:
    """Capture every visible interactive element on the page."""
    elements = await page.evaluate(
        """() => {
            const out = [];
            const interactive = document.querySelectorAll(
                'button, [role="button"], [role="textbox"], [role="dialog"], a, input, textarea'
            );
            for (const el of interactive) {
                const rect = el.getBoundingClientRect();
                if (rect.width === 0 || rect.height === 0) continue;
                const role = el.getAttribute('role') || el.tagName.toLowerCase();
                const name = el.getAttribute('aria-label')
                    || el.getAttribute('placeholder')
                    || (el.textContent || '').trim().slice(0, 80);
                if (!name) continue;
                out.push({role, name});
            }
            return out;
        }"""
    )

    lines = [f"=== {label} (captured {datetime.now().isoformat()}) ==="]
    for el in elements:
        lines.append(f"  role={el['role']!r:20s} name={el['name']!r}")
    lines.append("")
    return "\n".join(lines)


async def main(meet_url: str) -> None:
    OUT_DIR.mkdir(exist_ok=True)
    out_path = OUT_DIR / f"selectors-dump-{datetime.now():%Y%m%d-%H%M%S}.txt"

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=[
                "--use-fake-ui-for-media-stream",
                "--use-fake-device-for-media-stream",
            ],
        )
        context = await browser.new_context(
            permissions=["microphone", "camera"],
            viewport={"width": 1280, "height": 800},
        )
        page = await context.new_page()
        await page.goto(meet_url)
        await page.wait_for_load_state("networkidle")

        snapshots: list[str] = []
        stages = ["pre-join", "after-name-fill", "waiting-room", "in-call"]

        for stage in stages:
            input(f"\nAdvance the UI to stage '{stage}' in the browser, then press ENTER...")
            snapshots.append(await snapshot(page, stage))

        out_path.write_text("\n".join(snapshots), encoding="utf-8")
        print(f"\nSelector dump written to {out_path}")

        await browser.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python -m backend.bot.discover_selectors <meet-url>")
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
