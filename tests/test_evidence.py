import json

from open_agent_system.evidence import (
    EvidenceRecord,
    bound_evidence,
    serialize_trace,
    truncate_utf8,
)
from open_agent_system.settings import AgentLimits


def test_utf8_truncation_never_emits_a_partial_character() -> None:
    value, truncated = truncate_utf8("ab🙂cd", 5)
    assert value == "ab"
    assert truncated is True


def test_evidence_is_redacted_and_bounded() -> None:
    record = EvidenceRecord.bounded(
        source_id="source-1",
        uri="fixture://source-1",
        title="Safe",
        excerpt="api_key=synthetic-redaction-canary " + ("x" * 100),
        max_bytes=32,
    )
    assert "nvapi" not in record.excerpt
    assert len(record.excerpt.encode()) <= 32
    assert record.truncated is True


def test_record_count_is_bounded() -> None:
    records = [
        EvidenceRecord.bounded(
            source_id=str(index), uri=f"fixture://{index}", title="t", excerpt="e"
        )
        for index in range(3)
    ]
    bounded, truncated = bound_evidence(records, AgentLimits(evidence_records=2))
    assert len(bounded) == 2
    assert truncated is True


def test_trace_redacts_nested_values_and_replaces_oversized_payload() -> None:
    encoded = serialize_trace({"nested": ["authorization: Bearer secret-value"]})
    assert b"secret-value" not in encoded
    assert b"REDACTED" in encoded

    secret_key = serialize_trace({"authorization: Bearer secret-value": "safe"})
    assert b"secret-value" not in secret_key

    oversized = serialize_trace({"body": "x" * 1000}, max_bytes=100)
    decoded = json.loads(oversized)
    assert decoded["status"] == "trace_truncated"
    assert len(oversized) <= 100
