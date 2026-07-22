#!/bin/sh
set -eu

sandbox_name=${1:-open-agent-system}
server_name=research
project_root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
smoke_tmpdir=$(mktemp -d)
fixture_pid=
tunnel_pid=
bridge_added=false
workspace_uploaded=false
cleanup_done=false
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
    if ! nemo-deepagents "$sandbox_name" mcp remove "$server_name" >/dev/null 2>&1; then
      echo "warning: failed to remove the temporary MCP bridge" >&2
      cleanup_failed=true
    fi
  fi
  if [ "$workspace_uploaded" = true ]; then
    if ! openshell sandbox exec -n "$sandbox_name" --no-tty \
      find "$sandbox_upload_root" -depth -delete >/dev/null 2>&1; then
      echo "warning: failed to remove the temporary uploaded workspace" >&2
      cleanup_failed=true
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

for required_command in uv cloudflared curl rg openssl python3 nemo-deepagents openshell; do
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

tunnel_ready=false
attempt=0
while [ "$attempt" -lt 240 ]; do
  status=$(curl -sS -o /dev/null -w '%{http_code}' \
    -H "Authorization: Bearer $RESEARCH_FIXTURE_TOKEN" \
    "$mcp_origin/mcp" 2>/dev/null || true)
  case "$status" in
    200|400|405|406) tunnel_ready=true; break ;;
  esac
  attempt=$((attempt + 1))
  sleep 0.5
done
[ "$tunnel_ready" = true ] || {
  echo "HTTPS tunnel failed its credentialed probe (last HTTP status: ${status:-none})" >&2
  sed -n '1,80p' "$smoke_tmpdir/tunnel.log" >&2
  exit 1
}

unauthorized_status=$(curl -sS -o /dev/null -w '%{http_code}' \
  "$mcp_origin/mcp" 2>/dev/null || true)
[ "$unauthorized_status" = 401 ] || {
  echo "HTTPS tunnel accepted an unauthenticated fixture request" >&2
  exit 1
}

nemo-deepagents sandbox upload "$sandbox_name" "$project_root" "$sandbox_upload_root"
workspace_uploaded=true
project_name=$(basename "$project_root")
sandbox_project="$sandbox_upload_root/$project_name"
openshell sandbox exec -n "$sandbox_name" --workdir "$sandbox_project" \
  --no-tty -- git init -b main >/dev/null

RESEARCH_FIXTURE_TOKEN="$RESEARCH_FIXTURE_TOKEN" \
  nemo-deepagents "$sandbox_name" mcp add "$server_name" \
  --url "$mcp_origin/mcp" \
  --env RESEARCH_FIXTURE_TOKEN
bridge_added=true
unset RESEARCH_FIXTURE_TOKEN

"$project_root/integrations/nemoclaw/tighten-mcp-policy.sh" \
  "$sandbox_name" "$server_name" "$policy_restore"

openshell sandbox exec -n "$sandbox_name" \
  --workdir "$sandbox_project" \
  --no-tty --timeout 210 -- \
  dcode -n \
  'Delegate exactly once to the researcher. Search for Jensen Huang five layers, fetch the best result, and return compact JSON with delegation_count, source_id, uri, and five_layers. Do not use shell commands.' \
  --max-turns 10 --timeout 180 --no-stream

printf '%s\n' "Fixture audit:"
sed -n '1,80p' "$smoke_tmpdir/audit.jsonl"
