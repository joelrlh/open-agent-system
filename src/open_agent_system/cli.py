"""Repository verification CLI; this does not launch an agent runtime."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

from .evaluation import evaluate_trace
from .settings import AgentLimits

REQUIRED_PATHS = (
    "AGENTS.md",
    ".deepagents/AGENTS.md",
    ".deepagents/agents/researcher/AGENTS.md",
    ".deepagents/skills/agent-retrieval/SKILL.md",
    ".deepagents/skills/agent-retrieval/agents/openai.yaml",
    "integrations/nemoclaw/known-good.json",
)


def _read_frontmatter(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}
    try:
        _, block, _ = text.split("---", 2)
    except ValueError:
        return {}
    parsed = yaml.safe_load(block)
    return parsed if isinstance(parsed, dict) else {}


def verify_profile(root: Path) -> dict[str, Any]:
    failures: list[str] = []
    for relative in REQUIRED_PATHS:
        if not (root / relative).is_file():
            failures.append(f"missing:{relative}")

    researcher_path = root / ".deepagents/agents/researcher/AGENTS.md"
    if researcher_path.is_file():
        researcher = _read_frontmatter(researcher_path)
        if researcher.get("name") != "researcher" or not researcher.get("description"):
            failures.append("invalid:researcher-frontmatter")

    skill_path = root / ".deepagents/skills/agent-retrieval/SKILL.md"
    if skill_path.is_file():
        skill = _read_frontmatter(skill_path)
        if skill.get("name") != "agent-retrieval" or not skill.get("description"):
            failures.append("invalid:agent-retrieval-frontmatter")

    known_good_path = root / "integrations/nemoclaw/known-good.json"
    route: dict[str, Any] = {}
    if known_good_path.is_file():
        try:
            known_good = json.loads(known_good_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            failures.append("invalid:known-good-json")
        else:
            live_contract = known_good.get("live_contract", {})
            if not isinstance(live_contract, dict):
                live_contract = {}
            route = {
                "provider": live_contract.get("inference_provider"),
                "model": live_contract.get("inference_model"),
            }
            if not all(route.values()):
                failures.append("invalid:known-good-route")

    return {
        "schema_version": 1,
        "status": "ok" if not failures else "failed",
        "failures": failures,
        "limits": AgentLimits().to_dict(),
        "route": route,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="open-agent-system")
    subparsers = parser.add_subparsers(dest="command", required=True)
    verify = subparsers.add_parser("verify", help="validate the checked-in project profile")
    verify.add_argument("--root", type=Path, default=Path.cwd())
    verify.add_argument("--json", action="store_true", dest="as_json")
    evaluate = subparsers.add_parser(
        "evaluate-trace", help="evaluate a recorded JSON trace against safety invariants"
    )
    evaluate.add_argument("trace", type=Path)
    evaluate.add_argument("--json", action="store_true", dest="as_json")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = _build_parser().parse_args(argv)
    if args.command == "verify":
        result = verify_profile(args.root.resolve())
        passed = result["status"] == "ok"
    else:
        try:
            trace = json.loads(args.trace.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            result = {"passed": False, "violations": [f"trace.read_failed:{exc}"]}
        else:
            if not isinstance(trace, dict):
                result = {"passed": False, "violations": ["trace.root.invalid"]}
            else:
                result = evaluate_trace(trace).to_dict()
        passed = bool(result["passed"])
    if args.as_json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        if args.command == "verify":
            print(f"profile: {result['status']}")
            for failure in result["failures"]:
                print(f"- {failure}")
        else:
            print(f"trace: {'passed' if passed else 'failed'}")
            for violation in result["violations"]:
                print(f"- {violation}")
    raise SystemExit(0 if passed else 1)
