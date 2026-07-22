from pathlib import Path

from open_agent_system.cli import verify_profile


def test_checked_in_profile_is_valid() -> None:
    root = Path(__file__).resolve().parents[1]
    result = verify_profile(root)
    assert result["status"] == "ok", result["failures"]
    assert result["route"] == {
        "provider": "nvidia-prod",
        "model": "nvidia/nemotron-3-ultra-550b-a55b",
    }


def test_missing_profile_fails_before_launch(tmp_path: Path) -> None:
    result = verify_profile(tmp_path)
    assert result["status"] == "failed"
    assert result["failures"]
