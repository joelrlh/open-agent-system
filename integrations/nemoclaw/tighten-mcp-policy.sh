#!/bin/sh
set -eu

sandbox_name=${1:-open-agent-system}
server_name=${2:-research}
restore_path=${3:-}

case "$sandbox_name" in
  [a-z]*[a-z0-9]) ;;
  *) echo "invalid sandbox name" >&2; exit 2 ;;
esac

case "$server_name" in
  [a-z]*[a-z0-9]) ;;
  *) echo "invalid MCP server name" >&2; exit 2 ;;
esac

command -v jq >/dev/null 2>&1 || { echo "jq is required" >&2; exit 2; }
command -v openshell >/dev/null 2>&1 || { echo "openshell is required" >&2; exit 2; }

policy_name=$(printf '%s' "mcp_bridge_$server_name" | tr '-' '_')
policy_tmpdir=$(mktemp -d)
cleanup() {
  rm -rf "$policy_tmpdir"
}
trap cleanup EXIT HUP INT TERM

openshell policy get "$sandbox_name" --base -o json > "$policy_tmpdir/current.json"

if [ -n "$restore_path" ]; then
  if [ -e "$restore_path" ] || [ -L "$restore_path" ]; then
    echo "restore path already exists: $restore_path" >&2
    exit 2
  fi
  jq '.policy' "$policy_tmpdir/current.json" > "$restore_path"
fi

jq --arg policy_name "$policy_name" '
  if .policy.network_policies[$policy_name] == null then
    error("managed MCP policy not found: " + $policy_name)
  else
    .policy.network_policies[$policy_name].endpoints[0].mcp.max_body_bytes = 16384
    | .policy.network_policies[$policy_name].endpoints[0].rules = [
        {"allow": {"method": "initialize"}},
        {"allow": {"method": "notifications/initialized"}},
        {"allow": {"method": "ping"}},
        {"allow": {"method": "tools/list"}},
        {"allow": {"method": "tools/call"}}
      ]
    | .policy
  end
' "$policy_tmpdir/current.json" > "$policy_tmpdir/restricted.json"

openshell policy set "$sandbox_name" --policy "$policy_tmpdir/restricted.json" --wait
openshell policy get "$sandbox_name" --full -o json \
  | jq --arg policy_name "$policy_name" '{
      version,
      hash,
      status,
      max_body_bytes: .policy.network_policies[$policy_name].endpoints[0].mcp.max_body_bytes,
      methods: [.policy.network_policies[$policy_name].endpoints[0].rules[].allow.method]
    }'
