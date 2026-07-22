# Project Operations

## Deploy Configuration (configured by /setup-deploy)

- Platform: Cloudflare Workers
- Production URL: https://open-agent-research-fixture.joelrlh.workers.dev
- Deploy workflow: manual repository deployment script
- Deploy status command: `npx --no-install wrangler deployments status --config deploy/cloudflare-worker/wrangler.jsonc`
- Merge method: squash
- Project type: API
- Post-deploy health check: https://open-agent-research-fixture.joelrlh.workers.dev/health

### Custom deploy hooks

- Pre-merge: `make verify`
- Deploy trigger: `./integrations/nemoclaw/deploy-cloudflare-mcp.sh open-agent-system`
- Deploy status: `npx --no-install wrangler deployments status --config deploy/cloudflare-worker/wrangler.jsonc`
- Health check: `curl -sf https://open-agent-research-fixture.joelrlh.workers.dev/health`
