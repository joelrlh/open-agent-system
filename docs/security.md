# Security Model

## Trust Boundaries

- The operator's task is trusted intent, but still cannot widen OpenShell policy.
- Model output is untrusted until constrained by registered tools and policy.
- MCP arguments are untrusted and validated server-side.
- Retrieved content is untrusted and may contain prompt injection.
- Provider credentials are managed outside the repository by NemoClaw/OpenShell.

Security precedence is monotonic: project instructions cannot grant authority;
approval cannot override OpenShell; an OpenShell denial is final.

## v0.1 Authority

The business tool surface is read-only: `research.search` and
`research.fetch`. The fixture never performs arbitrary network fetches. It serves
only deterministic checked-in sources and rejects unknown identifiers, malformed
URIs, oversized requests, query strings, fragments, user info, ports, and
unapproved hosts.

The pinned declarative subagent loader does not support a specialist-specific
tool allowlist; it exposes the managed read tools to both the orchestrator and
researcher. OpenShell and the fixture prevent that inherited exposure from
widening authority. Project instructions assign the tools to the researcher,
and persisted-trace validation fails closed if the orchestrator calls them
directly. This detects and suppresses a topology violation but is not equivalent
to runtime role isolation.

Headless managed execution must not use shell tools. Interactive approval and
session behavior belong to the pinned Deep Agents Code runtime and are verified
live; this repository does not implement a parallel approval service.

## Secret Handling

Never put an API key in a prompt, environment snapshot, project file, trace,
exception, test fixture, or command output. Offline tests use only secret-shaped
canaries. Local trace serialization redacts conservative key/token patterns and
replaces oversized payloads with a bounded marker.

The Cloudflare deployment stores `RESEARCH_FIXTURE_TOKEN` as a Worker secret and
passes a separately managed copy to NemoClaw's MCP credential provider. The
public `/health` route returns only schema version and status. The Worker rejects
missing, malformed, duplicate, and incorrect authorization values before MCP
parsing, disables platform observability by default, and creates a fresh
stateless MCP server for each request.

The live gate stages only `.deepagents/`, `AGENTS.md`, and its two validation
scripts before sandbox upload. It never uploads the host working directory,
ignored dependency trees, local environment files, or build output.

## Dependency Advisory Boundary

The current MCP SDK dependency graph reports a moderate Windows path-traversal
advisory in its Node-only Hono static-file adapter. This project deploys a
Cloudflare Worker, does not import that adapter, and serves no filesystem paths.
CI blocks high and critical npm advisories and inspects the generated Worker
bundle to prove the Hono adapter, `serve-static`, Sharp, and libvips codepaths are
absent. The pinned Sharp override removes the separate high-severity local
Miniflare advisory without changing the Worker bundle. Remove these exceptions
when upstream packages publish compatible fixes.

## Release Blockers

Any unauthorized dispatch, missing denial signal, credential exposure,
provenance forgery, prompt-injection escalation, unbounded output, tuple drift,
or skipped live security case blocks a release. Stable release is also blocked
while the managed Nemotron route can complete with blank content or while
specialist-only tool ownership lacks a reviewed preventive runtime mechanism.
