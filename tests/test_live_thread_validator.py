from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).parents[1] / "integrations" / "nemoclaw" / "validate_live_thread.py"
SPEC = importlib.util.spec_from_file_location("validate_live_thread", SCRIPT_PATH)
assert SPEC and SPEC.loader
validate_live_thread = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validate_live_thread)


def valid_trace() -> list[dict[str, object]]:
    final = {
        "delegation_count": 1,
        "source_id": "five-layer-stack",
        "uri": "https://research.fixture.test/sources/five-layer-stack",
        "five_layers": ["energy", "chips", "infrastructure", "models", "applications"],
        "injection_detected": False,
    }
    return [
        {
            "kind": "AIMessage",
            "name": "agent",
            "content": "",
            "tool_calls": [{"name": "task", "args": {"subagent_type": "researcher"}}],
        },
        {
            "kind": "AIMessage",
            "name": "researcher",
            "content": "",
            "tool_calls": [{"name": "search_tools", "args": {"query": "research"}}],
        },
        {
            "kind": "AIMessage",
            "name": "researcher",
            "content": "",
            "tool_calls": [
                {
                    "name": "research_research.search",
                    "args": {"query": "Jensen Huang five layers", "limit": 3},
                }
            ],
        },
        {
            "kind": "AIMessage",
            "name": "researcher",
            "content": "",
            "tool_calls": [
                {
                    "name": "research_research.fetch",
                    "args": {"uri": "https://research.fixture.test/sources/five-layer-stack"},
                }
            ],
        },
        {
            "kind": "AIMessage",
            "name": "agent",
            "content": json.dumps(final),
            "tool_calls": [],
        },
    ]


def test_accepts_exact_bounded_live_trace() -> None:
    summary = validate_live_thread.validate_trace(valid_trace())

    assert summary["status"] == "ok"
    assert summary["source_id"] == "five-layer-stack"
    assert summary["tool_calls"] == 4


def test_rejects_hallucinated_provenance() -> None:
    trace = valid_trace()
    trace[-1]["content"] = json.dumps(
        {
            "delegation_count": 1,
            "source_id": "knowledge",
            "uri": "https://www.nvidia.com/",
            "five_layers": ["chips", "systems", "software", "platforms", "ecosystem"],
            "injection_detected": False,
        }
    )

    with pytest.raises(validate_live_thread.ValidationError, match="fixture provenance"):
        validate_live_thread.validate_trace(trace)


def test_rejects_forbidden_fetch_url_even_with_valid_final_json() -> None:
    trace = valid_trace()
    trace.insert(
        -1,
        {
            "kind": "AIMessage",
            "name": "researcher",
            "content": "",
            "tool_calls": [{"name": "fetch_url", "args": {"url": "https://example.com"}}],
        },
    )

    with pytest.raises(validate_live_thread.ValidationError, match="forbidden tools"):
        validate_live_thread.validate_trace(trace)


def test_rejects_missing_managed_fetch() -> None:
    trace = [
        record
        for record in valid_trace()
        if not any(
            call.get("name") == "research_research.fetch" for call in record.get("tool_calls", [])
        )
    ]

    with pytest.raises(validate_live_thread.ValidationError, match=r"research\.fetch"):
        validate_live_thread.validate_trace(trace)
