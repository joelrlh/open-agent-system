# NemoClaw/OpenShell Compatibility Report

Recorded: 2026-07-22
Host: Apple M4 Pro, macOS 26.4.1, Docker Desktop 29.4.1 (`aarch64`)

## Result

The compatibility gate is **in progress**. Configuration, sandbox creation,
managed inference, project-profile discovery, the MCP happy path, and first deny
paths now pass.

- Installed NemoClaw `0.0.90` from the official `lkg` ref at commit
  `acfa2613c7a645ae1bff21914f25d824e5fbcf62`.
- Installed OpenShell `0.0.85`; the local Docker-driver gateway is healthy and
  connected.
- Host, Docker bridge, host DNS, and container DNS preflights passed.
- Created `open-agent-system` using provider `nvidia-prod` and model
  `nvidia/nemotron-3-ultra-550b-a55b`.
- Verified the managed route, Deep Agents Code `0.1.34`, and a bounded model
  response (`OPEN_AGENT_MODEL_OK`).
- Verified project discovery of the orchestrator, `researcher`, and
  `$agent-retrieval`. Sandbox uploads intentionally omit `.git`, so the
  disposable uploaded workspace needs an empty Git-root marker before `dcode`
  discovers project extensions.
- Registered the repository-owned fixture through a temporary Cloudflare HTTPS
  tunnel and short-lived bearer credential. The credential-resolution probe
  returned HTTP 200 while the no-credential control returned HTTP 401.
- Tightened OpenShell policy version 7 to `initialize`,
  `notifications/initialized`, `ping`, `tools/list`, and `tools/call`, with a
  16 KiB request cap.
- Proved a full one-delegation search/fetch result with exact
  `five-layer-stack` provenance.
- Proved `resources/list` is denied by OpenShell with HTTP 403, and unknown
  tools plus malformed arguments are rejected without fixture-handler dispatch.
- Proved the provider environment contains a synthetic gateway credential rather
  than an NVIDIA key, the MCP environment contains only an OpenShell resolution
  placeholder, and the workspace provider-key scan is clean.
- Proved a direct pinned model-plus-fixture injection check preserved the source
  identifier, made no sentinel tool call, and revealed no credential. The full
  Deep Agents version still needs a clean rerun because its follow-up model call
  hit the NVIDIA worker request quota.
- Proved interactive rejection caused no execution and interactive approval
  executed the exact harmless command once. The persisted thread then resumed
  successfully by identifier after the terminal exited.
- Proved the agent-level one-second deadline exits cleanly with code 124 and an
  actionable timeout error.
- Removed the temporary MCP adapter, credential provider, policy endpoint,
  fixture process, HTTPS tunnel, and bearer credential. The configured sandbox,
  NVIDIA provider, and model route remain intact.
- Re-ran the failure path after hardening teardown. A newly issued quick-tunnel
  hostname resolved through public DNS but not the macOS system resolver, so
  registration failed closed. The script left no bridge, uploaded workspace,
  fixture process, tunnel process, or credential behind.

Machine-readable evidence is in `integrations/nemoclaw/known-good.json` and
`artifacts/compatibility/live-gate-20260722.json`. Their `release_ready` fields
remain `false` until every live case passes.

## Docker Desktop Diagnostic Finding

`nemo-deepagents open-agent-system status --json` reports
`terminalRuntimeHealth.kind = unavailable` because its auxiliary OOM probe
cannot read `/sys/fs/cgroup/memory.events` (including its local variant) under
Docker Desktop. The probe uses a login
shell, whose compatibility hook also prints a resource-limit warning.

This does **not** mean the managed agent launcher is running without limits.
Direct verification observed:

```text
nproc soft/hard: 512 / 512
nofile soft/hard: 65536 / 65536
dcode status: exit 0 through the fail-closed managed launcher
```

The acceptance checker treats an unavailable OOM counter as a diagnostic
limitation while independently requiring the exact limits and a successful
managed-launcher identity check. A real limit mismatch or launcher refusal
remains a release blocker.

## Architecture Finding

The production-shaped command is:

```text
nemo-deepagents open-agent-system agent -n "<bounded task>"
  -> managed dcode launcher
  -> Deep Agents Code inside OpenShell
  -> managed inference and MCP configuration
```

The pinned launcher uses an isolated, read-only Python environment and disables
executable hooks, unmanaged MCP files, custom provider overrides, and headless
shell execution. Its supported project extension surface is declarative:

```text
.deepagents/AGENTS.md
.deepagents/agents/<name>/AGENTS.md
.deepagents/skills/<name>/SKILL.md
NemoClaw-managed HTTPS MCP registration
```

Therefore the original custom Python `create_deep_agent(...)` launcher cannot
be the production NemoClaw path. The compatible design is config-first: project
instructions define the orchestrator, a project subagent defines the researcher,
a project skill defines the procedure, OpenShell enforces authority, and a
repository-owned HTTPS MCP fixture supplies deterministic read tools.

### Managed Tool-Calling Finding

Deep Agents Code exposes MCP tools through its bounded programmatic-tool-calling
path. Running with `--no-interpreter` leaves tool discovery available but
prevents the actual MCP call. The supported path keeps the default 64 MiB,
five-second safe interpreter enabled while shell commands remain unavailable in
headless mode.

OpenShell `0.0.85` can restrict MCP methods, but `strict_tool_names` validates
syntax; it does not authorize a per-tool allowlist. The fixture is therefore an
independent authority boundary: it exposes only `research.search` and
`research.fetch`, performs strict server-side validation, and never performs
arbitrary network fetches.

## Configuration State

NVIDIA onboarding is complete. The live route is
`nvidia-prod / nvidia/nemotron-3-ultra-550b-a55b`, with no route drift. No
additional operator input is required for the remaining automated gate checks.

## Remaining Gate Cases

- Sandbox rebuild/destroy lifecycle and immutable image digest
- Full Deep Agents prompt-injection containment rerun (the direct pinned
  model-plus-fixture path passed; the nested path hit worker quota)
- Complete live budget and dependency-failure matrices (the agent deadline and
  cleanup paths pass)
- Reliable system resolution of newly issued `trycloudflare.com` quick-tunnel
  hostnames, or a stable operator-managed HTTPS fixture endpoint
