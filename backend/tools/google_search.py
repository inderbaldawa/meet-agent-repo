"""Wrapper around Serper (Google Search proxy) for full-web search."""

from __future__ import annotations

import logging
import os
from typing import TypedDict

import httpx

log = logging.getLogger(__name__)

SERPER_URL = "https://google.serper.dev/search"


class SearchHit(TypedDict):
    title: str
    snippet: str
    link: str


def search(query: str, num: int = 3, timeout: float = 8.0) -> list[SearchHit]:
    api_key = os.environ.get("SERPER_API_KEY")
    if not api_key:
        log.warning("Google search not configured (missing SERPER_API_KEY)")
        return []
    try:
        r = httpx.post(
            SERPER_URL,
            headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
            json={"q": query, "num": num},
            timeout=timeout,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        log.warning("serper search failed: %s", e)
        return []

    hits: list[SearchHit] = []
    for item in data.get("organic", [])[:num]:
        hits.append(
            SearchHit(
                title=item.get("title", ""),
                snippet=item.get("snippet", ""),
                link=item.get("link", ""),
            )
        )
    return hits
