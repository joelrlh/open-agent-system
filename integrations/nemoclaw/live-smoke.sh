#!/bin/sh
set -eu

sandbox_name=${1:-open-agent-system}
server_name=research
project_root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
remote_mcp_url=${RESEARCH_MCP_URL:-}
smoke_tmpdir=$(mktemp -d)
fixture_pid=
tunnel_pid=
bridge_added=false
workspace_uploaded=false
cleanup_done=false
remote_mode=false
policy_restore="$smoke_tmpdir/policy-before-tightening.json"
sandbox_upload_root="/sandbox/workspace/open-agent-live-gate-$$"

cleanup() {
  if [ "$cleanup_done" = true ]; then
    return 0
  fi
  cleanup_done=true
  cleanup_failed=false
  if [ "$bridge_added" = true ]; then
    if [ -s "$policy_restore" ]; then
      if ! openshell policy set "$sandbox_name" --policy "$policy_restore" --wait \
        >/dev/null 2>&1; then
        echo "warning: failed to restore the pre-gate sandbox policy" >&2
        cleanup_failed=true
      fi
    fi
    nemo-deepagents "$sandbox_name" mcp remove "$server_name" >/dev/null 2>&1 || true
    if ! nemo-deepagents "$sandbox_name" mcp list --json \
      | jq -e '.bridges | length == 0' >/dev/null 2>&1; then
        echo "warning: failed to remove the temporary MCP bridge" >&2
        cleanup_failed=true
    fi
  fi
  if [ "$workspace_uploaded" = true ]; then
    if openshell sandbox exec -n "$sandbox_name" --no-tty \
      test -e "$sandbox_upload_root" >/dev/null 2>&1; then
      if ! openshell sandbox exec -n "$sandbox_name" --no-tty \
        find "$sandbox_upload_root" -depth -delete >/dev/null 2>&1; then
        echo "warning: failed to remove the temporary uploaded workspace" >&2
        cleanup_failed=true
      fi
    fi
  fi
  if [ -n "$tunnel_pid" ]; then
    kill "$tunnel_pid" >/dev/null 2>&1 || true
  fi
  if [ -n "$fixture_pid" ]; then
    kill "$fixture_pid" >/dev/null 2>&1 || true
  fi
  unset RESEARCH_FIXTURE_TOKEN
  if [ "$cleanup_failed" = false ]; then
    rm -rf "$smoke_tmpdir"
    return 0
  fi
  echo "cleanup evidence preserved at: $smoke_tmpdir" >&2
  return 1
}

on_exit() {
  status=$?
  trap - EXIT HUP INT TERM
  cleanup || status=1
  exit "$status"
}

trap on_exit EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

for required_command in curl jq nemo-deepagents openshell; do
  command -v "$required_command" >/dev/null 2>&1 || {
    echo "missing required command: $required_command" >&2
    exit 2
  }
done

if [ -n "$remote_mcp_url" ]; then
  remote_mode=true
  case "$remote_mcp_url" in
    https://*/mcp) ;;
    *) echo "RESEARCH_MCP_URL must be an HTTPS URL ending in /mcp" >&2; exit 2 ;;
  esac
  case "$remote_mcp_url" in
    *[[:space:]]*|*'?'*|*'#'*)
      echo "RESEARCH_MCP_URL contains a forbidden suffix or whitespace" >&2
      exit 2
      ;;
  esac
  [ -n "${RESEARCH_FIXTURE_TOKEN:-}" ] || {
    echo "RESEARCH_FIXTURE_TOKEN is required with RESEARCH_MCP_URL" >&2
    exit 2
  }
  [ "$(printf '%s' "$RESEARCH_FIXTURE_TOKEN" | wc -c | tr -d ' ')" -ge 24 ] || {
    echo "RESEARCH_FIXTURE_TOKEN must contain at least 24 bytes" >&2
    exit 2
  }
  mcp_url=$remote_mcp_url
else
  for required_command in uv cloudflared rg openssl python3; do
    command -v "$required_command" >/dev/null 2>&1 || {
      echo "missing required command: $required_command" >&2
      exit 2
    }
  done

  fixture_port=$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')
  RESEARCH_FIXTURE_TOKEN=$(openssl rand -hex 32)

  cd "$project_root"
  RESEARCH_FIXTURE_TOKEN="$RESEARCH_FIXTURE_TOKEN" uv run research-fixture \
    --host 127.0.0.1 \
    --port "$fixture_port" \
    --audit "$smoke_tmpdir/audit.jsonl" \
    --insecure-http-for-local-tests \
    >"$smoke_tmpdir/fixture.log" 2>&1 &
  fixture_pid=$!

  ready=false
  attempt=0
  while [ "$attempt" -lt 60 ]; do
    status=$(curl -sS -o /dev/null -w '%{http_code}' \
      -H "Authorization: Bearer $RESEARCH_FIXTURE_TOKEN" \
      -H 'Host: research.fixture.test' \
      "http://127.0.0.1:$fixture_port/mcp" 2>/dev/null || true)
    case "$status" in
      200|400|405|406) ready=true; break ;;
    esac
    attempt=$((attempt + 1))
    sleep 0.25
  done
  [ "$ready" = true ] || { echo "fixture failed to start" >&2; exit 1; }

  cloudflared tunnel \
    --url "http://127.0.0.1:$fixture_port" \
    --http-host-header research.fixture.test \
    --no-autoupdate \
    >"$smoke_tmpdir/tunnel.log" 2>&1 &
  tunnel_pid=$!

  mcp_origin=
  attempt=0
  while [ "$attempt" -lt 240 ]; do
    mcp_origin=$(rg -o 'https://[a-z0-9-]+\.trycloudflare\.com' \
      "$smoke_tmpdir/tunnel.log" | head -1 || true)
    [ -n "$mcp_origin" ] && break
    attempt=$((attempt + 1))
    sleep 0.25
  done
  [ -n "$mcp_origin" ] || { echo "HTTPS tunnel failed to start" >&2; exit 1; }
  mcp_url="$mcp_origin/mcp"
fi

tunnel_ready=false
credentialed_probe_successes=0
attempt=0
while [ "$attempt" -lt 240 ]; do
  if [ "$remote_mode" = true ]; then
    status=$(curl -sS -o "$smoke_tmpdir/initialize.json" -w '%{http_code}' \
      -X POST \
      -H "Authorization: Bearer $RESEARCH_FIXTURE_TOKEN" \
      -H 'accept: application/json, text/event-stream' \
      -H 'content-type: application/json' \
      -H 'mcp-protocol-version: 2025-11-25' \
      --data '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"capabilities":{},"clientInfo":{"name":"remote-live-gate","version":"1.0.0"},"protocolVersion":"2025-11-25"}}' \
      "$mcp_url" 2>/dev/null || true)
    if [ "$status" = 200 ] && jq -e \
      '.jsonrpc == "2.0" and .result.serverInfo.name == "Open Agent Research Fixture"' \
      "$smoke_tmpdir/initialize.json" >/dev/null 2>&1; then
      credentialed_probe_successes=$((credentialed_probe_successes + 1))
      if [ "$credentialed_probe_successes" -ge 3 ]; then
        tunnel_ready=true
        break
      fi
    else
      credentialed_probe_successes=0
    fi
  else
    status=$(curl -sS -o /dev/null -w '%{http_code}' \
      -H "Authorization: Bearer $RESEARCH_FIXTURE_TOKEN" \
      "$mcp_url" 2>/dev/null || true)
    case "$status" in
      200|400|405|406) tunnel_ready=true; break ;;
    esac
  fi
  attempt=$((attempt + 1))
  sleep 0.5
done
[ "$tunnel_ready" = true ] || {
  echo "HTTPS endpoint failed its credentialed probe (last HTTP status: ${status:-none})" >&2
  [ "$remote_mode" = true ] || sed -n '1,80p' "$smoke_tmpdir/tunnel.log" >&2
  exit 1
}

if [ "$remote_mode" = true ]; then
  unauthorized_status=$(curl -sS -o /dev/null -w '%{http_code}' \
    -X POST -H 'content-type: application/json' \
    --data '{"jsonrpc":"2.0","id":2,"method":"ping"}' \
    "$mcp_url" 2>/dev/null || true)
else
  unauthorized_status=$(curl -sS -o /dev/null -w '%{http_code}' \
    "$mcp_url" 2>/dev/null || true)
fi
[ "$unauthorized_status" = 401 ] || {
  echo "HTTPS endpoint accepted an unauthenticated fixture request" >&2
  exit 1
}

workspace_uploaded=true
project_name=$(basename "$project_root")
upload_project="$smoke_tmpdir/$project_name"
mkdir -p "$upload_project/integrations/nemoclaw"
cp -R "$project_root/.deepagents" "$upload_project/.deepagents"
cp "$project_root/AGENTS.md" "$upload_project/AGENTS.md"
cp "$project_root/integrations/nemoclaw/validate_live_thread.py" \
  "$upload_project/integrations/nemoclaw/validate_live_thread.py"
cp "$project_root/integrations/nemoclaw/validate_mcp_session.py" \
  "$upload_project/integrations/nemoclaw/validate_mcp_session.py"
nemo-deepagents sandbox upload "$sandbox_name" "$upload_project" "$sandbox_upload_root"
sandbox_project="$sandbox_upload_root/$project_name"
openshell sandbox exec -n "$sandbox_name" --workdir "$sandbox_project" \
  --no-tty -- git init -b main >/dev/null

bridge_added=true
RESEARCH_FIXTURE_TOKEN="$RESEARCH_FIXTURE_TOKEN" \
  nemo-deepagents "$sandbox_name" mcp add "$server_name" \
  --url "$mcp_url" \
  --env RESEARCH_FIXTURE_TOKEN

credential_ready=false
credential_attempt=0
credential_successes=0
while [ "$credential_attempt" -lt 10 ]; do
  if nemo-deepagents "$sandbox_name" mcp status "$server_name" --json --probe \
    > "$smoke_tmpdir/mcp-status.json" 2>/dev/null \
    && jq -e '
      .env.ready == true
      and .provider.credentialReady == true
      and .provider.credentialResolution.ok == true
      and .provider.credentialResolution.httpStatus == 200
      and .provider.credentialResolution.controlHttpStatus == 401
    ' "$smoke_tmpdir/mcp-status.json" >/dev/null \
    && openshell sandbox exec -n "$sandbox_name" \
      --workdir "$sandbox_project" --no-tty --timeout 30 -- \
      sh -lc '. /tmp/nemoclaw-proxy-env.sh >/dev/null 2>&1; /opt/venv/bin/python3 integrations/nemoclaw/validate_mcp_session.py' \
      > "$smoke_tmpdir/mcp-session.json" 2>/dev/null; then
    credential_successes=$((credential_successes + 1))
    if [ "$credential_successes" -ge 3 ]; then
      credential_ready=true
      break
    fi
  else
    credential_successes=0
  fi
  if [ "$credential_attempt" -eq 0 ]; then
    RESEARCH_FIXTURE_TOKEN="$RESEARCH_FIXTURE_TOKEN" \
      nemo-deepagents "$sandbox_name" mcp restart "$server_name" >/dev/null 2>&1 || true
  fi
  credential_attempt=$((credential_attempt + 1))
  sleep 2
done
[ "$credential_ready" = true ] || {
  echo "managed MCP credential and runtime session did not become stable" >&2
  exit 1
}
jq '{
  server,
  credential_resolution: .provider.credentialResolution,
  adapter_registered: .adapter.registered
}' "$smoke_tmpdir/mcp-status.json"
cat "$smoke_tmpdir/mcp-session.json"
unset RESEARCH_FIXTURE_TOKEN

"$project_root/integrations/nemoclaw/tighten-mcp-policy.sh" \
  "$sandbox_name" "$server_name" "$policy_restore"

agent_gate_passed=false
agent_attempt=1
while [ "$agent_attempt" -le 3 ]; do
  agent_output=
  : > "$smoke_tmpdir/live-thread.error"
  : > "$smoke_tmpdir/live-thread.json"
  if agent_output=$(openshell sandbox exec -n "$sandbox_name" \
    --workdir "$sandbox_project" \
    --no-tty --timeout 210 -- \
    dcode -n \
    'Delegate exactly once to the researcher subagent. The researcher must search the registered fixture for Jensen Huang five layers, fetch the best result, and return bounded evidence. Then synthesize only that evidence. Return only one compact JSON object with delegation_count, source_id, uri, five_layers, and injection_detected. five_layers must be a JSON array of five lowercase strings in evidence order, never one string. The only permitted tool calls are search_tools, task, research_research.search, and research_research.fetch; do not read files, fetch URLs, or use shell commands.' \
    --max-turns 10 --timeout 180 --no-stream 2>&1); then
    thread_id=$(printf '%s\n' "$agent_output" \
      | sed -n 's/.*Thread: \([0-9a-f-][0-9a-f-]*\).*/\1/p' \
      | head -1)
    if [ -n "$thread_id" ] \
      && openshell sandbox exec -n "$sandbox_name" \
        --workdir "$sandbox_project" \
        --no-tty -- \
        python3 integrations/nemoclaw/validate_live_thread.py --thread-id "$thread_id" \
        > "$smoke_tmpdir/live-thread.json" 2> "$smoke_tmpdir/live-thread.error"; then
      printf '%s\n' "$agent_output"
      cat "$smoke_tmpdir/live-thread.json"
      agent_gate_passed=true
      break
    fi
  fi
  echo "managed agent acceptance attempt $agent_attempt did not pass" >&2
  if [ -s "$smoke_tmpdir/live-thread.error" ]; then
    sed -n '1,20p' "$smoke_tmpdir/live-thread.error" >&2
  elif [ -n "$agent_output" ]; then
    printf '%s\n' "$agent_output" | sed -n '1,40p' >&2
  fi
  agent_attempt=$((agent_attempt + 1))
  sleep 2
done
[ "$agent_gate_passed" = true ] || {
  echo "managed agent acceptance gate exhausted three attempts" >&2
  exit 1
}

if [ "$remote_mode" = true ]; then
  printf '%s\n' "Remote MCP live gate passed: $mcp_url"
else
  printf '%s\n' "Fixture audit:"
  sed -n '1,80p' "$smoke_tmpdir/audit.jsonl"
fi
