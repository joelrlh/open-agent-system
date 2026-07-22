# Open Agent System

[![CI](https://github.com/joelrlh/open-agent-system/actions/workflows/ci.yml/badge.svg)](https://github.com/joelrlh/open-agent-system/actions/workflows/ci.yml)

A small, auditable reference implementation of an open agent system using
NVIDIA NemoClaw, OpenShell, and LangChain Deep Agents Code. The first vertical
slice contains one orchestrator, one read-only research specialist, one bounded
retrieval skill, and policy/evaluation guardrails.

The project uses Jensen Huang's five-layer AI framework accurately: energy,
chips, infrastructure, models, and applications. The orchestrator/worker/safety
design is the agent topology at the application layer, not a relabeling of those
five layers.

## Status

The NVIDIA route is configured and live model inference has passed with:

- Sandbox: `open-agent-system`
- Provider: `nvidia-prod`
- Model: `nvidia/nemotron-3-ultra-550b-a55b`
- NemoClaw: `v0.0.90`
- OpenShell: `v0.0.85`
- Deep Agents Code: `v0.1.34`
- Stable research MCP: `https://open-agent-research-fixture.joelrlh.workers.dev/mcp`

The repository remains pre-release until every live allow/deny, injection,
credential-isolation, approval, and failure-path gate passes.

## Quick Start

Prerequisites: Python 3.11+, [uv](https://docs.astral.sh/uv/), Node.js 22+, and npm.

```bash
make install
make verify
```

`make verify` is credential-free. It validates the 16-case contract manifest,
runs the deterministic portions of that contract, and performs lint checks.

NVIDIA credentials are entered only through local NemoClaw onboarding. Never
paste a provider key into a prompt or add it to this repository.

## Managed Runtime

The production-shaped entry point is owned by NemoClaw:

```bash
nemo-deepagents open-agent-system agent -n "Research the configured fixture and return cited evidence."
```

The managed runtime discovers `.deepagents/AGENTS.md`, the `researcher`
subagent, and `$agent-retrieval`. OpenShell remains the final authority for
filesystem, process, network, MCP, and credential access.

## Stable Research MCP

The deterministic research fixture can be deployed as a stateless Cloudflare
Worker and registered as NemoClaw's permanent `research` bridge:

```bash
npx wrangler@4.113.0 login --use-keyring \
  --scopes account:read user:read workers_scripts:write
./integrations/nemoclaw/deploy-cloudflare-mcp.sh open-agent-system
```

The script verifies the Worker, installs a generated bearer secret in
Cloudflare and NemoClaw without printing it, runs the managed remote live gate,
waits for consecutive endpoint and real LangChain-session checks, validates the
persisted agent trace, and applies the restricted MCP method policy. The live
Worker health endpoint is
[open-agent-research-fixture.joelrlh.workers.dev/health](https://open-agent-research-fixture.joelrlh.workers.dev/health). See the
[deployment guide](deploy/cloudflare-worker/README.md).

See [architecture](docs/architecture.md), [security](docs/security.md), the
[corrected Codex workflow](docs/codex-workflow.md), and the
[compatibility report](docs/compatibility-report.md).

## License

Apache-2.0. See [LICENSE](LICENSE).
