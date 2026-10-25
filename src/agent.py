from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Awaitable, Callable
from operator import add
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph

from src.models import Inputs
from src.render import render_transcript, write_run

MAX_TOOL_ROUNDS = 16

Complete = Callable[[list[dict[str, Any]]], dict[str, Any]]
CallTool = Callable[[str, dict[str, Any]], Awaitable[str]]


class AgentState(TypedDict):
    messages: Annotated[list[dict[str, Any]], add]
    city: str
    meal: str
    diet: str
    note: str
    rounds: int
    transcript_path: str


def system_prompt(inputs: Inputs) -> str:
    note = inputs.note.strip() or "none"
    return f"""You are a restaurant agent for one traveller. You decide which tools to call, read the results, and stop when you can answer. Nothing else chooses the next step.

Traveller
- City: {inputs.city}
- Meal: {inputs.meal}
- Diet: {inputs.diet}
- Note: {note}

Tools
- search_places(query, city) finds restaurants. You write the query. Each place has a name, place id, rating, website, address, and snippet.
- search_web(query) finds web pages. Use it to find a menu page. It returns a title, a url, and a snippet.
- fetch_page(url) returns the visible page text and says whether that text is English. If the text is not English, it names the language. Translate those dishes into English. If the result says "menu page not fetched" or "menu not readable as text", that page has no menu text. A PDF or a picture is not readable text.
- read_reviews(place_id) returns one review summary, the reviews link, and the disclosure line. You pick the positive lines and the negative lines from that summary. You also find lines that match this diet, this meal, and the note.

When you answer, cover all of the following. Copy dish names, prices, and review quotes from the tool results. Do not invent them.
- The restaurants found, and the searches that found them.
- The shortlist: which places you kept, which you dropped, and why.
- The menu URL you read for each place you suggest. Everyday dishes and their prices from that menu text. If the note says this is an ordinary meal, leave out a tasting-menu section.
- If a menu was not English, the language it was in and your English translation of the dishes.
- A positive review line copied from the summary, with the reviews link. A negative review line copied from the summary, with the same link. If the summary has no negative line, say that the summary had no negative line.
- Lines from that summary that match this diet, this meal, and the note, with the same link.
- One restaurant and one backup. For each, the homepage from search_places and the menu page URL.

Write the answer in English."""


def initial_messages(inputs: Inputs) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": system_prompt(inputs)},
        {"role": "user", "content": "Recommend restaurants for this trip."},
    ]


def route(state: AgentState) -> str:
    last = state["messages"][-1] if state["messages"] else {}
    if last.get("role") == "assistant" and last.get("tool_calls"):
        if state.get("rounds", 0) >= MAX_TOOL_ROUNDS:
            return "finish"
        return "tools"
    return "finish"


def _arguments(raw: object) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("tool arguments must be an object")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("tool arguments must be an object")
    return value


def build_graph(complete: Complete, call_tool: CallTool, runs_directory):
    async def agent_node(state: AgentState) -> dict[str, Any]:
        message = await asyncio.to_thread(complete, list(state["messages"]))
        return {"messages": [message]}

    async def tools_node(state: AgentState) -> dict[str, Any]:
        last = state["messages"][-1]
        results: list[dict[str, str]] = []
        for call in last.get("tool_calls") or []:
            function = call.get("function") or {}
            name = function.get("name") or ""
            call_id = str(call.get("id") or "")
            try:
                arguments = _arguments(function.get("arguments"))
            except (json.JSONDecodeError, ValueError) as exc:
                results.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": json.dumps({"error": f"invalid tool arguments: {exc}"}),
                    }
                )
                continue
            try:
                content = await call_tool(name, arguments)
            except Exception as exc:
                content = json.dumps({"error": str(exc)[:400] or exc.__class__.__name__})
            results.append({"role": "tool", "tool_call_id": call_id, "content": content})
        return {"messages": results, "rounds": state.get("rounds", 0) + 1}

    def finish_node(state: AgentState) -> dict[str, str]:
        inputs = Inputs.model_validate(
            {
                "city": state["city"],
                "meal": state["meal"],
                "diet": state["diet"],
                "note": state["note"],
            }
        )
        last = state["messages"][-1] if state["messages"] else {}
        capped = state.get("rounds", 0) >= MAX_TOOL_ROUNDS and bool(last.get("tool_calls"))
        text = render_transcript(inputs, state["messages"], capped=capped)
        path = write_run(runs_directory, text)
        sys.stdout.write(text)
        if not text.endswith("\n"):
            sys.stdout.write("\n")
        print(f"Wrote {path}", file=sys.stderr)
        return {"transcript_path": str(path)}

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tools_node)
    graph.add_node("finish", finish_node)
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", route, {"tools": "tools", "finish": "finish"})
    graph.add_edge("tools", "agent")
    graph.add_edge("finish", END)
    return graph.compile()


async def run_agent(graph, inputs: Inputs) -> dict[str, Any]:
    return await graph.ainvoke(
        {
            "messages": initial_messages(inputs),
            "city": inputs.city,
            "meal": inputs.meal,
            "diet": inputs.diet,
            "note": inputs.note,
            "rounds": 0,
            "transcript_path": "",
        },
        config={"recursion_limit": MAX_TOOL_ROUNDS * 4},
    )
