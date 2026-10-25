from src.places import location_bias_for, parse_places, search_places


def test_london_gets_city_center_bias():
    bias = location_bias_for("London")
    assert bias is not None
    assert bias["circle"]["center"]["latitude"] == 51.5117
    assert bias["circle"]["center"]["longitude"] == -0.1236
    assert bias["circle"]["radius"] == 4000.0
    assert location_bias_for("Lisbon") is None


def test_parse_places_keeps_required_fields_and_caps_at_12():
    places = [
        {
            "id": f"id-{i}",
            "displayName": {"text": f"Place {i}"},
            "formattedAddress": f"{i} Neal Street",
            "rating": 4.2,
            "userRatingCount": 10 + i,
            "websiteUri": f"https://place{i}.co.uk",
            "googleMapsUri": f"https://maps.google.com/?cid={i}",
            "editorialSummary": {"text": "veg lunch"},
        }
        for i in range(15)
    ]
    rows = parse_places({"places": places}, "vegetarian lunch London")
    assert len(rows) == 12
    assert rows[0].name == "Place 0"
    assert rows[0].address == "0 Neal Street"
    assert rows[0].website == "https://place0.co.uk"
    assert rows[0].maps_url == "https://maps.google.com/?cid=0"
    assert rows[0].query == "vegetarian lunch London"
    assert rows[0].review_count == 10
    assert rows[0].place_id == "id-0"
    assert rows[0].snippet == "veg lunch"


def test_parse_places_skips_duplicate_names():
    payload = {
        "places": [
            {"displayName": {"text": "Mildreds"}, "id": "a"},
            {"displayName": {"text": "mildreds"}, "id": "b"},
            {"displayName": {"text": "The Gate"}, "id": "c"},
        ]
    }
    rows = parse_places(payload, "q")
    assert [row.name for row in rows] == ["Mildreds", "The Gate"]


def test_search_places_returns_the_model_fields(monkeypatch):
    def fake_search(client, api_key, query, city, page_size=12):
        assert api_key == "places-key"
        assert query == "vegetarian lunch"
        assert page_size == 12
        return {
            "places": [
                {
                    "id": "abc",
                    "displayName": {"text": "Mildreds"},
                    "formattedAddress": "Soho",
                    "rating": 4.5,
                    "websiteUri": "https://mildreds.co.uk",
                    "editorialSummary": {"text": "veg"},
                }
            ]
        }

    monkeypatch.setattr("src.places.search_text", fake_search)
    london = search_places(None, "places-key", "vegetarian lunch", "London")
    assert london["query"] == "vegetarian lunch"
    assert london["location_bias"] == "London city center, 4 km"
    assert london["places"] == [
        {
            "name": "Mildreds",
            "place_id": "abc",
            "rating": 4.5,
            "website": "https://mildreds.co.uk",
            "address": "Soho",
            "snippet": "veg",
        }
    ]
    lisbon = search_places(None, "places-key", "vegetarian lunch", "Lisbon")
    assert "location_bias" not in lisbon
