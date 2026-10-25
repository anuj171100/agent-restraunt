from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from src.models import Inputs


def _pretty(raw: object) -> str:
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return raw
        return json.dumps(parsed, ensure_ascii=False, indent=2)
    return json.dumps(raw, ensure_ascii=False, indent=2)


def render_transcript(
    inputs: Inputs,
    messages: list[dict[str, Any]],
    *,
    capped: bool = False,
) -> str:
    """The conversation: each tool call, its result, then the model's final answer."""
    lines = [
        "# Restaurant agent",
        "",
        f"City: {inputs.city}",
        f"Meal: {inputs.meal}",
        f"Diet: {inputs.diet or 'n/a'}",
        f"Note: {inputs.note or 'n/a'}",
        "",
    ]
    calls: dict[str, dict[str, Any]] = {}
    final = ""
    for message in messages:
        role = message.get("role")
        if role == "assistant":
            content = (message.get("content") or "").strip()
            tool_calls = message.get("tool_calls") or []
            if tool_calls:
                if content:
                    lines.extend([content, ""])
                for call in tool_calls:
                    call_id = str(call.get("id") or "")
                    calls[call_id] = call
                    function = call.get("function") or {}
                    lines.extend(
                        [
                            f"## {function.get('name') or 'tool'}",
                            "",
                            _pretty(function.get("arguments") or ""),
                            "",
                        ]
                    )
            else:
                final = content
        elif role == "tool":
            call = calls.get(str(message.get("tool_call_id") or ""))
            function = (call or {}).get("function") or {}
            name = function.get("name") or "tool"
            lines.extend(
                [
                    f"### Result ({name})",
                    "",
                    message.get("content") or "",
                    "",
                ]
            )
    if capped:
        lines.extend(
            [
                "## Stopped",
                "",
                "The tool round cap was reached, so the last tool calls were not run.",
                "",
            ]
        )
    else:
        lines.extend(["## Final answer", "", final, ""])
    return "\n".join(lines)


def write_run(directory: Path, text: str, now: datetime | None = None) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    moment = now or datetime.now()
    path = directory / f"{moment.strftime('%Y%m%d-%H%M%S')}.md"
    if path.exists():
        path = directory / f"{moment.strftime('%Y%m%d-%H%M%S-%f')}.md"
    path.write_text(text, encoding="utf-8")
    return path
