import asyncio
import json
from pathlib import Path

import pytest

from src.agent import MAX_TOOL_ROUNDS, build_graph, initial_messages, route, run_agent, system_prompt
from src.demo import parse_args
from src.models import Inputs

LUNCH = Inputs(
    city="London",
    meal="lunch",
    diet="vegetarian",
    note="normal sit-down lunch, not a tasting menu",
)


def _state(messages, rounds=0):
    return {
        "messages": messages,
        "city": "London",
        "meal": "lunch",
        "diet": "vegetarian",
        "note": "",
        "rounds": rounds,
        "transcript_path": "",
    }


def test_prompt_states_the_traveller_and_every_answer_item():
    text = system_prompt(LUNCH)
    assert "London" in text
    assert "lunch" in text
    assert "vegetarian" in text
    assert "not a tasting menu" in text
    assert "which places you kept, which you dropped, and why" in text
    assert "Translate those dishes into English" in text
    assert "summary had no negative line" in text
    assert "One restaurant and one backup" in text
    assert "homepage" in text
    assert "menu page URL" in text
    assert "Copy dish names" in text
    messages = initial_messages(LUNCH)
    assert messages[0]["role"] == "system"
    assert messages[1]["content"] == "Recommend restaurants for this trip."


def test_route_sends_a_tool_call_to_tools_and_a_plain_reply_to_finish():
    call = {
        "role": "assistant",
        "content": "",
        "tool_calls": [{"id": "call_1", "function": {"name": "search_places", "arguments": "{}"}}],
    }
    answer = {"role": "assistant", "content": "Primary: Mildreds"}
    assert route(_state([call], rounds=0)) == "tools"
    assert route(_state([answer], rounds=0)) == "finish"
    assert route(_state([call], rounds=MAX_TOOL_ROUNDS)) == "finish"


def test_stdio_server_lists_the_four_tools():
    from mcp import ClientSession
    from mcp.client.stdio import stdio_client

    from src.demo import openai_tools, server_parameters, tool_text

    async def listed() -> tuple[list[str], set[str], str]:
        async with stdio_client(server_parameters()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = openai_tools(await session.list_tools())
                names = [item["function"]["name"] for item in tools]
                places = next(item for item in tools if item["function"]["name"] == "search_places")
                fields = set(places["function"]["parameters"]["properties"])
                result = await session.call_tool("read_reviews", {"place_id": " "})
                return names, fields, tool_text(result)

    names, fields, review = asyncio.run(listed())
    assert names == ["fetch_page", "read_reviews", "search_places", "search_web"]
    assert fields == {"query", "city"}
    assert "no place id" in review


def test_parse_args_takes_the_traveller_and_has_no_stage_switch():
    args = parse_args(
        ["--city", "London", "--meal", "lunch", "--diet", "vegetarian", "--note", "sit-down"]
    )
    assert args.city == "London"
    assert args.meal == "lunch"
    assert args.diet == "vegetarian"
    assert args.note == "sit-down"
    with pytest.raises(SystemExit):
        parse_args(["--city", "London", "--meal", "brunch", "--diet", "vegetarian"])


def test_tool_call_returns_to_the_agent_and_a_plain_reply_finishes(tmp_path):
    seen: list[list[dict]] = []
    tool_log: list[tuple[str, dict]] = []

    def complete(messages):
        seen.append(list(messages))
        if len(seen) == 1:
            return {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "search_places",
                            "arguments": json.dumps({"query": "vegetarian lunch", "city": "London"}),
                        },
                    }
                ],
            }
        return {"role": "assistant", "content": "Primary: Mildreds\nBackup: The Gate"}

    async def call_tool(name, arguments):
        tool_log.append((name, arguments))
        return json.dumps({"places": [{"name": "Mildreds", "website": "https://mildreds.co.uk"}]})

    graph = build_graph(complete, call_tool, tmp_path)
    result = asyncio.run(run_agent(graph, LUNCH))

    assert tool_log == [("search_places", {"query": "vegetarian lunch", "city": "London"})]
    assert len(seen) == 2
    assert seen[1][-1]["role"] == "tool"
    assert "Mildreds" in seen[1][-1]["content"]
    assert seen[1][-2]["tool_calls"][0]["function"]["name"] == "search_places"

    text = Path(result["transcript_path"]).read_text(encoding="utf-8")
    assert "## search_places" in text
    assert "vegetarian lunch" in text
    assert "### Result (search_places)" in text
    assert "https://mildreds.co.uk" in text
    assert "## Final answer" in text
    assert "Primary: Mildreds" in text
    assert "Backup: The Gate" in text


def test_sixteen_tool_rounds_then_finish_without_another_call(tmp_path):
    calls = {"n": 0}

    def complete(messages):
        calls["n"] += 1
        return {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": f"call_{calls['n']}",
                    "type": "function",
                    "function": {
                        "name": "search_web",
                        "arguments": json.dumps({"query": "menu"}),
                    },
                }
            ],
        }

    async def call_tool(name, arguments):
        return json.dumps({"results": []})

    graph = build_graph(complete, call_tool, tmp_path)
    result = asyncio.run(run_agent(graph, LUNCH))
    text = Path(result["transcript_path"]).read_text(encoding="utf-8")
    assert calls["n"] == MAX_TOOL_ROUNDS + 1
    assert text.count("### Result (search_web)") == MAX_TOOL_ROUNDS
    assert "The tool round cap was reached, so the last tool calls were not run." in text
    assert "## Final answer" not in text
