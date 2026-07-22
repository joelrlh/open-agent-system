"""Bounded evidence and trace serialization with conservative secret redaction."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any

from .settings import AgentLimits

_REDACTED = "[REDACTED]"
_SECRET_PATTERNS = (
    re.compile(r"\bnvapi-[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"),
    re.compile(
        r"(?i)\b(api[_ -]?key|access[_ -]?token|authorization)\b\s*[:=]\s*"
        r"(?:bearer\s+)?[^\s,;]+"
    ),
)


def truncate_utf8(value: str, max_bytes: int) -> tuple[str, bool]:
    raw = value.encode("utf-8")
    if len(raw) <= max_bytes:
        return value, False
    clipped = raw[:max_bytes]
    while clipped:
        try:
            return clipped.decode("utf-8"), True
        except UnicodeDecodeError:
            clipped = clipped[:-1]
    return "", True


def redact_text(value: str) -> str:
    redacted = value
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub(_REDACTED, redacted)
    return redacted


@dataclass(frozen=True, slots=True)
class EvidenceRecord:
    source_id: str
    uri: str
    title: str
    excerpt: str
    injection_detected: bool = False
    truncated: bool = False

    @classmethod
    def bounded(
        cls,
        *,
        source_id: str,
        uri: str,
        title: str,
        excerpt: str,
        injection_detected: bool = False,
        max_bytes: int = 4 * 1024,
    ) -> EvidenceRecord:
        bounded_excerpt, truncated = truncate_utf8(redact_text(excerpt), max_bytes)
        return cls(
            source_id=redact_text(source_id),
            uri=redact_text(uri),
            title=redact_text(title),
            excerpt=bounded_excerpt,
            injection_detected=injection_detected,
            truncated=truncated,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def bound_evidence(
    records: Iterable[EvidenceRecord], limits: AgentLimits | None = None
) -> tuple[list[EvidenceRecord], bool]:
    active = limits or AgentLimits()
    materialized = list(records)
    return materialized[: active.evidence_records], len(materialized) > active.evidence_records


def _redact_tree(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, Mapping):
        return {redact_text(str(key)): _redact_tree(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_redact_tree(item) for item in value]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return redact_text(repr(value))


def serialize_trace(payload: Mapping[str, Any], max_bytes: int = 64 * 1024) -> bytes:
    """Serialize redacted trace data, replacing oversized payloads with a bounded marker."""

    cleaned = _redact_tree(payload)
    encoded = json.dumps(cleaned, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if len(encoded) <= max_bytes:
        return encoded

    marker = {
        "status": "trace_truncated",
        "original_bytes": len(encoded),
        "truncated": True,
    }
    bounded = json.dumps(marker, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if len(bounded) > max_bytes:
        raise ValueError("trace byte limit is too small for the truncation marker")
    return bounded
