#!/bin/sh
set -eu

sandbox_name=${1:-open-agent-system}

printf '%s\n' "NemoClaw:"
nemo-deepagents --version
printf '%s\n' "OpenShell:"
openshell --version
printf '%s\n' "Docker:"
docker version --format 'client={{.Client.Version}} server={{.Server.Version}} arch={{.Server.Arch}}'
printf '%s\n' "Sandbox status:"
nemo-deepagents "$sandbox_name" status --json
printf '%s\n' "Doctor:"
nemo-deepagents "$sandbox_name" doctor --json
