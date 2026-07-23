import os
import subprocess
from pathlib import Path

import yaml


def test_research_policy_has_minimum_complete_mcp_method_surface() -> None:
    root = Path(__file__).resolve().parents[1]
    policy = yaml.safe_load(
        (root / "policies/openshell/research-readonly.yaml").read_text(encoding="utf-8")
    )
    endpoint = policy["network_policies"]["mcp_bridge_research"]["endpoints"][0]
    methods = [rule["allow"]["method"] for rule in endpoint["rules"]]
    assert methods == [
        "initialize",
        "notifications/initialized",
        "ping",
        "tools/list",
        "tools/call",
    ]
    assert endpoint["protocol"] == "mcp"
    assert endpoint["enforcement"] == "enforce"
    assert endpoint["mcp"]["allow_all_known_mcp_methods"] is False
    assert endpoint["mcp"]["max_body_bytes"] == 16384


def test_tool_name_authority_is_enforced_by_the_fixture_surface() -> None:
    root = Path(__file__).resolve().parents[1]
    server_source = (root / "src/open_agent_system/research_fixture.py").read_text()
    assert '@server.tool(name="research.search")' in server_source
    assert '@server.tool(name="research.fetch")' in server_source
    assert "@server.tool" in server_source
    assert server_source.count("@server.tool") == 2


def test_live_gate_scopes_credentials_and_restores_policy_before_teardown() -> None:
    root = Path(__file__).resolve().parents[1]
    script = (root / "integrations/nemoclaw/live-smoke.sh").read_text(encoding="utf-8")
    assert "export RESEARCH_FIXTURE_TOKEN" not in script
    assert 'RESEARCH_FIXTURE_TOKEN="$RESEARCH_FIXTURE_TOKEN" uv run research-fixture' in script
    assert 'policy_restore="$smoke_tmpdir/policy-before-tightening.json"' in script
    assert 'openshell policy set "$sandbox_name" --policy "$policy_restore" --wait' in script
    assert 'find "$sandbox_upload_root" -depth -delete' in script
    assert 'nemo-deepagents sandbox upload "$sandbox_name" "$project_root"' not in script
    assert 'cp -R "$project_root/.deepagents" "$upload_project/.deepagents"' in script
    assert 'cp "$project_root/AGENTS.md" "$upload_project/AGENTS.md"' in script
    assert 'nemo-deepagents sandbox upload "$sandbox_name" "$upload_project"' in script
    assert "credential_successes" in script
    assert 'if [ "$credential_successes" -ge 3 ]' in script
    assert "/opt/venv/bin/python3 integrations/nemoclaw/validate_mcp_session.py" in script
    assert 'while [ "$agent_attempt" -le 3 ]' in script
    assert (
        'python3 integrations/nemoclaw/validate_live_thread.py --thread-id "$thread_id"' in script
    )
    assert '[ "$validation_status" -eq 3 ]' in script
    assert "non-retryable authority boundary" in script
    assert "five_layers must be a JSON array" in script
    assert "do not read files, fetch URLs, or use shell commands" in script


def test_stable_deploy_rechecks_the_final_runtime_session() -> None:
    root = Path(__file__).resolve().parents[1]
    script = (root / "integrations/nemoclaw/deploy-cloudflare-mcp.sh").read_text(encoding="utf-8")
    assert "permanent MCP registration is not ready after policy tightening" in script
    assert 'validate_mcp_session.py"' in script
    assert "intentionally narrower than NemoClaw's generated policy" in script


def test_ask_launcher_stages_minimum_profile_and_validates_the_trace() -> None:
    root = Path(__file__).resolve().parents[1]
    script_path = root / "integrations" / "nemoclaw" / "ask.sh"
    script = script_path.read_text(encoding="utf-8")
    makefile = (root / "Makefile").read_text(encoding="utf-8")

    subprocess.run(["sh", "-n", str(script_path)], check=True)
    missing_query = subprocess.run(
        ["sh", str(script_path)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert missing_query.returncode == 2
    assert "QUERY is required" in missing_query.stderr
    assert 'cp -R "$project_root/.deepagents"' not in script
    for profile_file in (
        ".deepagents/AGENTS.md",
        ".deepagents/agents/researcher/AGENTS.md",
        ".deepagents/skills/agent-retrieval/SKILL.md",
        ".deepagents/skills/agent-retrieval/agents/openai.yaml",
        ".deepagents/skills/agent-retrieval/references/evidence-contract.md",
    ):
        assert f'"$project_root/{profile_file}"' in script
    assert 'cp "$project_root/AGENTS.md" "$upload_project/AGENTS.md"' in script
    assert 'nemo-deepagents sandbox upload \\\n  "$sandbox_name" "$upload_project"' in script
    assert 'nemo-deepagents sandbox upload "$sandbox_name" "$project_root"' not in script
    assert "--contract user --thread-id" in script
    assert "1 | 2 | 3)" in script
    assert 'find "$sandbox_upload_root" -depth -delete' in script
    assert '[ "$validation_status" -eq 3 ]' in script
    assert "ask: export OPEN_AGENT_QUERY := $(value QUERY)" in makefile
    assert "@./integrations/nemoclaw/ask.sh" in makefile


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _fake_managed_runtime(tmp_path: Path) -> tuple[dict[str, str], Path]:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    call_log = tmp_path / "calls.log"
    counter = tmp_path / "dcode-count"

    _write_executable(
        fake_bin / "nemo-deepagents",
        """#!/bin/sh
printf 'nemo %s\\n' "$*" >> "$ASK_TEST_LOG"
case " $* " in
  *" mcp list --json "*)
    ready=${ASK_TEST_BRIDGE_READY:-true}
    printf '{"bridges":[{"server":"research","env":{"ready":%s},' "$ready"
    printf '"provider":{"credentialReady":%s},' "$ready"
    printf '"adapter":{"registered":%s}}]}\\n' "$ready"
    ;;
esac
""",
    )
    _write_executable(
        fake_bin / "openshell",
        """#!/bin/sh
printf 'openshell %s\\n' "$*" >> "$ASK_TEST_LOG"
case " $* " in
  *" dcode -n "*)
    count=0
    [ ! -f "$ASK_TEST_COUNTER" ] || count=$(cat "$ASK_TEST_COUNTER")
    count=$((count + 1))
    printf '%s\\n' "$count" > "$ASK_TEST_COUNTER"
    if [ "${ASK_TEST_DCODE_FAIL_ONCE:-false}" = true ] && [ "$count" -eq 1 ]; then
      echo "Unexpected error (APIError): transient provider failure"
      exit 1
    fi
    echo "Thread: 019f0000-0000-7000-8000-000000000001"
    echo "bounded answer"
    [ "${ASK_TEST_DCODE_EXIT_AFTER_THREAD:-false}" != true ] || exit 1
    ;;
  *"validate_live_thread.py "*)
    if [ "${ASK_TEST_VALIDATION_EXIT:-0}" -eq 3 ]; then
      echo "live thread validation failed: forbidden tools called: shell" >&2
      exit 3
    fi
    echo '{"delegation_count":1,"status":"ok","tool_calls":4}'
    ;;
  *" find /sandbox/workspace/open-agent-run-"*)
    [ "${ASK_TEST_CLEANUP_FAIL:-false}" != true ]
    ;;
  *" test ! -e /sandbox/workspace/open-agent-run-"*)
    [ "${ASK_TEST_CLEANUP_FAIL:-false}" != true ]
    ;;
esac
""",
    )
    _write_executable(fake_bin / "sleep", "#!/bin/sh\nexit 0\n")

    environment = os.environ.copy()
    environment.update(
        {
            "ASK_TEST_COUNTER": str(counter),
            "ASK_TEST_LOG": str(call_log),
            "OPEN_AGENT_ATTEMPTS": "3",
            "OPEN_AGENT_QUERY": "Research the configured fixture.",
            "PATH": f"{fake_bin}:{environment['PATH']}",
        }
    )
    return environment, call_log


def test_ask_launcher_executes_validated_happy_path_and_cleanup(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    environment, call_log = _fake_managed_runtime(tmp_path)

    result = subprocess.run(
        [str(root / "integrations" / "nemoclaw" / "ask.sh")],
        cwd=root,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert '"status":"ok"' in result.stdout
    calls = call_log.read_text(encoding="utf-8")
    assert "sandbox upload" in calls
    assert " dcode -n " in calls
    assert "validate_live_thread.py --contract user" in calls
    assert "find /sandbox/workspace/open-agent-run-" in calls


def test_ask_launcher_retries_one_transient_provider_failure(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    environment, _ = _fake_managed_runtime(tmp_path)
    environment["ASK_TEST_DCODE_FAIL_ONCE"] = "true"

    result = subprocess.run(
        [str(root / "integrations" / "nemoclaw" / "ask.sh")],
        cwd=root,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "attempt 1 of 3" in result.stderr
    assert (tmp_path / "dcode-count").read_text(encoding="utf-8").strip() == "2"


def test_ask_launcher_does_not_retry_authority_violation(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    environment, call_log = _fake_managed_runtime(tmp_path)
    environment["ASK_TEST_VALIDATION_EXIT"] = "3"
    environment["ASK_TEST_DCODE_EXIT_AFTER_THREAD"] = "true"

    result = subprocess.run(
        [str(root / "integrations" / "nemoclaw" / "ask.sh")],
        cwd=root,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "non-retryable authority boundary" in result.stderr
    assert (tmp_path / "dcode-count").read_text(encoding="utf-8").strip() == "1"
    assert "find /sandbox/workspace/open-agent-run-" in call_log.read_text(encoding="utf-8")


def test_ask_launcher_does_not_treat_nonzero_dcode_as_success(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    environment, _ = _fake_managed_runtime(tmp_path)
    environment["ASK_TEST_DCODE_EXIT_AFTER_THREAD"] = "true"

    result = subprocess.run(
        [str(root / "integrations" / "nemoclaw" / "ask.sh")],
        cwd=root,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "despite a valid persisted trace" in result.stderr
    assert "exhausted 3 bounded attempts" in result.stderr
    assert (tmp_path / "dcode-count").read_text(encoding="utf-8").strip() == "3"


def test_ask_launcher_fails_when_remote_cleanup_cannot_be_verified(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    environment, _ = _fake_managed_runtime(tmp_path)
    environment["ASK_TEST_CLEANUP_FAIL"] = "true"

    result = subprocess.run(
        [str(root / "integrations" / "nemoclaw" / "ask.sh")],
        cwd=root,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "failed to remove the temporary uploaded workspace" in result.stderr


def test_ask_launcher_rejects_unready_research_bridge(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    environment, call_log = _fake_managed_runtime(tmp_path)
    environment["ASK_TEST_BRIDGE_READY"] = "false"

    result = subprocess.run(
        [str(root / "integrations" / "nemoclaw" / "ask.sh")],
        cwd=root,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "not credential-ready" in result.stderr
    assert " dcode -n " not in call_log.read_text(encoding="utf-8")
