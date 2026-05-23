"""Tiny wrapper around Google Programmable Search Engine."""

from __future__ import annotations

import logging
import os
from typing import TypedDict

import httpx

log = logging.getLogger(__name__)

SEARCH_URL = "https://www.googleapis.com/customsearch/v1"


class SearchHit(TypedDict):
    title: str
    snippet: str
    link: str


def search(query: str, num: int = 3, timeout: float = 8.0) -> list[SearchHit]:
    api_key = os.environ.get("GOOGLE_SEARCH_API_KEY")
    cx = os.environ.get("GOOGLE_SEARCH_CX")
    if not (api_key and cx):
        log.warning("Google search not configured (missing GOOGLE_SEARCH_API_KEY or GOOGLE_SEARCH_CX)")
        return []
    try:
        r = httpx.get(
            SEARCH_URL,
            params={"key": api_key, "cx": cx, "q": query, "num": num},
            timeout=timeout,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        log.warning("google search failed: %s", e)
        return []

    hits: list[SearchHit] = []
    for item in data.get("items", [])[:num]:
        hits.append(
            SearchHit(
                title=item.get("title", ""),
                snippet=item.get("snippet", ""),
                link=item.get("link", ""),
            )
        )
    return hits
