import pytest

from open_agent_system.settings import AgentLimits, SettingsError


def test_default_limits_match_reviewed_policy() -> None:
    limits = AgentLimits()
    assert limits.delegations == 1
    assert limits.model_turns == 12
    assert limits.tool_calls == 8
    assert limits.wall_time_seconds == 180
    assert limits.evidence_records == 10


def test_cli_style_overrides_can_only_lower_limits() -> None:
    limits = AgentLimits().lowered(tool_calls=3, wall_time_seconds=60)
    assert limits.tool_calls == 3
    with pytest.raises(SettingsError, match="cannot exceed"):
        limits.lowered(tool_calls=4)


@pytest.mark.parametrize("value", [0, -1, True, 1.5])
def test_invalid_limits_fail_closed(value: object) -> None:
    with pytest.raises(SettingsError):
        AgentLimits(tool_calls=value)  # type: ignore[arg-type]
