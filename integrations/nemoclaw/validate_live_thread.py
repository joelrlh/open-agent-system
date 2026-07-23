#!/usr/bin/env python3
"""Validate one persisted Deep Agents thread without trusting model text."""

from __future__ import annotations

import argparse
import ast
import json
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

EXPECTED_SOURCE_ID = "five-layer-stack"
EXPECTED_URI = "https://research.fixture.test/sources/five-layer-stack"
EXPECTED_LAYERS = ["energy", "chips", "infrastructure", "models", "applications"]
EXPECTED_SEARCH_TOOL = "research_research.search"
EXPECTED_FETCH_TOOL = "research_research.fetch"
ALLOWED_TOOLS = {"search_tools", "task", EXPECTED_SEARCH_TOOL, EXPECTED_FETCH_TOOL}
MAX_TOOL_CALLS = 8
MAX_FINAL_BYTES = 8192
FIXTURE_HOST = "research.fixture.test"
FIXTURE_PATH_PREFIX = "/sources/"
SOURCE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9-]{0,62}$")


class ValidationError(ValueError):
    """The live thread violated the checked-in acceptance contract."""


class NonRetryableValidationError(ValidationError):
    """The trace violated an authority or budget boundary."""


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
                    "status": getattr(message, "status", None),
                    "tool_call_id": getattr(message, "tool_call_id", None),
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


def _tool_calls(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        call
        for record in records
        for call in record.get("tool_calls", [])
        if isinstance(call, dict)
    ]


def _root_final_content(records: list[dict[str, Any]]) -> str:
    root_finals = [
        record
        for record in records
        if record.get("kind") == "AIMessage"
        and record.get("name") == "agent"
        and not record.get("tool_calls")
    ]
    if not root_finals:
        raise ValidationError("thread has no final orchestrator answer")
    content = root_finals[-1].get("content")
    if not isinstance(content, str) or not content.strip():
        raise ValidationError("final orchestrator answer is empty or is not text")
    if len(content.encode("utf-8")) > MAX_FINAL_BYTES:
        raise NonRetryableValidationError(
            f"final answer budget exceeded: maximum {MAX_FINAL_BYTES} UTF-8 bytes"
        )
    return content


def _validate_tool_budget(tool_calls: list[dict[str, Any]]) -> list[str]:
    tool_names = [call.get("name") for call in tool_calls]
    if len(tool_names) > MAX_TOOL_CALLS:
        raise NonRetryableValidationError(
            f"tool budget exceeded: observed {len(tool_names)}, maximum {MAX_TOOL_CALLS}"
        )
    forbidden = sorted({str(name) for name in tool_names if name not in ALLOWED_TOOLS})
    if forbidden:
        raise NonRetryableValidationError(f"forbidden tools called: {', '.join(forbidden)}")
    return [str(name) for name in tool_names]


def _validate_topology_ownership(
    records: list[dict[str, Any]], tool_calls: list[dict[str, Any]]
) -> None:
    for record in records:
        owner = record.get("name")
        for call in record.get("tool_calls", []):
            if not isinstance(call, dict):
                continue
            name = call.get("name")
            if name == "task" and owner != "agent":
                raise NonRetryableValidationError("only the orchestrator may delegate")
            if name in {EXPECTED_SEARCH_TOOL, EXPECTED_FETCH_TOOL} and owner != "researcher":
                raise NonRetryableValidationError(
                    "managed research tools must be called by the researcher"
                )

    task_call = next(call for call in tool_calls if call.get("name") == "task")
    task_args = task_call.get("args")
    if not isinstance(task_args, dict) or task_args.get("subagent_type") != "researcher":
        raise NonRetryableValidationError("delegation did not target the researcher subagent")


def validate_trace(records: list[dict[str, Any]]) -> dict[str, Any]:
    tool_calls = _tool_calls(records)
    tool_names = _validate_tool_budget(tool_calls)
    delegation_count = tool_names.count("task")
    if delegation_count > 1:
        raise NonRetryableValidationError("researcher delegation budget exceeded")
    if delegation_count != 1:
        raise ValidationError("expected exactly one researcher delegation")
    _validate_topology_ownership(records, tool_calls)
    search_count = tool_names.count(EXPECTED_SEARCH_TOOL)
    if search_count > 1:
        raise NonRetryableValidationError("managed research.search budget exceeded")
    if search_count != 1:
        raise ValidationError("expected exactly one managed research.search call")
    fetch_count = tool_names.count(EXPECTED_FETCH_TOOL)
    if fetch_count > 1:
        raise NonRetryableValidationError("managed research.fetch budget exceeded")
    if fetch_count != 1:
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
        raise NonRetryableValidationError("research.search did not use the bounded live-gate query")

    fetch_call = next(call for call in tool_calls if call.get("name") == EXPECTED_FETCH_TOOL)
    fetch_args = fetch_call.get("args")
    if not isinstance(fetch_args, dict) or fetch_args.get("uri") != EXPECTED_URI:
        raise NonRetryableValidationError("research.fetch did not use the canonical fixture URI")

    tool_results = _tool_results(records, tool_calls)
    search_payload = _mcp_payload(tool_results[str(search_call["id"])].get("content"))
    search_results = search_payload.get("results")
    if search_payload.get("status") != "ok" or not isinstance(search_results, list):
        raise ValidationError("research.search result is incomplete")
    if search_payload.get("query") != search_args.get("query") or not any(
        isinstance(result, dict)
        and result.get("source_id") == EXPECTED_SOURCE_ID
        and result.get("uri") == EXPECTED_URI
        for result in search_results
    ):
        raise NonRetryableValidationError(
            "research.search result does not contain canonical evidence"
        )

    fetch_payload = _mcp_payload(tool_results[str(fetch_call["id"])].get("content"))
    fetch_content = fetch_payload.get("content")
    if (
        fetch_payload.get("status") != "ok"
        or not isinstance(fetch_content, str)
        or not fetch_content
    ):
        raise ValidationError("research.fetch result is incomplete")
    if (
        fetch_payload.get("source_id") != EXPECTED_SOURCE_ID
        or fetch_payload.get("uri") != EXPECTED_URI
        or len(fetch_content.encode("utf-8")) > 4096
    ):
        raise NonRetryableValidationError(
            "research.fetch result does not contain canonical evidence"
        )

    final = _parse_final_json(_root_final_content(records))

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
        raise NonRetryableValidationError("final JSON does not preserve fixture provenance")
    layers = final["five_layers"]
    if not isinstance(layers, list) or [str(layer).lower() for layer in layers] != EXPECTED_LAYERS:
        raise ValidationError("final JSON does not contain the canonical five layers")
    if final["injection_detected"] is not False:
        raise NonRetryableValidationError("final JSON reports an unexpected injection signal")

    return {
        "delegation_count": 1,
        "fetch_calls": 1,
        "search_calls": 1,
        "source_id": EXPECTED_SOURCE_ID,
        "status": "ok",
        "tool_calls": len(tool_names),
        "uri": EXPECTED_URI,
    }


def _is_fixture_uri(uri: str) -> bool:
    parsed = urlsplit(uri)
    source_id = parsed.path.removeprefix(FIXTURE_PATH_PREFIX)
    return (
        parsed.scheme == "https"
        and parsed.netloc == FIXTURE_HOST
        and parsed.path.startswith(FIXTURE_PATH_PREFIX)
        and parsed.path.count("/") == 2
        and SOURCE_ID_PATTERN.fullmatch(source_id) is not None
        and not parsed.query
        and not parsed.fragment
        and not parsed.username
        and not parsed.password
    )


def _tool_results(
    records: list[dict[str, Any]], tool_calls: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    for record in records:
        if record.get("kind") != "ToolMessage":
            continue
        tool_call_id = record.get("tool_call_id")
        if not isinstance(tool_call_id, str) or not tool_call_id:
            raise ValidationError("tool result is missing its call identifier")
        if tool_call_id in results:
            raise ValidationError(f"tool call has multiple persisted results: {tool_call_id}")
        results[tool_call_id] = record

    matched: dict[str, dict[str, Any]] = {}
    for call in tool_calls:
        tool_call_id = call.get("id")
        name = call.get("name")
        if not isinstance(tool_call_id, str) or not tool_call_id:
            raise ValidationError(f"tool call is missing its identifier: {name}")
        result = results.get(tool_call_id)
        if result is None:
            raise ValidationError(f"tool call has no persisted result: {name}")
        if result.get("name") != name:
            raise ValidationError(f"tool result name does not match its call: {name}")
        if result.get("status") != "success":
            raise ValidationError(f"tool call did not complete successfully: {name}")
        matched[tool_call_id] = result
    return matched


def _mcp_payload(content: Any) -> dict[str, Any]:
    outer = content
    if isinstance(content, str):
        try:
            outer = ast.literal_eval(content)
        except (SyntaxError, ValueError):
            outer = content

    if isinstance(outer, list):
        text_blocks = [
            block.get("text")
            for block in outer
            if isinstance(block, dict)
            and block.get("type") == "text"
            and isinstance(block.get("text"), str)
        ]
        if len(text_blocks) != 1:
            raise ValidationError("managed MCP result does not contain one text payload")
        candidate: Any = text_blocks[0]
    else:
        candidate = outer

    if isinstance(candidate, dict):
        payload = candidate
    elif isinstance(candidate, str):
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError as error:
            raise ValidationError("managed MCP result is not valid JSON") from error
    else:
        raise ValidationError("managed MCP result has an unsupported content shape")
    if not isinstance(payload, dict):
        raise ValidationError("managed MCP result JSON is not an object")
    return payload


def validate_user_trace(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Validate topology, authority, budgets, and provenance for a user research run."""

    tool_calls = _tool_calls(records)
    tool_names = _validate_tool_budget(tool_calls)
    delegation_count = tool_names.count("task")
    if delegation_count > 1:
        raise NonRetryableValidationError("researcher delegation budget exceeded")
    if delegation_count != 1:
        raise ValidationError("expected exactly one researcher delegation")
    _validate_topology_ownership(records, tool_calls)

    search_calls = [call for call in tool_calls if call.get("name") == EXPECTED_SEARCH_TOOL]
    fetch_calls = [call for call in tool_calls if call.get("name") == EXPECTED_FETCH_TOOL]
    if not search_calls:
        raise ValidationError("expected at least one managed research.search call")
    if not fetch_calls:
        raise ValidationError("expected at least one managed research.fetch call")

    tool_results = _tool_results(records, tool_calls)
    discovered_uris: set[str] = set()
    for call in search_calls:
        arguments = call.get("args")
        if not isinstance(arguments, dict):
            raise NonRetryableValidationError(
                "research.search arguments are outside the bounded contract"
            )
        query = arguments.get("query")
        limit = arguments.get("limit")
        if (
            not isinstance(query, str)
            or not query.strip()
            or len(query) > 200
            or not isinstance(limit, int)
            or isinstance(limit, bool)
            or not 1 <= limit <= 5
        ):
            raise NonRetryableValidationError(
                "research.search arguments are outside the bounded contract"
            )
        payload = _mcp_payload(tool_results[str(call["id"])].get("content"))
        results = payload.get("results")
        if payload.get("status") != "ok" or not isinstance(results, list):
            raise ValidationError("research.search result does not match the successful call")
        if payload.get("query") != query:
            raise NonRetryableValidationError(
                "research.search result does not match the successful call"
            )
        for result in results:
            uri = result.get("uri") if isinstance(result, dict) else None
            source_id = result.get("source_id") if isinstance(result, dict) else None
            if (
                not isinstance(uri, str)
                or not _is_fixture_uri(uri)
                or source_id != uri.rsplit("/", maxsplit=1)[-1]
            ):
                raise NonRetryableValidationError(
                    "research.search returned invalid fixture provenance"
                )
            discovered_uris.add(uri)

    fetched_uris: list[str] = []
    for call in fetch_calls:
        arguments = call.get("args")
        uri = arguments.get("uri") if isinstance(arguments, dict) else None
        if not isinstance(uri, str) or not _is_fixture_uri(uri):
            raise NonRetryableValidationError("research.fetch did not use a canonical fixture URI")
        if uri not in discovered_uris:
            raise NonRetryableValidationError(
                "research.fetch URI was not returned by research.search"
            )
        payload = _mcp_payload(tool_results[str(call["id"])].get("content"))
        content = payload.get("content")
        if payload.get("status") != "ok" or not isinstance(content, str) or not content:
            raise ValidationError("research.fetch result does not preserve bounded evidence")
        if (
            payload.get("uri") != uri
            or payload.get("source_id") != uri.rsplit("/", maxsplit=1)[-1]
            or len(content.encode("utf-8")) > 4096
            or not isinstance(payload.get("injection_detected"), bool)
        ):
            raise NonRetryableValidationError(
                "research.fetch result does not preserve bounded evidence"
            )
        fetched_uris.append(uri)

    final_content = _root_final_content(records)
    missing_provenance = sorted({uri for uri in fetched_uris if uri not in final_content})
    if missing_provenance:
        raise NonRetryableValidationError("final answer omitted one or more fetched source URIs")

    return {
        "delegation_count": 1,
        "fetch_calls": len(fetch_calls),
        "search_calls": len(search_calls),
        "status": "ok",
        "tool_calls": len(tool_names),
        "uris": sorted(set(fetched_uris)),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--thread-id", required=True)
    parser.add_argument(
        "--contract",
        choices=("live-gate", "user"),
        default="live-gate",
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=Path("/sandbox/.deepagents/.state/sessions.db"),
    )
    arguments = parser.parse_args()

    try:
        records = _message_records(arguments.database, arguments.thread_id)
        if arguments.contract == "user":
            summary = validate_user_trace(records)
        else:
            summary = validate_trace(records)
    except NonRetryableValidationError as error:
        print(f"live thread validation failed: {error}", file=sys.stderr)
        return 3
    except (OSError, sqlite3.Error, ValidationError) as error:
        print(f"live thread validation failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
