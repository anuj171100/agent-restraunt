import json

import httpx

from src.cache import CachedClient, HttpCache
from src.places import PLACE_DETAILS_FIELDS, place_details, place_details_url
from src.reviews import clean_summary, read_reviews

PAGE = "https://maps.example/reviews"
DISCLOSURE = "Summarized with Gemini"

SAGAR = (
    "Diners praise this restaurant for its delicious South Indian vegetarian and vegan food, "
    "highlighting popular dishes such as dosas, paneer tikka masala, and Gobi Manchurian. "
    "They also appreciate the reasonable prices, friendly staff, and cozy atmosphere.\n\n"
    "Some reviews mention the service can be unprofessional."
)


def summary(text: str, url: str = PAGE, disclosure: str = DISCLOSURE) -> dict:
    return {
        "reviewSummary": {
            "text": {"text": text, "languageCode": "en-US"},
            "reviewsUri": url,
            "disclosureText": {"text": disclosure, "languageCode": "en-US"},
        }
    }


def test_place_details_url_uses_the_place_id():
    assert place_details_url("ChIJtest") == "https://places.googleapis.com/v1/places/ChIJtest"
    assert place_details_url("places/ChIJtest") == "https://places.googleapis.com/v1/places/ChIJtest"
    assert PLACE_DETAILS_FIELDS == "reviewSummary"


def test_clean_summary_strips_the_control_token():
    raw = "Diners like the vegan food and the tasting menu.<ctrl100>"
    assert clean_summary(raw) == "Diners like the vegan food and the tasting menu."
    assert "<ctrl" not in clean_summary(raw)


def test_read_reviews_returns_the_cleaned_summary_the_link_and_the_disclosure(monkeypatch):
    def fake_details(client, api_key, place_id):
        assert api_key == "places-key"
        assert place_id == "ChIJtest"
        return summary(SAGAR + "<ctrl100>")

    monkeypatch.setattr("src.reviews.place_details", fake_details)
    result = read_reviews(None, "places-key", " places/ChIJtest ")
    assert result["place_id"] == "ChIJtest"
    assert result["reviews_uri"] == PAGE
    assert result["disclosure"] == DISCLOSURE
    assert "<ctrl" not in result["summary"]
    assert "vegetarian" in result["summary"]
    assert "Some reviews mention the service can be unprofessional." in result["summary"]


def test_read_reviews_names_an_omitted_summary(monkeypatch):
    monkeypatch.setattr("src.reviews.place_details", lambda client, api_key, place_id: {"id": place_id})
    result = read_reviews(None, "places-key", "ChIJtest")
    assert result == {
        "place_id": "ChIJtest",
        "error": "Place Details omitted the review summary",
    }


def test_read_reviews_names_a_failed_details_call(monkeypatch):
    def fake_details(client, api_key, place_id):
        raise RuntimeError("Place Details failed (403): denied")

    monkeypatch.setattr("src.reviews.place_details", fake_details)
    failed = read_reviews(None, "places-key", "ChIJgood")
    assert failed["place_id"] == "ChIJgood"
    assert failed["error"] == "Place Details failed (403): denied"
    assert read_reviews(None, "places-key", "  ") == {"error": "no place id"}


def test_place_details_is_cached(tmp_path, monkeypatch):
    cache = HttpCache(tmp_path)
    client = CachedClient(cache)
    calls = {"n": 0}
    body = summary("Excellent vegetarian lunch.")

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def request(self, method, url, **kwargs):
            calls["n"] += 1
            assert method == "GET"
            assert url == place_details_url("ChIJtest")
            assert kwargs["headers"]["X-Goog-Api-Key"] == "places-key"
            assert kwargs["headers"]["X-Goog-FieldMask"] == "reviewSummary"
            return httpx.Response(200, json=body, request=httpx.Request(method, url))

    monkeypatch.setattr("src.cache.httpx.Client", FakeClient)
    first = place_details(client, "places-key", "ChIJtest")
    second = place_details(client, "places-key", "ChIJtest")
    assert calls["n"] == 1
    assert first == second
    assert first["reviewSummary"]["text"]["text"] == "Excellent vegetarian lunch."
    stored = json.loads(next(tmp_path.glob("*.json")).read_text(encoding="utf-8"))
    assert stored["method"] == "GET"
    assert "Excellent vegetarian lunch." in stored["text"]
    url = place_details_url("ChIJtest")
    assert cache.path_for("GET", url, field_mask="reviews") != cache.path_for(
        "GET", url, field_mask="reviewSummary"
    )
