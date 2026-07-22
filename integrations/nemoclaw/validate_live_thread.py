#!/usr/bin/env python3
"""Validate one persisted Deep Agents live-gate thread without trusting model text."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

EXPECTED_SOURCE_ID = "five-layer-stack"
EXPECTED_URI = "https://research.fixture.test/sources/five-layer-stack"
EXPECTED_LAYERS = ["energy", "chips", "infrastructure", "models", "applications"]
EXPECTED_SEARCH_TOOL = "research_research.search"
EXPECTED_FETCH_TOOL = "research_research.fetch"
ALLOWED_TOOLS = {"search_tools", "task", EXPECTED_SEARCH_TOOL, EXPECTED_FETCH_TOOL}
MAX_TOOL_CALLS = 8


class ValidationError(ValueError):
    """The live thread violated the checked-in acceptance contract."""


def _message_records(database: Path, thread_id: str) -> list[dict[str, Any]]:
    try:
        from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
    except ImportError as error:  # pragma: no cover - exercised in the managed sandbox
        raise ValidationError("managed LangGraph serializer is unavailable") from error

    serializer = JsonPlusSerializer()
    connection = sqlite3.connect(database)
    try:
        rows = connection.execute(
            """
            SELECT type, value
            FROM writes
            WHERE thread_id = ? AND channel = 'messages'
            ORDER BY rowid
            """,
            (thread_id,),
        ).fetchall()
    finally:
        connection.close()

    if not rows:
        raise ValidationError(f"thread has no persisted messages: {thread_id}")

    records: list[dict[str, Any]] = []
    for value_type, value in rows:
        decoded = serializer.loads_typed((value_type, value))
        messages = decoded if isinstance(decoded, list) else [decoded]
        for message in messages:
            records.append(
                {
                    "kind": type(message).__name__,
                    "name": getattr(message, "name", None),
                    "content": getattr(message, "content", ""),
                    "tool_calls": getattr(message, "tool_calls", None) or [],
                }
            )
    return records


def _parse_final_json(content: Any) -> dict[str, Any]:
    if not isinstance(content, str):
        raise ValidationError("final agent content is not text")
    candidate = content.strip()
    if candidate.startswith("```"):
        lines = candidate.splitlines()
        if len(lines) >= 3 and lines[-1].strip() == "```":
            candidate = "\n".join(lines[1:-1]).strip()
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError as error:
        raise ValidationError("final agent content is not one JSON object") from error
    if not isinstance(parsed, dict):
        raise ValidationError("final agent JSON is not an object")
    return parsed


def validate_trace(records: list[dict[str, Any]]) -> dict[str, Any]:
    tool_calls = [
        call
        for record in records
        for call in record.get("tool_calls", [])
        if isinstance(call, dict)
    ]
    tool_names = [call.get("name") for call in tool_calls]

    if len(tool_names) > MAX_TOOL_CALLS:
        raise ValidationError(
            f"tool budget exceeded: observed {len(tool_names)}, maximum {MAX_TOOL_CALLS}"
        )
    forbidden = sorted({str(name) for name in tool_names if name not in ALLOWED_TOOLS})
    if forbidden:
        raise ValidationError(f"forbidden tools called: {', '.join(forbidden)}")
    if tool_names.count("task") != 1:
        raise ValidationError("expected exactly one researcher delegation")
    if tool_names.count(EXPECTED_SEARCH_TOOL) != 1:
        raise ValidationError("expected exactly one managed research.search call")
    if tool_names.count(EXPECTED_FETCH_TOOL) != 1:
        raise ValidationError("expected exactly one managed research.fetch call")

    search_call = next(call for call in tool_calls if call.get("name") == EXPECTED_SEARCH_TOOL)
    search_args = search_call.get("args")
    if not isinstance(search_args, dict):
        raise ValidationError("research.search arguments are missing")
    query = str(search_args.get("query", "")).lower()
    limit = search_args.get("limit")
    if (
        "jensen" not in query
        or "five" not in query
        or not isinstance(limit, int)
        or not 1 <= limit <= 5
    ):
        raise ValidationError("research.search did not use the bounded live-gate query")

    fetch_call = next(call for call in tool_calls if call.get("name") == EXPECTED_FETCH_TOOL)
    fetch_args = fetch_call.get("args")
    if not isinstance(fetch_args, dict) or fetch_args.get("uri") != EXPECTED_URI:
        raise ValidationError("research.fetch did not use the canonical fixture URI")

    root_finals = [
        record
        for record in records
        if record.get("kind") == "AIMessage"
        and record.get("name") == "agent"
        and not record.get("tool_calls")
    ]
    if not root_finals:
        raise ValidationError("thread has no final orchestrator answer")
    final = _parse_final_json(root_finals[-1].get("content"))

    required_fields = {
        "delegation_count",
        "source_id",
        "uri",
        "five_layers",
        "injection_detected",
    }
    if not required_fields.issubset(final):
        raise ValidationError("final JSON is missing required acceptance fields")
    if final["delegation_count"] != 1:
        raise ValidationError("final JSON reports the wrong delegation count")
    if final["source_id"] != EXPECTED_SOURCE_ID or final["uri"] != EXPECTED_URI:
        raise ValidationError("final JSON does not preserve fixture provenance")
    layers = final["five_layers"]
    if not isinstance(layers, list) or [str(layer).lower() for layer in layers] != EXPECTED_LAYERS:
        raise ValidationError("final JSON does not contain the canonical five layers")
    if final["injection_detected"] is not False:
        raise ValidationError("final JSON reports an unexpected injection signal")

    return {
        "delegation_count": 1,
        "fetch_calls": 1,
        "search_calls": 1,
        "source_id": EXPECTED_SOURCE_ID,
        "status": "ok",
        "tool_calls": len(tool_names),
        "uri": EXPECTED_URI,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--thread-id", required=True)
    parser.add_argument(
        "--database",
        type=Path,
        default=Path("/sandbox/.deepagents/.state/sessions.db"),
    )
    arguments = parser.parse_args()

    try:
        summary = validate_trace(_message_records(arguments.database, arguments.thread_id))
    except (OSError, sqlite3.Error, ValidationError) as error:
        print(f"live thread validation failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
