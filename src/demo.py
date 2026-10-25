from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from src.agent import build_graph, run_agent
from src.cache import HttpCache
from src.config import ROOT, cache_dir, load_env, openai_model, require_env, runs_dir
from src.model import complete
from src.models import Inputs

__all__ = ["parse_args"]


def server_parameters() -> StdioServerParameters:
    load_env()
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "src.mcp_server"],
        cwd=str(ROOT),
        env=env,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Restaurant agent demo")
    parser.add_argument("--city", required=True)
    parser.add_argument("--meal", required=True, choices=["breakfast", "lunch", "dinner"])
    parser.add_argument("--diet", required=True)
    parser.add_argument("--note", default="")
    return parser.parse_args(argv)


def openai_tools(listed: Any) -> list[dict[str, Any]]:
    schemas = []
    for tool in listed.tools:
        schemas.append(
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description or "",
                    "parameters": tool.inputSchema or {"type": "object", "properties": {}},
                },
            }
        )
    schemas.sort(key=lambda item: item["function"]["name"])
    return schemas


def tool_text(result: Any) -> str:
    parts: list[str] = []
    for block in getattr(result, "content", None) or []:
        text = getattr(block, "text", None)
        if isinstance(text, str) and text:
            parts.append(text)
    body = "\n".join(parts)
    if getattr(result, "isError", False):
        return json_error(body or "tool failed")
    return body


def json_error(message: str) -> str:
    return json.dumps({"error": message[:400]}, ensure_ascii=False)


async def run(argv: list[str] | None = None) -> int:
    load_env()
    args = parse_args(argv)
    inputs = Inputs(city=args.city, meal=args.meal, diet=args.diet, note=args.note)
    require_env("GOOGLE_PLACES_API_KEY")
    require_env("TAVILY_API_KEY")
    api_key = require_env("OPENAI_API_KEY")
    model_name = openai_model()
    cache = HttpCache(cache_dir())
    params = server_parameters()
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            schemas = openai_tools(await session.list_tools())

            def complete_turn(messages: list[dict[str, Any]]) -> dict[str, Any]:
                return complete(cache, api_key, model_name, messages, schemas)

            async def call_tool(name: str, arguments: dict[str, Any]) -> str:
                return tool_text(await session.call_tool(name, arguments))

            graph = build_graph(complete_turn, call_tool, runs_dir())
            await run_agent(graph, inputs)
    return 0


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(run(argv))


if __name__ == "__main__":
    sys.exit(main())
