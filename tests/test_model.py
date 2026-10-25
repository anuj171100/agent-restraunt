import json
from types import SimpleNamespace

import pytest
from openai import OpenAIError

from src.cache import HttpCache
from src.model import OPENROUTER_BASE_URL, complete


def test_complete_caches_the_assistant_message(tmp_path, monkeypatch):
    cache = HttpCache(tmp_path)
    calls = {"n": 0}
    function = SimpleNamespace(name="search_places", arguments='{"query": "veg", "city": "London"}')
    call = SimpleNamespace(id="call_1", type="function", function=function)
    message = SimpleNamespace(content="", tool_calls=[call])

    class Completions:
        def create(self, **kwargs):
            calls["n"] += 1
            assert kwargs["model"] == "openai/gpt-4o-mini"
            assert kwargs["temperature"] == 0
            assert kwargs["tools"][0]["function"]["name"] == "search_places"
            return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    class FakeOpenAI:
        def __init__(self, api_key, timeout, base_url):
            assert api_key == "sk-test"
            assert base_url == OPENROUTER_BASE_URL
            self.chat = SimpleNamespace(completions=Completions())

    monkeypatch.setattr("src.model.OpenAI", FakeOpenAI)
    messages = [{"role": "user", "content": "Recommend restaurants for this trip."}]
    tools = [
        {
            "type": "function",
            "function": {"name": "search_places", "parameters": {"type": "object"}},
        }
    ]
    first = complete(cache, "sk-test", "openai/gpt-4o-mini", messages, tools)
    second = complete(cache, "sk-test", "openai/gpt-4o-mini", messages, tools)
    assert calls["n"] == 1
    assert first == second
    assert first["tool_calls"][0]["id"] == "call_1"
    assert first["tool_calls"][0]["function"]["name"] == "search_places"


def test_complete_raises_when_openrouter_fails(tmp_path, monkeypatch):
    class Completions:
        def create(self, **kwargs):
            raise OpenAIError("down")

    class FakeOpenAI:
        def __init__(self, api_key, timeout, base_url):
            self.chat = SimpleNamespace(completions=Completions())

    monkeypatch.setattr("src.model.OpenAI", FakeOpenAI)
    with pytest.raises(RuntimeError, match="OpenRouter request failed"):
        complete(HttpCache(tmp_path), "sk-test", "openai/gpt-4o-mini", [], [])
