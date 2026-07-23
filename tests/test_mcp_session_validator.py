from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).parents[1] / "integrations" / "nemoclaw" / "validate_mcp_session.py"
SPEC = importlib.util.spec_from_file_location("validate_mcp_session", SCRIPT_PATH)
assert SPEC and SPEC.loader
validate_mcp_session = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validate_mcp_session)


def test_accepts_exact_research_tool_set() -> None:
    summary = validate_mcp_session.validate_tool_names(["research.search", "research.fetch"])

    assert summary == {
        "status": "ok",
        "tools": ["research.fetch", "research.search"],
    }


def test_normalizes_nemoclaw_http_config_for_langchain() -> None:
    raw = {
        "type": "http",
        "url": "https://fixture.example/mcp",
        "headers": {"Authorization": "Bearer openshell:resolve:env:TOKEN"},
    }

    connection = validate_mcp_session.normalize_connection(raw)

    assert connection == {
        "transport": "streamable_http",
        "url": "https://fixture.example/mcp",
        "headers": {"Authorization": "Bearer openshell:resolve:env:TOKEN"},
    }
    assert raw["type"] == "http"


def test_rejects_non_http_connection() -> None:
    with pytest.raises(validate_mcp_session.ValidationError, match="Streamable HTTP"):
        validate_mcp_session.normalize_connection({"type": "stdio"})


@pytest.mark.parametrize(
    "names",
    [
        ["research.search"],
        ["research.search", "research.fetch", "filesystem.read"],
        ["research.search", "research.search", "research.fetch"],
    ],
)
def test_rejects_missing_extra_or_duplicate_tools(names: list[str]) -> None:
    with pytest.raises(validate_mcp_session.ValidationError):
        validate_mcp_session.validate_tool_names(names)
