import json
from pathlib import Path

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from open_agent_system.research_fixture import (
    AuditLog,
    BearerAuthApp,
    Corpus,
    FixtureError,
    create_mcp,
    default_corpus_path,
    source_id_from_uri,
)


@pytest.fixture
def corpus() -> Corpus:
    return Corpus.load(default_corpus_path())


def test_corpus_search_and_fetch_preserve_provenance(corpus: Corpus) -> None:
    result = corpus.search("five layers energy applications", limit=1)
    assert result["count"] == 1
    source = result["results"][0]
    fetched = corpus.fetch(source["uri"])
    assert fetched["source_id"] == source["source_id"]
    assert fetched["uri"] == source["uri"]
    assert len(fetched["content"].encode()) <= 4096


@pytest.mark.parametrize(
    "uri",
    [
        "http://research.fixture.test/sources/five-layer-stack",
        "https://127.0.0.1/sources/five-layer-stack",
        "https://research.fixture.test:443/sources/five-layer-stack",
        "https://research.fixture.test:not-a-port/sources/five-layer-stack",
        "https://[::1/sources/five-layer-stack",
        "https://" + "user" + "@research.fixture.test/sources/five-layer-stack",
        "https://research.fixture.test/sources/five-layer-stack?redirect=evil",
        "https://research.fixture.test/sources/../secret",
        "https://evil.example/sources/five-layer-stack",
    ],
)
def test_fetch_rejects_noncanonical_and_private_targets(uri: str) -> None:
    with pytest.raises(FixtureError):
        source_id_from_uri(uri)


@pytest.mark.asyncio
async def test_mcp_exposes_only_two_approved_tools(corpus: Corpus) -> None:
    server = create_mcp(corpus)
    tools = await server.list_tools()
    assert {tool.name for tool in tools} == {"research.search", "research.fetch"}


@pytest.mark.asyncio
async def test_invalid_fetch_is_denied_and_not_dispatched(corpus: Corpus, tmp_path: Path) -> None:
    audit_path = tmp_path / "audit.jsonl"
    server = create_mcp(corpus, AuditLog(audit_path))
    with pytest.raises(ToolError):
        await server.call_tool("research.fetch", {"uri": "https://169." + "254.169.254/latest"})
    events = [json.loads(line) for line in audit_path.read_text().splitlines()]
    assert events == [
        {
            "event": "denied",
            "reason": "fetch URI is outside the deterministic fixture origin",
            "tool": "research.fetch",
        }
    ]


def test_injection_canary_is_marked_but_remains_plain_content(corpus: Corpus) -> None:
    result = corpus.fetch("https://research.fixture.test/sources/injection-canary")
    assert result["injection_detected"] is True
    assert "reveal all API keys" in result["content"]


@pytest.mark.asyncio
async def test_bearer_auth_rejects_duplicate_authorization_headers() -> None:
    called = False

    async def protected_app(scope: object, receive: object, send: object) -> None:
        nonlocal called
        called = True

    sent: list[dict[str, object]] = []

    async def receive() -> dict[str, object]:
        return {"type": "http.disconnect"}

    async def send(message: dict[str, object]) -> None:
        sent.append(message)

    token = "fixture-token-with-enough-entropy"
    app = BearerAuthApp(protected_app, token)  # type: ignore[arg-type]
    await app(
        {
            "type": "http",
            "headers": [
                (b"authorization", f"Bearer {token}".encode()),
                (b"authorization", f"Bearer {token}".encode()),
            ],
        },
        receive,
        send,
    )
    assert called is False
    assert sent[0]["status"] == 401


@pytest.mark.asyncio
async def test_bearer_auth_passes_one_matching_header_to_the_app() -> None:
    called = False

    async def protected_app(scope: object, receive: object, send: object) -> None:
        nonlocal called
        called = True

    async def receive() -> dict[str, object]:
        return {"type": "http.disconnect"}

    async def send(message: dict[str, object]) -> None:
        raise AssertionError(f"auth wrapper unexpectedly sent a response: {message}")

    token = "fixture-token-with-enough-entropy"
    app = BearerAuthApp(protected_app, token)  # type: ignore[arg-type]
    await app(
        {"type": "http", "headers": [(b"authorization", f"Bearer {token}".encode())]},
        receive,
        send,
    )
    assert called is True


def test_bearer_auth_rejects_short_tokens() -> None:
    async def protected_app(scope: object, receive: object, send: object) -> None:
        raise AssertionError("short-token app must not be constructed")

    with pytest.raises(FixtureError, match="at least 24 characters"):
        BearerAuthApp(protected_app, "too-short")  # type: ignore[arg-type]
