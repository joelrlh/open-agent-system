from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).parents[1] / "integrations" / "nemoclaw" / "validate_live_thread.py"
SPEC = importlib.util.spec_from_file_location("validate_live_thread", SCRIPT_PATH)
assert SPEC and SPEC.loader
validate_live_thread = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validate_live_thread)


def _call_trace() -> list[dict[str, object]]:
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


def valid_trace() -> list[dict[str, object]]:
    trace = copy.deepcopy(_call_trace())
    call_ids = ("task-call", "discovery-call", "search-call", "fetch-call")
    for record, call_id in zip(trace[:-1], call_ids, strict=True):
        record["tool_calls"][0]["id"] = call_id

    uri = "https://research.fixture.test/sources/five-layer-stack"
    tool_results = [
        {
            "kind": "ToolMessage",
            "name": "task",
            "content": "bounded researcher evidence",
            "status": "success",
            "tool_call_id": "task-call",
            "tool_calls": [],
        },
        {
            "kind": "ToolMessage",
            "name": "search_tools",
            "content": "bounded discovery results",
            "status": "success",
            "tool_call_id": "discovery-call",
            "tool_calls": [],
        },
        {
            "kind": "ToolMessage",
            "name": "research_research.search",
            "content": repr(
                [
                    {
                        "type": "text",
                        "text": json.dumps(
                            {
                                "count": 1,
                                "query": "Jensen Huang five layers",
                                "results": [
                                    {
                                        "source_id": "five-layer-stack",
                                        "uri": uri,
                                    }
                                ],
                                "status": "ok",
                            }
                        ),
                    }
                ]
            ),
            "status": "success",
            "tool_call_id": "search-call",
            "tool_calls": [],
        },
        {
            "kind": "ToolMessage",
            "name": "research_research.fetch",
            "content": repr(
                [
                    {
                        "type": "text",
                        "text": json.dumps(
                            {
                                "content": "bounded fixture evidence",
                                "injection_detected": False,
                                "source_id": "five-layer-stack",
                                "status": "ok",
                                "uri": uri,
                            }
                        ),
                    }
                ]
            ),
            "status": "success",
            "tool_call_id": "fetch-call",
            "tool_calls": [],
        },
    ]
    return [*trace[:-1], *tool_results, trace[-1]]


def valid_user_trace() -> list[dict[str, object]]:
    return copy.deepcopy(valid_trace())


def test_accepts_exact_bounded_live_trace() -> None:
    summary = validate_live_thread.validate_trace(valid_trace())

    assert summary["status"] == "ok"
    assert summary["source_id"] == "five-layer-stack"
    assert summary["tool_calls"] == 4


def test_exact_live_trace_requires_successful_managed_results() -> None:
    trace = valid_trace()
    fetch_result = next(
        record
        for record in trace
        if record.get("kind") == "ToolMessage" and record.get("name") == "research_research.fetch"
    )
    fetch_result["status"] = "error"

    with pytest.raises(validate_live_thread.ValidationError, match="complete successfully"):
        validate_live_thread.validate_trace(trace)


def test_exact_live_trace_requires_researcher_delegation() -> None:
    trace = valid_trace()
    trace[0]["tool_calls"][0]["args"]["subagent_type"] = "general-purpose"

    with pytest.raises(
        validate_live_thread.NonRetryableValidationError,
        match="researcher subagent",
    ):
        validate_live_thread.validate_trace(trace)


def test_exact_live_trace_rejects_direct_orchestrator_research_call() -> None:
    trace = valid_trace()
    trace[2]["name"] = "agent"

    with pytest.raises(
        validate_live_thread.NonRetryableValidationError,
        match="called by the researcher",
    ):
        validate_live_thread.validate_trace(trace)


def test_exact_live_trace_rejects_forged_search_provenance() -> None:
    trace = valid_trace()
    search_result = next(
        record
        for record in trace
        if record.get("kind") == "ToolMessage" and record.get("name") == "research_research.search"
    )
    search_result["content"] = {
        "query": "Jensen Huang five layers",
        "results": [
            {
                "source_id": "forged",
                "uri": "https://research.fixture.test/sources/five-layer-stack",
            }
        ],
        "status": "ok",
    }

    with pytest.raises(
        validate_live_thread.NonRetryableValidationError,
        match="canonical evidence",
    ):
        validate_live_thread.validate_trace(trace)


def test_exact_live_trace_rejects_oversized_fetch_evidence() -> None:
    trace = valid_trace()
    fetch_result = next(
        record
        for record in trace
        if record.get("kind") == "ToolMessage" and record.get("name") == "research_research.fetch"
    )
    fetch_result["content"] = {
        "content": "x" * 4097,
        "injection_detected": False,
        "source_id": "five-layer-stack",
        "status": "ok",
        "uri": "https://research.fixture.test/sources/five-layer-stack",
    }

    with pytest.raises(
        validate_live_thread.NonRetryableValidationError,
        match="canonical evidence",
    ):
        validate_live_thread.validate_trace(trace)


def test_exact_live_trace_rejects_oversized_final_answer() -> None:
    trace = valid_trace()
    trace[-1]["content"] = "x" * 8193

    with pytest.raises(
        validate_live_thread.NonRetryableValidationError,
        match="budget exceeded",
    ):
        validate_live_thread.validate_trace(trace)


def test_accepts_bounded_user_research_trace() -> None:
    summary = validate_live_thread.validate_user_trace(valid_user_trace())

    assert summary == {
        "delegation_count": 1,
        "fetch_calls": 1,
        "search_calls": 1,
        "status": "ok",
        "tool_calls": 4,
        "uris": ["https://research.fixture.test/sources/five-layer-stack"],
    }


def test_user_trace_requires_researcher_delegation() -> None:
    trace = valid_user_trace()
    trace[0]["tool_calls"] = [{"name": "task", "args": {"subagent_type": "general-purpose"}}]

    with pytest.raises(validate_live_thread.ValidationError, match="researcher subagent"):
        validate_live_thread.validate_user_trace(trace)


def test_user_trace_requires_delegation_from_orchestrator() -> None:
    trace = valid_user_trace()
    trace[0]["name"] = "researcher"

    with pytest.raises(validate_live_thread.NonRetryableValidationError, match="orchestrator"):
        validate_live_thread.validate_user_trace(trace)


def test_user_trace_rejects_direct_orchestrator_research_call() -> None:
    trace = valid_user_trace()
    trace[2]["name"] = "agent"

    with pytest.raises(validate_live_thread.ValidationError, match="called by the researcher"):
        validate_live_thread.validate_user_trace(trace)


@pytest.mark.parametrize(
    "arguments",
    [
        None,
        {"query": "", "limit": 3},
        {"query": "x" * 201, "limit": 3},
        {"query": "bounded", "limit": True},
        {"query": "bounded", "limit": 0},
        {"query": "bounded", "limit": 6},
    ],
)
def test_user_trace_rejects_unbounded_search_arguments(arguments: object) -> None:
    trace = valid_user_trace()
    trace[2]["tool_calls"][0]["args"] = arguments

    with pytest.raises(validate_live_thread.ValidationError, match="bounded contract"):
        validate_live_thread.validate_user_trace(trace)


@pytest.mark.parametrize(
    "uri",
    [
        "http://research.fixture.test/sources/five-layer-stack",
        "https://example.com/sources/five-layer-stack",
        "https://research.fixture.test:443/sources/five-layer-stack",
        "https://user@research.fixture.test/sources/five-layer-stack",
        "https://research.fixture.test/sources/../secret",
        "https://research.fixture.test/sources/_bad",
        "https://research.fixture.test/sources/five-layer-stack?redirect=evil",
    ],
)
def test_user_trace_rejects_non_fixture_fetch_uri(uri: str) -> None:
    trace = valid_user_trace()
    trace[3]["tool_calls"][0]["args"]["uri"] = uri

    with pytest.raises(
        validate_live_thread.NonRetryableValidationError,
        match="canonical fixture URI",
    ):
        validate_live_thread.validate_user_trace(trace)


def test_user_trace_requires_fetched_uri_in_final_answer() -> None:
    trace = valid_user_trace()
    final = json.loads(trace[-1]["content"])
    final.pop("uri")
    trace[-1]["content"] = json.dumps(final)

    with pytest.raises(validate_live_thread.NonRetryableValidationError, match="omitted"):
        validate_live_thread.validate_user_trace(trace)


def test_user_trace_requires_successful_tool_results() -> None:
    trace = valid_user_trace()
    fetch_result = next(
        record
        for record in trace
        if record.get("kind") == "ToolMessage" and record.get("name") == "research_research.fetch"
    )
    fetch_result["status"] = "error"

    with pytest.raises(validate_live_thread.ValidationError, match="complete successfully"):
        validate_live_thread.validate_user_trace(trace)


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "wrong-name"])
def test_user_trace_correlates_each_tool_result(mutation: str) -> None:
    trace = valid_user_trace()
    search_result = next(
        record
        for record in trace
        if record.get("kind") == "ToolMessage" and record.get("name") == "research_research.search"
    )
    if mutation == "missing":
        trace.remove(search_result)
        expected = "no persisted result"
    elif mutation == "duplicate":
        trace.insert(-1, copy.deepcopy(search_result))
        expected = "multiple persisted results"
    else:
        search_result["name"] = "research_research.fetch"
        expected = "does not match"

    with pytest.raises(validate_live_thread.ValidationError, match=expected):
        validate_live_thread.validate_user_trace(trace)


def test_user_trace_requires_fetch_uri_from_search_result() -> None:
    trace = valid_user_trace()
    search_result = next(
        record
        for record in trace
        if record.get("kind") == "ToolMessage" and record.get("name") == "research_research.search"
    )
    search_result["content"] = {
        "query": "Jensen Huang five layers",
        "results": [],
        "status": "ok",
    }

    with pytest.raises(validate_live_thread.NonRetryableValidationError, match="not returned"):
        validate_live_thread.validate_user_trace(trace)


def test_user_trace_rejects_invalid_search_result_provenance() -> None:
    trace = valid_user_trace()
    search_result = next(
        record
        for record in trace
        if record.get("kind") == "ToolMessage" and record.get("name") == "research_research.search"
    )
    search_result["content"] = {
        "query": "Jensen Huang five layers",
        "results": [
            {
                "source_id": "forged",
                "uri": "https://research.fixture.test/sources/five-layer-stack",
            }
        ],
        "status": "ok",
    }

    with pytest.raises(
        validate_live_thread.NonRetryableValidationError,
        match="invalid fixture provenance",
    ):
        validate_live_thread.validate_user_trace(trace)


@pytest.mark.parametrize(
    "payload",
    [
        {"status": "error"},
        {
            "content": "",
            "injection_detected": False,
            "source_id": "five-layer-stack",
            "status": "ok",
            "uri": "https://research.fixture.test/sources/five-layer-stack",
        },
        {
            "content": "x" * 4097,
            "injection_detected": False,
            "source_id": "five-layer-stack",
            "status": "ok",
            "uri": "https://research.fixture.test/sources/five-layer-stack",
        },
        {
            "content": "bounded",
            "injection_detected": "false",
            "source_id": "five-layer-stack",
            "status": "ok",
            "uri": "https://research.fixture.test/sources/five-layer-stack",
        },
    ],
)
def test_user_trace_rejects_invalid_fetch_result(payload: dict[str, object]) -> None:
    trace = valid_user_trace()
    fetch_result = next(
        record
        for record in trace
        if record.get("kind") == "ToolMessage" and record.get("name") == "research_research.fetch"
    )
    fetch_result["content"] = payload

    expected_error = (
        validate_live_thread.ValidationError
        if payload.get("status") != "ok" or not payload.get("content")
        else validate_live_thread.NonRetryableValidationError
    )
    with pytest.raises(expected_error, match="bounded evidence"):
        validate_live_thread.validate_user_trace(trace)


@pytest.mark.parametrize("content", ["", "x" * 8193, ["not", "text"]])
def test_user_trace_rejects_invalid_final_answer(content: object) -> None:
    trace = valid_user_trace()
    trace[-1]["content"] = content

    expected_error = (
        validate_live_thread.NonRetryableValidationError
        if isinstance(content, str) and len(content.encode("utf-8")) > 8192
        else validate_live_thread.ValidationError
    )
    with pytest.raises(expected_error, match="final"):
        validate_live_thread.validate_user_trace(trace)


@pytest.mark.parametrize(
    ("tool_name", "error"),
    [
        ("task", "delegation"),
        ("research_research.search", r"research\.search"),
        ("research_research.fetch", r"research\.fetch"),
    ],
)
def test_user_trace_requires_each_topology_call(tool_name: str, error: str) -> None:
    trace = valid_user_trace()
    call_record = next(
        record
        for record in trace
        if any(call.get("name") == tool_name for call in record.get("tool_calls", []))
    )
    trace.remove(call_record)

    with pytest.raises(validate_live_thread.ValidationError, match=error):
        validate_live_thread.validate_user_trace(trace)


def test_user_trace_rejects_tool_budget_overrun() -> None:
    trace = valid_user_trace()
    discovery = trace[1]
    for index in range(5):
        duplicate = copy.deepcopy(discovery)
        duplicate["tool_calls"][0]["id"] = f"extra-discovery-{index}"
        trace.insert(-1, duplicate)

    with pytest.raises(validate_live_thread.NonRetryableValidationError, match="budget"):
        validate_live_thread.validate_user_trace(trace)


@pytest.mark.parametrize(
    ("contract", "records"),
    [
        ("live-gate", valid_trace()),
        ("user", valid_user_trace()),
    ],
)
def test_cli_dispatches_each_trace_contract(
    contract: str,
    records: list[dict[str, object]],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        validate_live_thread,
        "_message_records",
        lambda _database, _thread_id: records,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["validate_live_thread.py", "--thread-id", "thread-1", "--contract", contract],
    )

    assert validate_live_thread.main() == 0
    assert json.loads(capsys.readouterr().out)["status"] == "ok"


def test_cli_uses_distinct_exit_for_non_retryable_violation(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    trace = valid_user_trace()
    trace.insert(
        -1,
        {
            "kind": "AIMessage",
            "name": "researcher",
            "content": "",
            "tool_calls": [{"id": "shell-call", "name": "shell", "args": {}}],
        },
    )
    monkeypatch.setattr(
        validate_live_thread,
        "_message_records",
        lambda _database, _thread_id: trace,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["validate_live_thread.py", "--thread-id", "thread-1", "--contract", "user"],
    )

    assert validate_live_thread.main() == 3
    assert "forbidden tools" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("source_id", "forged", "fixture provenance"),
        ("injection_detected", True, "injection signal"),
    ],
)
def test_cli_returns_nonretryable_exit_for_exact_final_integrity(
    field: str,
    value: object,
    message: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    trace = valid_trace()
    final = json.loads(trace[-1]["content"])
    final[field] = value
    trace[-1]["content"] = json.dumps(final)
    monkeypatch.setattr(
        validate_live_thread,
        "_message_records",
        lambda _database, _thread_id: trace,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["validate_live_thread.py", "--thread-id", "thread-1"],
    )

    assert validate_live_thread.main() == 3
    assert message in capsys.readouterr().err


def test_cli_reports_retryable_trace_failure(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        validate_live_thread,
        "_message_records",
        lambda _database, _thread_id: [],
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["validate_live_thread.py", "--thread-id", "thread-1", "--contract", "user"],
    )

    assert validate_live_thread.main() == 1
    assert "expected exactly one researcher delegation" in capsys.readouterr().err


@pytest.mark.parametrize(
    "content",
    [
        "not-json",
        [],
        [{"type": "image", "data": "ignored"}],
        42,
    ],
)
def test_mcp_payload_rejects_unsupported_content(content: object) -> None:
    with pytest.raises(validate_live_thread.ValidationError, match="MCP result"):
        validate_live_thread._mcp_payload(content)


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

    with pytest.raises(
        validate_live_thread.NonRetryableValidationError,
        match="fixture provenance",
    ):
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
