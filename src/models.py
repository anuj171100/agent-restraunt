from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class Inputs(BaseModel):
    city: str
    meal: Literal["breakfast", "lunch", "dinner"]
    diet: str
    note: str = ""


class Candidate(BaseModel):
    name: str
    address: str = ""
    rating: float | None = None
    review_count: int | None = None
    website: str = ""
    maps_url: str = ""
    query: str
    place_id: str = ""
    snippet: str = ""
    source: str = "places"
