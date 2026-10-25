import json

import httpx

from src.cache import CachedClient, HttpCache
from src.menu import fetch_page, is_english, language_name, page_text
from src.search import TAVILY_URL, parse_results, search

ENGLISH_HTML = """<!DOCTYPE html><html><head><title>Menu</title></head><body><article>
<h1>Starters</h1>
<p>Our lunch menu is served all day with care for the season.</p>
<p>Roast vegetable tart 14.50</p>
<p>Soup of the day 8.00</p>
</article></body></html>"""

SPANISH_HTML = """<!DOCTYPE html><html><head><title>Carta</title></head><body><article>
<h1>Entrantes</h1>
<p>Nuestros platos de la carta se sirven con pan y para compartir.</p>
<p>Tortilla de patatas con pimientos 9.50</p>
<p>Crema de calabaza del día 8.00</p>
</article></body></html>"""

SPANISH = (
    "Nuestros platos de la carta se sirven con pan y para compartir. "
    "Tortilla de patatas con pimientos del día."
)
FRENCH = "Notre carte propose une tarte aux légumes avec salade. Les desserts suivent."
GERMAN = "Vorspeisen mit Spargel und Sauce für den Abend."


class FakePage:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error

    def get(self, url, **kwargs):
        if self.error is not None:
            raise self.error
        return self.response


def test_parse_results_keeps_title_url_and_snippet():
    rows = parse_results(
        {
            "results": [
                {"title": "Menu", "url": " https://mildreds.co.uk/menus ", "content": "lunch"},
                {"title": "", "url": ""},
                "skip",
            ]
        }
    )
    assert rows == [{"title": "Menu", "url": "https://mildreds.co.uk/menus", "snippet": "lunch"}]


def test_english_check_accepts_english_and_rejects_other_menu_languages():
    assert is_english(
        "Our lunch menu is served all day with care for the season. "
        "Roast vegetable tart 14.50. Soup of the day."
    )
    assert is_english("Roast vegetable tart green salad tomato soup house potatoes")
    assert not is_english(SPANISH)
    assert not is_english(FRENCH)
    assert not is_english(GERMAN)


def test_language_name_names_english_and_the_other_menu_languages():
    assert language_name("Our lunch menu is served all day with care for the season.") == "English"
    assert language_name(SPANISH) == "Spanish"
    assert language_name(FRENCH) == "French"
    assert language_name(GERMAN) == "German"
    assert language_name("メニューはこちらです。本日のおすすめ。") == "not English"


def test_page_text_extracts_an_english_menu_and_drops_unreadable_pages():
    text, reason = page_text("https://mildreds.co.uk/menus", 200, "text/html", ENGLISH_HTML)
    assert reason == ""
    assert "Roast vegetable tart" in text
    spanish, spanish_reason = page_text("https://x.example/carta", 200, "text/html", SPANISH_HTML)
    assert spanish_reason == ""
    assert spanish
    assert not is_english(spanish)

    assert page_text("https://x.example/menu", 403, "text/html", ENGLISH_HTML)[1] == (
        "menu page not fetched"
    )
    assert page_text("https://x.example/menu.pdf", 200, "application/pdf", "%PDF-1.4")[1] == (
        "menu not readable as text"
    )
    assert page_text("https://x.example/menu.jpg", 200, "image/jpeg", "")[1] == (
        "menu not readable as text"
    )
    assert page_text("https://x.example/menu", 200, "text/html", "<html><body>Hi</body></html>")[1] == (
        "menu not readable as text"
    )


def test_fetch_page_returns_text_and_names_a_non_english_language():
    english = fetch_page(
        FakePage(
            httpx.Response(
                200,
                headers={"content-type": "text/html"},
                text=ENGLISH_HTML,
                request=httpx.Request("GET", "https://mildreds.co.uk/menus"),
            )
        ),
        "https://mildreds.co.uk/menus",
    )
    assert english["english"] is True
    assert english["language"] == "English"
    assert "Roast vegetable tart" in english["text"]

    spanish = fetch_page(
        FakePage(
            httpx.Response(
                200,
                headers={"content-type": "text/html"},
                text=SPANISH_HTML,
                request=httpx.Request("GET", "https://x.example/carta"),
            )
        ),
        "https://x.example/carta",
    )
    assert spanish["english"] is False
    assert spanish["language"] == "Spanish"
    assert "Tortilla" in spanish["text"]


def test_fetch_page_names_fetch_and_unreadable_failures():
    missing = fetch_page(
        FakePage(error=httpx.ConnectError("offline")),
        "https://mildreds.co.uk/menus",
    )
    assert missing == {"url": "https://mildreds.co.uk/menus", "error": "menu page not fetched"}

    blocked = fetch_page(
        FakePage(
            httpx.Response(
                403,
                headers={"content-type": "text/html"},
                text=ENGLISH_HTML,
                request=httpx.Request("GET", "https://mildreds.co.uk/menus"),
            )
        ),
        "https://mildreds.co.uk/menus",
    )
    assert blocked["error"] == "menu page not fetched"

    picture = fetch_page(
        FakePage(
            httpx.Response(
                200,
                headers={"content-type": "image/jpeg"},
                text="",
                request=httpx.Request("GET", "https://mildreds.co.uk/menu.jpg"),
            )
        ),
        "https://mildreds.co.uk/menu.jpg",
    )
    assert picture["error"] == "menu not readable as text"


def test_search_posts_the_query_and_then_uses_the_cache(tmp_path, monkeypatch):
    cache = HttpCache(tmp_path)
    client = CachedClient(cache)
    calls = {"n": 0}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def request(self, method, url, **kwargs):
            calls["n"] += 1
            assert method == "POST"
            assert url == TAVILY_URL
            body = json.loads(kwargs["content"])
            assert body["query"] == '"Mildreds" London menu'
            assert "api_key" not in body
            assert kwargs["headers"]["Authorization"] == "Bearer tvly-test"
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "title": "Menu",
                            "url": "https://mildreds.co.uk/menus",
                            "content": "lunch",
                        }
                    ]
                },
                request=httpx.Request(method, url),
            )

    monkeypatch.setattr("src.cache.httpx.Client", FakeClient)
    query = '"Mildreds" London menu'
    first = search(client, "tvly-test", query)
    second = search(client, "tvly-test", query)
    assert first == second
    assert first[0]["url"] == "https://mildreds.co.uk/menus"
    assert calls["n"] == 1
