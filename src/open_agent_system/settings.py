"""Validated, policy-bounded settings for the declarative agent profile."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace


class SettingsError(ValueError):
    """Raised when a setting would violate the reviewed policy bounds."""


@dataclass(frozen=True, slots=True)
class AgentLimits:
    delegations: int = 1
    model_turns: int = 12
    tool_calls: int = 8
    tool_timeout_seconds: int = 30
    wall_time_seconds: int = 180
    evidence_records: int = 10
    evidence_bytes: int = 4 * 1024
    final_result_bytes: int = 8 * 1024
    trace_bytes: int = 64 * 1024

    def __post_init__(self) -> None:
        for name, value in asdict(self).items():
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise SettingsError(f"{name} must be a positive integer")

    def lowered(self, **overrides: int) -> AgentLimits:
        """Return a profile with limits lowered, never widened."""

        current = asdict(self)
        unknown = sorted(set(overrides) - set(current))
        if unknown:
            raise SettingsError(f"unknown limit(s): {', '.join(unknown)}")

        for name, value in overrides.items():
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise SettingsError(f"{name} must be a positive integer")
            if value > current[name]:
                raise SettingsError(
                    f"{name} cannot exceed the policy value {current[name]} without review"
                )
        return replace(self, **overrides)

    def to_dict(self) -> dict[str, int]:
        return asdict(self)
