import json

from src.cache import CachedClient, HttpCache


def test_cached_get_hits_disk_on_second_call(tmp_path, monkeypatch):
    cache = HttpCache(tmp_path)
    client = CachedClient(cache)
    calls = {"n": 0}

    class FakeResponse:
        status_code = 200
        headers = {"content-type": "text/plain"}
        text = "hello"

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def request(self, method, url, **kwargs):
            calls["n"] += 1
            return FakeResponse()

    monkeypatch.setattr("src.cache.httpx.Client", FakeClient)

    first = client.get("https://example.com/menu")
    second = client.get("https://example.com/menu")

    assert first.text == "hello"
    assert second.text == "hello"
    assert calls["n"] == 1
    assert list(tmp_path.glob("*.json"))


def test_replay_ignores_gzip_header_on_decoded_body(tmp_path):
    cache = HttpCache(tmp_path)
    client = CachedClient(cache)
    body = json.dumps({"textQuery": "vegan"}, ensure_ascii=False).encode()
    path = cache.put(
        "POST",
        "https://places.googleapis.com/v1/places:searchText",
        body,
        200,
        {
            "content-type": "application/json; charset=UTF-8",
            "content-encoding": "gzip",
            "content-length": "40",
            "transfer-encoding": "chunked",
        },
        '{"places":[]}',
    )
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert "content-encoding" not in stored["headers"]

    # Files written before the strip still carry the gzip header.
    stored["headers"]["content-encoding"] = "gzip"
    stored["headers"]["transfer-encoding"] = "chunked"
    path.write_text(json.dumps(stored), encoding="utf-8")

    response = client.post(
        "https://places.googleapis.com/v1/places:searchText",
        json_body={"textQuery": "vegan"},
    )

    assert response.status_code == 200
    assert response.text == '{"places":[]}'
    assert "content-encoding" not in response.headers
