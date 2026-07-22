from pathlib import Path

import yaml

EXPECTED_IDS = {
    "CFG-001",
    "AGT-001",
    "AGT-002",
    "MCP-001",
    "MCP-002",
    "NET-001",
    "HITL-001",
    "HITL-002",
    "TOOL-001",
    "BUD-001",
    "TRC-001",
    "FLOW-001",
    "FLOW-002",
    "SEC-001",
    "SEC-002",
    "FAIL-001",
}


def test_all_reviewed_cases_are_executable_contracts() -> None:
    cases_dir = Path(__file__).resolve().parents[1] / "evals/cases"
    cases: list[dict[str, object]] = []
    for path in sorted(cases_dir.glob("*.yaml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        cases.extend(document["cases"])

    ids = [case["id"] for case in cases]
    assert len(ids) == len(set(ids))
    assert set(ids) == EXPECTED_IDS
    assert all(case.get("tier") and case.get("invariant") for case in cases)
