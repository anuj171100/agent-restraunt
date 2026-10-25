from __future__ import annotations

import json
from typing import Any

from openai import OpenAI, OpenAIError

from src.cache import HttpCache

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENAI_URL = f"{OPENROUTER_BASE_URL}/chat/completions"


def _cache_body(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()


def message_dict(message: Any) -> dict[str, Any]:
    tool_calls = []
    for call in getattr(message, "tool_calls", None) or []:
        function = call.function
        arguments = function.arguments if isinstance(function.arguments, str) else "{}"
        tool_calls.append(
            {
                "id": call.id,
                "type": getattr(call, "type", None) or "function",
                "function": {
                    "name": function.name,
                    "arguments": arguments or "{}",
                },
            }
        )
    result: dict[str, Any] = {"role": "assistant", "content": message.content or ""}
    if tool_calls:
        result["tool_calls"] = tool_calls
    return result


def complete(
    cache: HttpCache,
    api_key: str,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
) -> dict[str, Any]:
    """One cached chat completion. A rerun replays the stored assistant message."""
    payload = {
        "model": model,
        "temperature": 0,
        "max_tokens": 8000,
        "messages": messages,
        "tools": tools,
    }
    body = _cache_body(payload)
    cached = cache.get("POST", OPENAI_URL, body)
    if cached is not None:
        try:
            stored = json.loads(cached.get("text") or "")
        except json.JSONDecodeError as exc:
            raise RuntimeError("cached completion was not valid JSON") from exc
        if not isinstance(stored, dict):
            raise RuntimeError("cached completion was not an assistant message")
        return stored

    try:
        completion = OpenAI(
            api_key=api_key,
            base_url=OPENROUTER_BASE_URL,
            timeout=60.0,
        ).chat.completions.create(
            model=payload["model"],
            temperature=payload["temperature"],
            max_tokens=payload["max_tokens"],
            messages=payload["messages"],
            tools=payload["tools"],
        )
    except OpenAIError as exc:
        raise RuntimeError(f"OpenRouter request failed: {exc}") from exc

    result = message_dict(completion.choices[0].message)
    cache.put(
        "POST",
        OPENAI_URL,
        body,
        200,
        {},
        json.dumps(result, ensure_ascii=False),
    )
    return result
