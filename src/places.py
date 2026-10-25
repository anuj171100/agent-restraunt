from __future__ import annotations

from typing import Any
from urllib.parse import quote

from src.cache import CachedClient
from src.models import Candidate

TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
TEXT_SEARCH_FIELDS = ",".join(
    [
        "places.id",
        "places.displayName",
        "places.formattedAddress",
        "places.rating",
        "places.userRatingCount",
        "places.websiteUri",
        "places.googleMapsUri",
        "places.editorialSummary",
    ]
)

PLACE_DETAILS_FIELDS = "reviewSummary"

# Covent Garden. Used only when the city is London.
LONDON_CENTER = {"latitude": 51.5117, "longitude": -0.1236}
LONDON_RADIUS_M = 4000.0


MAX_CANDIDATES = 12


def _text(value: object) -> str:
    if isinstance(value, dict):
        text = value.get("text")
        return text.strip() if isinstance(text, str) else ""
    if isinstance(value, str):
        return value.strip()
    return ""


def parse_places(payload: dict, query: str) -> list[Candidate]:
    rows: list[Candidate] = []
    seen: set[str] = set()
    for place in payload.get("places") or []:
        if not isinstance(place, dict):
            continue
        name = _text(place.get("displayName"))
        if not name:
            continue
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        rating = place.get("rating")
        review_count = place.get("userRatingCount")
        rows.append(
            Candidate(
                name=name,
                address=_text(place.get("formattedAddress")),
                rating=rating if isinstance(rating, (int, float)) else None,
                review_count=review_count if isinstance(review_count, int) else None,
                website=_text(place.get("websiteUri")),
                maps_url=_text(place.get("googleMapsUri")),
                query=query,
                place_id=_text(place.get("id")),
                snippet=_text(place.get("editorialSummary")),
                source="places",
            )
        )
        if len(rows) >= MAX_CANDIDATES:
            break
    return rows


def location_bias_for(city: str) -> dict[str, Any] | None:
    if city.strip().casefold() != "london":
        return None
    return {
        "circle": {
            "center": LONDON_CENTER,
            "radius": LONDON_RADIUS_M,
        }
    }


def search_text(
    client: CachedClient,
    api_key: str,
    query: str,
    city: str,
    page_size: int = 12,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "textQuery": query,
        "pageSize": page_size,
        "includedType": "restaurant",
    }
    bias = location_bias_for(city)
    if bias is not None:
        payload["locationBias"] = bias

    response = client.post(
        TEXT_SEARCH_URL,
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": TEXT_SEARCH_FIELDS,
        },
        json_body=payload,
    )
    if response.status_code >= 400:
        raise RuntimeError(
            f"Places Text Search failed ({response.status_code}): {response.text[:400]}"
        )
    return response.json()


def place_details_url(place_id: str) -> str:
    cleaned = place_id.strip()
    if cleaned.startswith("places/"):
        cleaned = cleaned[len("places/") :]
    return f"https://places.googleapis.com/v1/places/{quote(cleaned, safe='')}"


def place_details(client: CachedClient, api_key: str, place_id: str) -> dict[str, Any]:
    url = place_details_url(place_id)
    response = client.get(
        url,
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": PLACE_DETAILS_FIELDS,
        },
    )
    if response.status_code >= 400:
        raise RuntimeError(
            f"Place Details failed ({response.status_code}): {response.text[:400]}"
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError("Place Details returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Place Details returned invalid JSON")
    return payload


def search_places(client: CachedClient, api_key: str, query: str, city: str) -> dict[str, Any]:
    """Places the model asked for. The query is the model's. London keeps its location bias."""
    payload = search_text(client, api_key, query, city, page_size=MAX_CANDIDATES)
    places = [
        {
            "name": row.name,
            "place_id": row.place_id,
            "rating": row.rating,
            "website": row.website,
            "address": row.address,
            "snippet": row.snippet,
        }
        for row in parse_places(payload, query)
    ]
    result: dict[str, Any] = {"query": query, "city": city, "places": places}
    if location_bias_for(city) is not None:
        result["location_bias"] = "London city center, 4 km"
    return result
