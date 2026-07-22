import json
from pathlib import Path

import pytest

from open_agent_system.cli import _read_frontmatter, main, verify_profile


def test_frontmatter_reader_fails_closed(tmp_path: Path) -> None:
    plain = tmp_path / "plain.md"
    plain.write_text("no frontmatter\n", encoding="utf-8")
    assert _read_frontmatter(plain) == {}

    incomplete = tmp_path / "incomplete.md"
    incomplete.write_text("---\nname: incomplete\n", encoding="utf-8")
    assert _read_frontmatter(incomplete) == {}

    sequence = tmp_path / "sequence.md"
    sequence.write_text("---\n- not\n- a mapping\n---\n", encoding="utf-8")
    assert _read_frontmatter(sequence) == {}


def test_verify_profile_reports_invalid_checked_in_contracts(tmp_path: Path) -> None:
    for relative in (
        "AGENTS.md",
        ".deepagents/AGENTS.md",
        ".deepagents/agents/researcher/AGENTS.md",
        ".deepagents/skills/agent-retrieval/SKILL.md",
        ".deepagents/skills/agent-retrieval/agents/openai.yaml",
    ):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("invalid\n", encoding="utf-8")

    known_good = tmp_path / "integrations/nemoclaw/known-good.json"
    known_good.parent.mkdir(parents=True)
    known_good.write_text('{"live_contract": []}', encoding="utf-8")

    result = verify_profile(tmp_path)
    assert result["status"] == "failed"
    assert set(result["failures"]) == {
        "invalid:researcher-frontmatter",
        "invalid:agent-retrieval-frontmatter",
        "invalid:known-good-route",
    }

    known_good.write_text("not json", encoding="utf-8")
    assert "invalid:known-good-json" in verify_profile(tmp_path)["failures"]


def test_cli_verify_emits_json_and_success_exit(capsys: pytest.CaptureFixture[str]) -> None:
    root = Path(__file__).resolve().parents[1]
    with pytest.raises(SystemExit, match="0"):
        main(["verify", "--root", str(root), "--json"])
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "ok"


def test_cli_evaluate_trace_handles_valid_and_invalid_input(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    valid = tmp_path / "valid.json"
    valid.write_text('{"events": [], "final": "bounded"}', encoding="utf-8")
    with pytest.raises(SystemExit, match="0"):
        main(["evaluate-trace", str(valid)])
    assert capsys.readouterr().out == "trace: passed\n"

    invalid_root = tmp_path / "invalid-root.json"
    invalid_root.write_text("[]", encoding="utf-8")
    with pytest.raises(SystemExit, match="1"):
        main(["evaluate-trace", str(invalid_root), "--json"])
    assert json.loads(capsys.readouterr().out)["violations"] == ["trace.root.invalid"]

    unreadable = tmp_path / "missing.json"
    with pytest.raises(SystemExit, match="1"):
        main(["evaluate-trace", str(unreadable)])
    assert "trace.read_failed:" in capsys.readouterr().out
