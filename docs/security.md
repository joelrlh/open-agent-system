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

Headless managed execution must not use shell tools. Interactive approval and
session behavior belong to the pinned Deep Agents Code runtime and are verified
live; this repository does not implement a parallel approval service.

## Secret Handling

Never put an API key in a prompt, environment snapshot, project file, trace,
exception, test fixture, or command output. Offline tests use only secret-shaped
canaries. Local trace serialization redacts conservative key/token patterns and
replaces oversized payloads with a bounded marker.

## Release Blockers

Any unauthorized dispatch, missing denial signal, credential exposure,
provenance forgery, prompt-injection escalation, unbounded output, tuple drift,
or skipped live security case blocks a release.
