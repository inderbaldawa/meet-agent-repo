"""Centralized Playwright locators for Google Meet UI.

Google Meet's DOM changes frequently. Keeping every locator in this one file means
when the bot breaks, we only need to update here — and we can re-run
`discover_selectors.py` to discover the current accessible names.

Use Playwright's accessibility locators (`get_by_role`, `get_by_label`) rather than
raw CSS selectors. They survive class/id refactors as long as accessible names stay stable.
"""

from __future__ import annotations

import re

from playwright.async_api import Locator, Page


def name_input(page: Page) -> Locator:
    return page.get_by_role("textbox", name=re.compile("your name", re.I))


def ask_to_join_button(page: Page) -> Locator:
    return page.get_by_role("button", name=re.compile(r"ask to join|join now", re.I))


def mic_toggle(page: Page) -> Locator:
    return page.get_by_role("button", name=re.compile(r"turn off microphone|turn on microphone", re.I))


def camera_toggle(page: Page) -> Locator:
    return page.get_by_role("button", name=re.compile(r"turn off camera|turn on camera", re.I))


def leave_call_button(page: Page) -> Locator:
    return page.get_by_role("button", name=re.compile(r"leave call", re.I))


def chat_panel_toggle(page: Page) -> Locator:
    return page.get_by_role("button", name=re.compile(r"chat with everyone|chat", re.I))


def chat_input(page: Page) -> Locator:
    return page.get_by_role("textbox", name=re.compile(r"send a message", re.I))


def chat_send_button(page: Page) -> Locator:
    return page.get_by_role("button", name=re.compile(r"send a message|send message", re.I))


def chat_messages(page: Page) -> Locator:
    """All chat message rows currently rendered. Order is chronological."""
    return page.get_by_role("listitem").filter(has=page.locator("[data-sender-name], [data-message-text]"))


def reaction_button(page: Page) -> Locator:
    return page.get_by_role("button", name=re.compile(r"send a reaction|reaction", re.I))


def reaction_emoji_button(page: Page, emoji: str) -> Locator:
    """Within the reactions popover, the button that sends `emoji`."""
    return page.get_by_role("button", name=emoji)


def participants_count_button(page: Page) -> Locator:
    """The toolbar button labelled with the current participant count."""
    return page.get_by_role("button", name=re.compile(r"^\d+$"))
