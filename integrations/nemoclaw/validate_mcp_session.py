#!/usr/bin/env python3
"""Exercise the same MCP session path used by Deep Agents tool discovery."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any


class ValidationError(RuntimeError):
    """Raised when the managed MCP session is unavailable or has drifted."""


EXPECTED_TOOLS = {"research.fetch", "research.search"}


def validate_tool_names(names: list[str]) -> dict[str, Any]:
    if len(names) != len(set(names)):
        raise ValidationError("managed MCP server returned duplicate tool names")
    actual = set(names)
    if actual != EXPECTED_TOOLS:
        raise ValidationError(
            f"managed MCP tool set drifted: expected {sorted(EXPECTED_TOOLS)}, got {sorted(actual)}"
        )
    return {"status": "ok", "tools": sorted(actual)}


def normalize_connection(raw: object) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValidationError("managed MCP connection is not an object")
    connection = dict(raw)
    transport = connection.pop("type", connection.get("transport"))
    if transport != "http":
        raise ValidationError("managed MCP connection is not Streamable HTTP")
    connection["transport"] = "streamable_http"
    return connection


async def probe_session(config_path: Path, server_name: str) -> dict[str, Any]:
    from langchain_mcp_adapters.sessions import create_session

    try:
        document = json.loads(config_path.read_text(encoding="utf-8"))
        connection = normalize_connection(document["mcpServers"][server_name])
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValidationError("managed MCP adapter config is missing or invalid") from exc

    async with create_session(connection) as session:
        await session.initialize()
        result = await session.list_tools()
    return validate_tool_names([tool.name for tool in result.tools])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("/sandbox/.deepagents/.nemoclaw-mcp.json"),
    )
    parser.add_argument("--server", default="research")
    parser.add_argument("--timeout", type=float, default=20.0)
    args = parser.parse_args()

    try:
        summary = asyncio.run(
            asyncio.wait_for(probe_session(args.config, args.server), timeout=args.timeout)
        )
    except (ValidationError, TimeoutError, ExceptionGroup) as exc:
        raise SystemExit(f"managed MCP session validation failed: {exc}") from exc
    print(json.dumps(summary, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
