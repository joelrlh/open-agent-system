from __future__ import annotations

import ast
import copy
import importlib.util
import json
import sqlite3
import sys
import types
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


def _set_fetch_injection(trace: list[dict[str, object]], detected: bool) -> None:
    fetch_result = next(
        record
        for record in trace
        if record.get("kind") == "ToolMessage" and record.get("name") == "research_research.fetch"
    )
    outer = ast.literal_eval(fetch_result["content"])
    payload = json.loads(outer[0]["text"])
    payload["injection_detected"] = detected
    outer[0]["text"] = json.dumps(payload)
    fetch_result["content"] = repr(outer)


def _runtime_failure(code: str) -> dict[str, object]:
    return {
        "kind": "RuntimeError",
        "name": "runtime",
        "content": code,
        "status": "error",
        "tool_call_id": None,
        "tool_calls": [],
    }


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


@pytest.mark.parametrize(
    "validator",
    [validate_live_thread.validate_trace, validate_live_thread.validate_user_trace],
)
def test_trace_rejects_orphan_tool_result(validator: object) -> None:
    trace = valid_trace()
    trace.insert(
        -1,
        {
            "kind": "ToolMessage",
            "name": "search_tools",
            "content": "orphaned discovery",
            "status": "success",
            "tool_call_id": "orphan-call",
            "tool_calls": [],
        },
    )

    with pytest.raises(
        validate_live_thread.NonRetryableValidationError,
        match="no corresponding tool call",
    ):
        validator(trace)


@pytest.mark.parametrize(
    "validator",
    [validate_live_thread.validate_trace, validate_live_thread.validate_user_trace],
)
def test_trace_rejects_tool_activity_after_final_answer(validator: object) -> None:
    trace = valid_trace()
    trace.extend(
        [
            {
                "kind": "AIMessage",
                "name": "researcher",
                "content": "",
                "tool_calls": [
                    {
                        "id": "late-discovery",
                        "name": "search_tools",
                        "args": {"query": "research"},
                    }
                ],
            },
            {
                "kind": "ToolMessage",
                "name": "search_tools",
                "content": "late discovery",
                "status": "success",
                "tool_call_id": "late-discovery",
                "tool_calls": [],
            },
        ]
    )

    with pytest.raises(
        validate_live_thread.NonRetryableValidationError,
        match="after the final orchestrator answer",
    ):
        validator(trace)


@pytest.mark.parametrize(
    "validator",
    [validate_live_thread.validate_trace, validate_live_thread.validate_user_trace],
)
def test_trace_rejects_tool_result_after_final_answer(validator: object) -> None:
    trace = valid_trace()
    search_result = next(
        record
        for record in trace
        if record.get("kind") == "ToolMessage" and record.get("name") == "research_research.search"
    )
    trace.remove(search_result)
    trace.append(search_result)

    with pytest.raises(
        validate_live_thread.NonRetryableValidationError,
        match="after the final orchestrator answer",
    ):
        validator(trace)


@pytest.mark.parametrize(
    "validator",
    [validate_live_thread.validate_trace, validate_live_thread.validate_user_trace],
)
def test_trace_rejects_research_before_delegation(validator: object) -> None:
    trace = valid_trace()
    trace[0], trace[1] = trace[1], trace[0]

    with pytest.raises(
        validate_live_thread.NonRetryableValidationError,
        match="before orchestrator delegation",
    ):
        validator(trace)


@pytest.mark.parametrize(
    "validator",
    [validate_live_thread.validate_trace, validate_live_thread.validate_user_trace],
)
def test_trace_rejects_fetch_before_search(validator: object) -> None:
    trace = valid_trace()
    trace[2], trace[3] = trace[3], trace[2]

    with pytest.raises(
        validate_live_thread.NonRetryableValidationError,
        match=r"research\.fetch occurred before research\.search",
    ):
        validator(trace)


@pytest.mark.parametrize(
    "validator",
    [validate_live_thread.validate_trace, validate_live_thread.validate_user_trace],
)
def test_trace_accepts_bounded_task_focused_root_discovery(validator: object) -> None:
    trace = valid_trace()
    trace.insert(
        0,
        {
            "kind": "AIMessage",
            "name": "agent",
            "content": "",
            "tool_calls": [
                {
                    "id": "root-discovery",
                    "name": "search_tools",
                    "args": {"query": "task delegation"},
                }
            ],
        },
    )
    trace.insert(
        -1,
        {
            "kind": "ToolMessage",
            "name": "search_tools",
            "content": "bounded task discovery",
            "status": "success",
            "tool_call_id": "root-discovery",
            "tool_calls": [],
        },
    )

    assert validator(trace)["status"] == "ok"


@pytest.mark.parametrize(
    ("owner", "query"),
    [
        ("agent", "research"),
        ("researcher", "task"),
        ("agent", "task research.search shell.exec filesystem.read"),
        ("researcher", "research shell.exec filesystem.read"),
    ],
)
@pytest.mark.parametrize(
    "validator",
    [validate_live_thread.validate_trace, validate_live_thread.validate_user_trace],
)
def test_trace_rejects_out_of_scope_tool_discovery(
    validator: object, owner: str, query: str
) -> None:
    trace = valid_trace()
    discovery = next(
        record
        for record in trace
        if record.get("kind") == "AIMessage"
        and record.get("name") == "researcher"
        and any(call.get("name") == "search_tools" for call in record.get("tool_calls", []))
    )
    discovery["name"] = owner
    discovery["tool_calls"][0]["args"]["query"] = query

    with pytest.raises(
        validate_live_thread.NonRetryableValidationError,
        match=r"discovery scope|tool sequence",
    ):
        validator(trace)


@pytest.mark.parametrize(
    "validator",
    [validate_live_thread.validate_trace, validate_live_thread.validate_user_trace],
)
def test_trace_rejects_direct_orchestrator_research_without_delegation(
    validator: object,
) -> None:
    trace = valid_trace()
    task_call = trace.pop(0)
    task_call_id = task_call["tool_calls"][0]["id"]
    trace = [record for record in trace if record.get("tool_call_id") != task_call_id]
    trace[1]["name"] = "agent"

    with pytest.raises(
        validate_live_thread.NonRetryableValidationError,
        match="called by the researcher",
    ):
        validator(trace)


@pytest.mark.parametrize(
    ("raw_error", "code"),
    [
        (
            "APIError('ResourceExhausted: Worker local total request limit reached')",
            "provider_capacity_exhausted",
        ),
        ("TimeoutError('model timed out')", "runtime_timeout"),
        ("APIError('provider rejected request')", "provider_api_error"),
        ("secret-shaped unexpected internal detail", "managed_runtime_error"),
    ],
)
def test_runtime_failure_codes_do_not_preserve_untrusted_error_text(
    raw_error: str, code: str
) -> None:
    assert validate_live_thread._runtime_failure_code(raw_error) == code
    assert raw_error not in code


def test_message_records_sanitizes_persisted_runtime_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FakeMessage:
        def __init__(self) -> None:
            self.name = "agent"
            self.content = "bounded final"
            self.status = None
            self.tool_call_id = None
            self.tool_calls: list[dict[str, object]] = []

    class FakeSerializer:
        def loads_typed(self, value: tuple[str, bytes]) -> object:
            if value[0] == "message":
                return FakeMessage()
            return value[1].decode("utf-8")

    jsonplus = types.ModuleType("langgraph.checkpoint.serde.jsonplus")
    jsonplus.JsonPlusSerializer = FakeSerializer
    monkeypatch.setitem(sys.modules, "langgraph", types.ModuleType("langgraph"))
    monkeypatch.setitem(sys.modules, "langgraph.checkpoint", types.ModuleType("checkpoint"))
    monkeypatch.setitem(sys.modules, "langgraph.checkpoint.serde", types.ModuleType("serde"))
    monkeypatch.setitem(sys.modules, "langgraph.checkpoint.serde.jsonplus", jsonplus)

    database = tmp_path / "sessions.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            CREATE TABLE writes (
                thread_id TEXT NOT NULL,
                channel TEXT NOT NULL,
                type TEXT,
                value BLOB
            )
            """
        )
        connection.execute(
            "INSERT INTO writes VALUES (?, ?, ?, ?)",
            ("thread-1", "messages", "message", b"ignored"),
        )
        connection.execute(
            "INSERT INTO writes VALUES (?, ?, ?, ?)",
            (
                "thread-1",
                "__error__",
                "str",
                b"APIError('ResourceExhausted: secret-shaped provider detail')",
            ),
        )

    records = validate_live_thread._message_records(database, "thread-1")

    assert records == [
        {
            "kind": "FakeMessage",
            "name": "agent",
            "content": "bounded final",
            "status": None,
            "tool_call_id": None,
            "tool_calls": [],
        },
        _runtime_failure("provider_capacity_exhausted"),
    ]
    assert "secret-shaped provider detail" not in json.dumps(records)


@pytest.mark.parametrize(
    "validator",
    [validate_live_thread.validate_trace, validate_live_thread.validate_user_trace],
)
def test_trace_reports_sanitized_persisted_runtime_failure(validator: object) -> None:
    trace = valid_trace()
    trace.pop()
    trace.append(_runtime_failure("provider_capacity_exhausted"))

    with pytest.raises(
        validate_live_thread.ValidationError,
        match="persisted managed runtime failure: provider_capacity_exhausted",
    ):
        validator(trace)


def test_persisted_runtime_failure_codes_are_sorted_and_deduplicated() -> None:
    trace = [
        _runtime_failure("runtime_timeout"),
        _runtime_failure("provider_api_error"),
        _runtime_failure("runtime_timeout"),
    ]

    with pytest.raises(
        validate_live_thread.ValidationError,
        match="provider_api_error, runtime_timeout",
    ):
        validate_live_thread._raise_persisted_runtime_failure(trace)


def test_authority_violation_precedes_persisted_runtime_failure() -> None:
    trace = valid_user_trace()
    trace[2]["name"] = "agent"
    trace.insert(-1, _runtime_failure("provider_capacity_exhausted"))

    with pytest.raises(
        validate_live_thread.NonRetryableValidationError,
        match="called by the researcher",
    ):
        validate_live_thread.validate_user_trace(trace)


@pytest.mark.parametrize(
    "validator",
    [validate_live_thread.validate_trace, validate_live_thread.validate_user_trace],
)
def test_search_budget_violation_precedes_persisted_runtime_failure(
    validator: object,
) -> None:
    trace = valid_trace()
    duplicate = copy.deepcopy(trace[2])
    duplicate["tool_calls"][0]["id"] = "duplicate-search"
    trace.insert(3, duplicate)
    trace.insert(-1, _runtime_failure("provider_capacity_exhausted"))

    with pytest.raises(
        validate_live_thread.NonRetryableValidationError,
        match=r"research\.search budget exceeded",
    ):
        validator(trace)


def test_exact_argument_violation_precedes_persisted_runtime_failure() -> None:
    trace = valid_trace()
    trace[3]["tool_calls"][0]["args"]["uri"] = "https://example.com/private"
    trace.insert(-1, _runtime_failure("provider_capacity_exhausted"))

    with pytest.raises(
        validate_live_thread.NonRetryableValidationError,
        match="canonical fixture URI",
    ):
        validate_live_thread.validate_trace(trace)


def test_user_argument_violation_precedes_persisted_runtime_failure() -> None:
    trace = valid_user_trace()
    trace[2]["tool_calls"][0]["args"]["limit"] = 999
    trace.insert(-1, _runtime_failure("provider_capacity_exhausted"))

    with pytest.raises(
        validate_live_thread.NonRetryableValidationError,
        match="bounded contract",
    ):
        validate_live_thread.validate_user_trace(trace)


@pytest.mark.parametrize(
    "validator",
    [validate_live_thread.validate_trace, validate_live_thread.validate_user_trace],
)
def test_forged_result_precedes_persisted_runtime_failure(validator: object) -> None:
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
    trace.insert(-1, _runtime_failure("provider_capacity_exhausted"))

    with pytest.raises(
        validate_live_thread.NonRetryableValidationError,
        match=r"provenance|canonical evidence",
    ):
        validator(trace)


def test_exact_forged_final_precedes_persisted_runtime_failure() -> None:
    trace = valid_trace()
    final = json.loads(trace[-1]["content"])
    final["source_id"] = "forged"
    trace[-1]["content"] = json.dumps(final)
    trace.insert(-1, _runtime_failure("provider_capacity_exhausted"))

    with pytest.raises(
        validate_live_thread.NonRetryableValidationError,
        match="provenance",
    ):
        validate_live_thread.validate_trace(trace)


def test_user_omitted_final_provenance_precedes_persisted_runtime_failure() -> None:
    trace = valid_user_trace()
    trace[-1]["content"] = "bounded answer without a source"
    trace.insert(-1, _runtime_failure("provider_capacity_exhausted"))

    with pytest.raises(
        validate_live_thread.NonRetryableValidationError,
        match="omitted",
    ):
        validate_live_thread.validate_user_trace(trace)


def test_user_trace_rejects_duplicate_fetch_uri() -> None:
    trace = valid_user_trace()
    fetch_call = copy.deepcopy(trace[3])
    fetch_call["tool_calls"][0]["id"] = "duplicate-fetch"
    fetch_result = copy.deepcopy(
        next(
            record
            for record in trace
            if record.get("kind") == "ToolMessage"
            and record.get("name") == "research_research.fetch"
        )
    )
    fetch_result["tool_call_id"] = "duplicate-fetch"
    task_result_index = next(
        index
        for index, record in enumerate(trace)
        if record.get("kind") == "ToolMessage" and record.get("name") == "task"
    )
    trace.insert(task_result_index, fetch_call)
    trace.insert(-1, fetch_result)

    with pytest.raises(
        validate_live_thread.NonRetryableValidationError,
        match=r"research\.fetch repeated",
    ):
        validate_live_thread.validate_user_trace(trace)


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
        "injection_detected": False,
        "search_calls": 1,
        "status": "ok",
        "tool_calls": 4,
        "uris": ["https://research.fixture.test/sources/five-layer-stack"],
    }


def test_user_trace_requires_final_injection_marker_for_flagged_evidence() -> None:
    trace = valid_user_trace()
    _set_fetch_injection(trace, True)

    with pytest.raises(
        validate_live_thread.NonRetryableValidationError,
        match="omitted the fetched prompt-injection signal",
    ):
        validate_live_thread.validate_user_trace(trace)


def test_user_trace_accepts_bound_injection_marker() -> None:
    trace = valid_user_trace()
    _set_fetch_injection(trace, True)
    trace[-1]["content"] += "\ninjection_detected: true"

    summary = validate_live_thread.validate_user_trace(trace)

    assert summary["injection_detected"] is True


def test_user_trace_rejects_unfounded_injection_marker() -> None:
    trace = valid_user_trace()
    trace[-1]["content"] += "\ninjection_detected: true"

    with pytest.raises(
        validate_live_thread.NonRetryableValidationError,
        match="absent from fetched evidence",
    ):
        validate_live_thread.validate_user_trace(trace)


def test_exact_trace_rejects_flagged_canonical_fetch() -> None:
    trace = valid_trace()
    _set_fetch_injection(trace, True)

    with pytest.raises(
        validate_live_thread.NonRetryableValidationError,
        match="canonical evidence",
    ):
        validate_live_thread.validate_trace(trace)


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
