# Cloudflare MCP Worker

This package deploys the deterministic read-only research fixture as a stateless
Cloudflare Worker using Streamable HTTP at `/mcp`. It exposes only
`research.search` and `research.fetch`. The checked-in corpus remains the single
source of truth.

The `/mcp` endpoint requires one exact bearer credential stored as the
Cloudflare secret `RESEARCH_FIXTURE_TOKEN`. `/health` is public and returns only
service status. Observability is disabled to avoid exporting prompts, arguments,
or evidence by default.

## Local verification

```bash
npm ci
npm run worker:check
```

For local protocol testing, create an ignored `.dev.vars` file containing a
fresh test-only `RESEARCH_FIXTURE_TOKEN`, then run `npm run worker:dev`.

## Deployment

```bash
npx wrangler@4.113.0 login --use-keyring \
  --scopes account:read user:read workers_scripts:write
./integrations/nemoclaw/deploy-cloudflare-mcp.sh open-agent-system
```

The deployment script verifies the local bundle, deploys the Worker, generates
and installs a fresh bearer secret, waits for three consecutive authenticated
endpoint checks and three real LangChain MCP sessions, runs the persisted-trace
live gate, and then leaves a least-authority `research` bridge registered in
NemoClaw. It aborts if the sandbox already has a bridge so an existing credential
cannot be rotated by accident.

Production endpoints:

- Health: `https://open-agent-research-fixture.joelrlh.workers.dev/health`
- MCP: `https://open-agent-research-fixture.joelrlh.workers.dev/mcp`

The reviewed effective policy is intentionally narrower than NemoClaw's
generated registration policy. As a result, `mcp status` reports policy drift
after tightening and skips its built-in credential probe. The deployment gates
on that probe before tightening, then verifies the actual LangChain session and
the exact five-method effective policy. Re-run the deployment script for
credential rotation or policy reconciliation; do not run an unmanaged restart.

Never place the bearer value in this repository, a prompt, command history, or
deployment log. The script passes it to Cloudflare and NemoClaw over standard
input and environment only, then discards its local copy.
