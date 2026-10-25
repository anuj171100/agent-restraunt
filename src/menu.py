from __future__ import annotations

import re
from urllib.parse import urlparse

import httpx
import trafilatura

from src.cache import CachedClient

MIN_TEXT = 40

_MENU_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
}

_UNREADABLE_SUFFIXES = (".pdf", ".png", ".jpg", ".jpeg", ".webp", ".gif")

_ENGLISH = frozenset(
    "the and with our from which this that your we are for of is to "
    "in on at by or as an be it not you all".split()
)
_LANGUAGES: dict[str, frozenset[str]] = {
    "Spanish": frozenset(
        "los las una del por como para con sobre carta platos nuestros "
        "entrantes postres bebidas raciones".split()
    ),
    "French": frozenset("les des une avec aux carte entrée entrées boissons".split()),
    "Italian": frozenset("della delle degli alla nel nella antipasti".split()),
    "German": frozenset("und der das mit für von nicht vorspeisen speisekarte".split()),
    "Catalan": frozenset("amb dels entrants begudes".split()),
}
_OTHER = frozenset().union(*_LANGUAGES.values())


def is_english(text: str) -> bool:
    words = re.findall(r"[A-Za-zÀ-ÿ']+", text.lower())
    if len(words) < 4:
        return False
    english_hits = sum(1 for word in words if word in _ENGLISH)
    other_hits = sum(1 for word in words if word in _OTHER)
    letters = [char for char in text if char.isalpha()]
    if letters:
        non_latin = sum(1 for char in letters if ord(char) > 0x024F)
        if non_latin / len(letters) > 0.2:
            return False
    if other_hits >= 2 and other_hits > english_hits:
        return False
    if english_hits >= 2 and english_hits >= other_hits:
        return True
    if other_hits == 0 and letters:
        basic = sum(1 for char in letters if "a" <= char.lower() <= "z")
        return basic / len(letters) >= 0.95
    return False


def language_name(text: str) -> str:
    if is_english(text):
        return "English"
    words = re.findall(r"[A-Za-zÀ-ÿ']+", text.lower())
    scores = {
        name: sum(1 for word in words if word in vocab) for name, vocab in _LANGUAGES.items()
    }
    best_score = max(scores.values(), default=0)
    tied = [name for name, score in scores.items() if score == best_score]
    if best_score >= 2 and len(tied) == 1:
        return tied[0]
    return "not English"


def page_text(url: str, status: int, content_type: str, html: str) -> tuple[str, str]:
    if status >= 400:
        return "", "menu page not fetched"
    kind = content_type.lower()
    path = urlparse(url).path.lower()
    if (
        "pdf" in kind
        or kind.startswith("image/")
        or path.endswith(_UNREADABLE_SUFFIXES)
        or html.lstrip().startswith("%PDF")
    ):
        return "", "menu not readable as text"
    extracted = trafilatura.extract(
        html,
        url=url,
        include_comments=False,
        include_tables=True,
        favor_recall=True,
    )
    text = (extracted or "").strip()
    if len(text) < MIN_TEXT:
        return "", "menu not readable as text"
    return text, ""


def fetch_html(client: CachedClient, url: str) -> tuple[int, str, str]:
    response = client.get(url, headers=_MENU_HEADERS)
    return response.status_code, response.headers.get("content-type", ""), response.text


def fetch_page(client: CachedClient, url: str) -> dict[str, object]:
    """Visible text for the model to read. A non-English page is still returned."""
    try:
        status, content_type, html = fetch_html(client, url)
    except httpx.HTTPError:
        return {"url": url, "error": "menu page not fetched"}
    text, reason = page_text(url, status, content_type, html)
    if reason:
        return {"url": url, "error": reason}
    return {
        "url": url,
        "english": is_english(text),
        "language": language_name(text),
        "text": text,
    }
