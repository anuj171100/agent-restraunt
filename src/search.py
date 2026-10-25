from __future__ import annotations

from typing import Any

from src.cache import CachedClient

TAVILY_URL = "https://api.tavily.com/search"


def parse_results(payload: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for row in payload.get("results") or []:
        if not isinstance(row, dict):
            continue
        url = row.get("url")
        if not isinstance(url, str) or not url.strip():
            continue
        title = row.get("title")
        snippet = row.get("content")
        rows.append(
            {
                "title": title.strip() if isinstance(title, str) else "",
                "url": url.strip(),
                "snippet": snippet.strip() if isinstance(snippet, str) else "",
            }
        )
    return rows


def search(
    client: CachedClient,
    api_key: str,
    query: str,
    max_results: int = 8,
) -> list[dict[str, str]]:
    response = client.post(
        TAVILY_URL,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        json_body={
            "query": query,
            "max_results": max_results,
            "search_depth": "basic",
            "include_answer": False,
        },
    )
    if response.status_code >= 400:
        raise RuntimeError(f"Search failed ({response.status_code}): {response.text[:400]}")
    return parse_results(response.json())


def search_web(client: CachedClient, api_key: str, query: str) -> dict[str, Any]:
    return {"query": query, "results": search(client, api_key, query)}
