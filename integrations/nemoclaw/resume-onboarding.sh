#!/usr/bin/env bash
set -euo pipefail

readonly SANDBOX_NAME="open-agent-system"
readonly AGENT_NAME="langchain-deepagents-code"

if ! command -v nemo-deepagents >/dev/null 2>&1; then
  echo "nemo-deepagents is not installed or is not on PATH." >&2
  exit 1
fi

if [[ -n "${NVIDIA_INFERENCE_API_KEY:-}" ]]; then
  echo "Using NVIDIA_INFERENCE_API_KEY already present in this terminal session."
  NEMOCLAW_AGENT="$AGENT_NAME" \
    NEMOCLAW_SANDBOX_NAME="$SANDBOX_NAME" \
    nemo-deepagents onboard --resume
  exit $?
fi

read -r -s -p "NVIDIA inference API key (input is hidden): " provider_key
echo

if [[ -z "$provider_key" ]]; then
  echo "No key entered; onboarding was not resumed." >&2
  exit 2
fi

NVIDIA_INFERENCE_API_KEY="$provider_key" \
  NEMOCLAW_AGENT="$AGENT_NAME" \
  NEMOCLAW_SANDBOX_NAME="$SANDBOX_NAME" \
  nemo-deepagents onboard --resume

unset provider_key
