from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

from src.cache import CachedClient, HttpCache
from src.config import cache_dir, load_env
from src.menu import fetch_page as fetch_page_text
from src.places import search_places as find_places
from src.reviews import read_reviews as fetch_review_summary
from src.search import search_web as find_pages

mcp = FastMCP("restaurant")
_client: CachedClient | None = None


def http_client() -> CachedClient:
    global _client
    if _client is None:
        load_env()
        _client = CachedClient(HttpCache(cache_dir()))
    return _client


def _key(name: str) -> str:
    load_env()
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing {name}")
    return value


def _dump(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _guard(fn: Callable[[], dict[str, Any]]) -> str:
    try:
        return _dump(fn())
    except (RuntimeError, httpx.HTTPError, ValueError, OSError) as exc:
        return _dump({"error": str(exc)[:400] or exc.__class__.__name__})


@mcp.tool(structured_output=False)
def search_places(query: str, city: str) -> str:
    """Find restaurants. query is the search you write. city is the city name. London searches are biased to the city center. Returns name, place id, rating, website, address, and snippet."""
    return _guard(lambda: find_places(http_client(), _key("GOOGLE_PLACES_API_KEY"), query, city))


@mcp.tool(structured_output=False)
def search_web(query: str) -> str:
    """Search the web for a menu page. Returns title, url, and snippet for each result."""
    return _guard(lambda: find_pages(http_client(), _key("TAVILY_API_KEY"), query))


@mcp.tool(structured_output=False)
def fetch_page(url: str) -> str:
    """Fetch a page. Returns the visible text, whether it is English, and the language name. A page that is not English is still returned. A failed fetch says menu page not fetched. A PDF or a picture says menu not readable as text."""
    return _guard(lambda: fetch_page_text(http_client(), url))


@mcp.tool(structured_output=False)
def read_reviews(place_id: str) -> str:
    """Read the Google review summary for a place id from search_places. Returns the cleaned summary, the reviews link, and the disclosure line."""
    return _guard(lambda: fetch_review_summary(http_client(), _key("GOOGLE_PLACES_API_KEY"), place_id))


def main() -> None:
    load_env()
    logging.getLogger("mcp").setLevel(logging.WARNING)
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
