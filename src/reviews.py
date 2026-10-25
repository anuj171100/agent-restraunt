from __future__ import annotations

import re
from typing import Any

import httpx

from src.cache import CachedClient
from src.places import place_details

_CTRL = re.compile(r"<ctrl\d+>")


def _block(value: object) -> str:
    if isinstance(value, dict):
        text = value.get("text")
        return text if isinstance(text, str) else ""
    if isinstance(value, str):
        return value
    return ""


def clean_summary(text: str) -> str:
    return _CTRL.sub("", text).strip()


def review_fields(payload: dict) -> dict[str, str]:
    raw = payload.get("reviewSummary")
    if not isinstance(raw, dict):
        return {"summary": "", "reviews_uri": "", "disclosure": ""}
    uri = raw.get("reviewsUri")
    return {
        "summary": clean_summary(_block(raw.get("text"))),
        "reviews_uri": uri.strip() if isinstance(uri, str) else "",
        "disclosure": clean_summary(_block(raw.get("disclosureText"))),
    }


def read_reviews(client: CachedClient, api_key: str, place_id: str) -> dict[str, Any]:
    """The cleaned summary, its link, and the disclosure. The model splits the lines."""
    cleaned_id = place_id.strip()
    if cleaned_id.startswith("places/"):
        cleaned_id = cleaned_id[len("places/") :]
    if not cleaned_id:
        return {"error": "no place id"}
    try:
        payload = place_details(client, api_key, cleaned_id)
    except (RuntimeError, httpx.HTTPError) as exc:
        detail = str(exc).strip() or "request failed"
        return {"place_id": cleaned_id, "error": detail[:400]}
    fields = review_fields(payload)
    if not fields["summary"]:
        return {"place_id": cleaned_id, "error": "Place Details omitted the review summary"}
    return {"place_id": cleaned_id, **fields}
