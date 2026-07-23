#!/bin/sh
set -eu

sandbox_name=${1:-open-agent-system}
server_name=research
project_root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
wrangler_config="$project_root/deploy/cloudflare-worker/wrangler.jsonc"
deploy_tmpdir=$(mktemp -d)
bridge_added=false
deployment_complete=false
token=
policy_restore="$deploy_tmpdir/policy-before-tightening.json"

cleanup() {
  status=$?
  trap - EXIT HUP INT TERM
  if [ "$deployment_complete" != true ] && [ "$bridge_added" = true ]; then
    if [ -s "$policy_restore" ]; then
      openshell policy set "$sandbox_name" --policy "$policy_restore" --wait \
        >/dev/null 2>&1 || echo "warning: failed to restore the pre-deploy policy" >&2
    fi
    nemo-deepagents "$sandbox_name" mcp remove "$server_name" >/dev/null 2>&1 || true
    if ! nemo-deepagents "$sandbox_name" mcp list --json \
      | jq -e '.bridges | length == 0' >/dev/null 2>&1; then
      echo "warning: failed to remove the incomplete MCP bridge" >&2
    fi
  fi
  unset token RESEARCH_FIXTURE_TOKEN
  rm -rf "$deploy_tmpdir"
  exit "$status"
}

trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

case "$sandbox_name" in
  [a-z]*[a-z0-9]) ;;
  *) echo "invalid sandbox name" >&2; exit 2 ;;
esac

for required_command in curl jq npm npx openssl rg nemo-deepagents openshell; do
  command -v "$required_command" >/dev/null 2>&1 || {
    echo "missing required command: $required_command" >&2
    exit 2
  }
done

bridge_state=$(nemo-deepagents "$sandbox_name" mcp list --json)
if ! printf '%s' "$bridge_state" | jq -e '.bridges | type == "array"' >/dev/null; then
  echo "NemoClaw returned an unexpected MCP bridge document" >&2
  exit 1
fi
if ! printf '%s' "$bridge_state" | jq -e '.bridges | length == 0' >/dev/null; then
  echo "the sandbox already has an MCP bridge; remove or review it before rotating the stable endpoint" >&2
  exit 1
fi

cd "$project_root"
if ! npx --no-install wrangler whoami --json >/dev/null 2>&1; then
  echo "Wrangler is not authenticated. Run the least-privilege login command from deploy/cloudflare-worker/README.md." >&2
  exit 1
fi
npm run worker:check

if ! deploy_output=$(npx --no-install wrangler deploy --strict --config "$wrangler_config" 2>&1); then
  printf '%s\n' "$deploy_output" >&2
  exit 1
fi
printf '%s\n' "$deploy_output"
printf '%s\n' "$deploy_output" > "$deploy_tmpdir/wrangler-deploy.log"

worker_origin=$(printf '%s\n' "$deploy_output" \
  | rg -o 'https://[a-zA-Z0-9.-]+\.workers\.dev' \
  | tail -1)
[ -n "$worker_origin" ] || {
  echo "could not determine the workers.dev deployment URL" >&2
  exit 1
}
mcp_url="$worker_origin/mcp"

token=$(openssl rand -hex 32)
printf '%s' "$token" \
  | npx --no-install wrangler secret put RESEARCH_FIXTURE_TOKEN \
      --config "$wrangler_config" >/dev/null

health_ready=false
attempt=0
while [ "$attempt" -lt 60 ]; do
  status=$(curl -sS -o /dev/null -w '%{http_code}' "$worker_origin/health" 2>/dev/null || true)
  if [ "$status" = 200 ]; then
    health_ready=true
    break
  fi
  attempt=$((attempt + 1))
  sleep 1
done
[ "$health_ready" = true ] || {
  echo "deployed Worker health check failed (last HTTP status: ${status:-none})" >&2
  exit 1
}

unauthorized_status=$(curl -sS -o /dev/null -w '%{http_code}' \
  -X POST -H 'content-type: application/json' \
  --data '{"jsonrpc":"2.0","id":1,"method":"ping"}' \
  "$mcp_url" 2>/dev/null || true)
[ "$unauthorized_status" = 401 ] || {
  echo "deployed Worker did not reject an unauthenticated MCP request" >&2
  exit 1
}

RESEARCH_MCP_URL="$mcp_url" RESEARCH_FIXTURE_TOKEN="$token" \
  "$project_root/integrations/nemoclaw/live-smoke.sh" "$sandbox_name"

post_gate_state=$(nemo-deepagents "$sandbox_name" mcp list --json)
printf '%s' "$post_gate_state" | jq -e '.bridges | length == 0' >/dev/null || {
  echo "the remote live gate did not clean up its temporary MCP bridge" >&2
  exit 1
}

bridge_added=true
RESEARCH_FIXTURE_TOKEN="$token" \
  nemo-deepagents "$sandbox_name" mcp add "$server_name" \
  --url "$mcp_url" \
  --env RESEARCH_FIXTURE_TOKEN

credential_ready=false
credential_attempt=0
credential_successes=0
while [ "$credential_attempt" -lt 10 ]; do
  if nemo-deepagents "$sandbox_name" mcp status "$server_name" --json --probe \
    > "$deploy_tmpdir/mcp-status.json" 2>/dev/null \
    && jq -e '
      .env.ready == true
      and .provider.credentialReady == true
      and .provider.credentialResolution.ok == true
      and .provider.credentialResolution.httpStatus == 200
      and .provider.credentialResolution.controlHttpStatus == 401
    ' "$deploy_tmpdir/mcp-status.json" >/dev/null; then
    credential_successes=$((credential_successes + 1))
    if [ "$credential_successes" -ge 3 ]; then
      credential_ready=true
      break
    fi
  else
    credential_successes=0
  fi
  if [ "$credential_attempt" -eq 0 ]; then
    RESEARCH_FIXTURE_TOKEN="$token" \
      nemo-deepagents "$sandbox_name" mcp restart "$server_name" >/dev/null 2>&1 || true
  fi
  credential_attempt=$((credential_attempt + 1))
  sleep 2
done
[ "$credential_ready" = true ] || {
  echo "permanent MCP credential did not become stable" >&2
  exit 1
}
unset token

"$project_root/integrations/nemoclaw/tighten-mcp-policy.sh" \
  "$sandbox_name" "$server_name" "$policy_restore"
permanent_state=$(nemo-deepagents "$sandbox_name" mcp list --json)
printf '%s' "$permanent_state" | jq -e '
  (.bridges | length) == 1
  and .bridges[0].server == "research"
  and .bridges[0].adapter.registered == true
  and .bridges[0].provider.attached == true
  and .bridges[0].provider.credentialReady == true
  and .bridges[0].env.ready == true
' >/dev/null || {
  echo "permanent MCP registration is not ready after policy tightening" >&2
  exit 1
}
nemo-deepagents "$sandbox_name" exec --stdin --timeout 30 -- \
  sh -lc '. /tmp/nemoclaw-proxy-env.sh >/dev/null 2>&1; /opt/venv/bin/python3 -' \
  < "$project_root/integrations/nemoclaw/validate_mcp_session.py"
echo "note: the reviewed policy is intentionally narrower than NemoClaw's generated policy; use this deployment script for restart or rotation"

deployment_complete=true
printf '%s\n' "Stable MCP endpoint deployed and registered: $mcp_url"
