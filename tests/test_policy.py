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
    assert "five_layers must be a JSON array" in script
    assert "do not read files, fetch URLs, or use shell commands" in script


def test_stable_deploy_rechecks_the_final_runtime_session() -> None:
    root = Path(__file__).resolve().parents[1]
    script = (root / "integrations/nemoclaw/deploy-cloudflare-mcp.sh").read_text(encoding="utf-8")
    assert "permanent MCP registration is not ready after policy tightening" in script
    assert 'validate_mcp_session.py"' in script
    assert "intentionally narrower than NemoClaw's generated policy" in script
