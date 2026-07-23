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
- Deployed the repository-owned fixture to the stable Cloudflare Worker
  `open-agent-research-fixture.joelrlh.workers.dev` and permanently registered
  its authenticated `/mcp` endpoint. Health returned HTTP 200 while an
  unauthenticated MCP request returned HTTP 401.
- Tightened permanent OpenShell policy version 47 to `initialize`,
  `notifications/initialized`, `ping`, `tools/list`, and `tools/call`, with a
  16 KiB request cap.
- Proved a full persisted-trace result with one delegation, one managed search,
  one canonical fetch, exact `five-layer-stack` provenance, and seven tool calls
  within the eight-call budget.
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
- Replaced the quick-tunnel dependency with the stable Worker. Credential
  rotation showed up to 52 seconds of mixed edge responses, so deployment now
  requires three consecutive authenticated endpoint checks, three wire-level
  credential checks, and three real LangChain MCP sessions before inference.
- Left one permanent `research` bridge attached and credential-ready. A direct
  post-tightening LangChain session discovered exactly `research.search` and
  `research.fetch`; no temporary live-gate workspace remained.

Machine-readable evidence is in `integrations/nemoclaw/known-good.json` and
`artifacts/compatibility/live-gate-20260722.json`. Their `release_ready` fields
remain `false` until every live case passes.

## Stable Cloudflare Deployment

- Origin: `https://open-agent-research-fixture.joelrlh.workers.dev`
- Health: `GET /health` -> HTTP 200
- MCP without bearer: `POST /mcp` -> HTTP 401
- Active Worker version: `72e11668-6bd6-45fd-93a6-862450474ae7`
- Deploy-reported startup time: 56 ms
- Effective OpenShell policy: version 47,
  `f4e6abd0fd2f09317fd089c5d37a5acbac28a3e1b63d91d6c1d25d6d76ffd9d7`

The reviewed effective policy is narrower than NemoClaw's generated registration
policy. NemoClaw therefore reports policy drift and skips its built-in
post-tightening credential probe. Deployment verifies that probe before
tightening, then verifies the real LangChain session and exact effective policy.
Credential rotation and policy reconciliation must use the repository deploy
script so the broad generated policy is never left active.

Wrangler's alpha `check startup` command analyzed the prebuilt bundle but then
failed inside Wrangler while parsing FormData. This does not affect deployment;
the normal deploy completed and reported the startup measurement above.

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
make ask QUERY="<bounded research task>"
  -> upload the minimal declarative profile to a disposable Git-root workspace
  -> managed dcode launcher
  -> Deep Agents Code inside OpenShell
  -> managed inference and MCP configuration
  -> persisted-trace validation and workspace cleanup
```

The pinned launcher uses an isolated, read-only Python environment and disables
executable hooks, unmanaged MCP files, custom provider overrides, and headless
shell execution. The direct `nemo-deepagents ... agent` wrapper starts at
`/sandbox` and does not copy the host checkout, so the repository entry point
performs the minimal upload before invoking `dcode`. Its supported project
extension surface is declarative:

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
The stable Worker and permanent `research` bridge are active.

## 2026-07-23 Reliability Finding

A fresh production-shaped run succeeded once with one delegation, one search,
one fetch, and a final cited answer. A subsequent bounded three-attempt run
failed with two immediate one-byte newline completions and one newline
completion after `search_tools`; each response reported `finish_reason: stop`.
An earlier persisted trace also exposed the managed provider failure
`ResourceExhausted: Worker local total request limit reached`. The validator now
surfaces that failure as the fixed code `provider_capacity_exhausted` without
reprinting provider exception text.

After the prompt and validator hardening, a fresh production-shaped run passed
on its third bounded attempt with one delegation, one search, one fetch, five
total tool calls, and canonical provenance. Its first attempt missed delegation,
and its second attempt surfaced `provider_capacity_exhausted`. This proves the
bounded retry and fail-closed validation path, but it does not prove the
underlying managed model route is stable.

NVIDIA's [Nemotron model guidance](https://build.nvidia.com/nvidia/nemotron-3-ultra-550b-a55b/modelcard)
requires
`extra_body.chat_template_kwargs.force_nonempty_content = true` for coding
agents. The sandbox `config.toml` contains that exact setting, but the pinned
NemoClaw hardening replaces Deep Agents Code's provider-parameter resolver with
a managed resolver that returns only the inference URL, synthetic credential,
and `use_responses_api = false`. The resolved constructor settings therefore
omit `extra_body`, and the managed launcher separately disables
`--model-params`. The repository cannot safely repair this without bypassing the
supported managed runtime. Stable release remains blocked pending a reviewed
NemoClaw/runtime fix and a clean live rerun.

The same investigation proved that Deep Agents Code `0.1.34` declarative
subagents inherit the root agent's tools. The orchestrator can therefore see the
managed research tools even though they are assigned to the researcher. The
fixture and OpenShell keep the inherited surface deterministic and read-only;
project prompts now make ownership explicit, and persisted-trace validation
rejects a direct orchestrator research call before considering retryable
conformance failures. This is fail-closed detection, not per-agent runtime
isolation, and remains a stable-release blocker.

## Remaining Gate Cases

- Managed Nemotron constructor must preserve the required non-empty-content
  setting, followed by a clean bounded rerun without blank stop completions
- Preventive specialist-only tool isolation, or an explicitly reviewed
  architecture amendment that treats fail-closed trace ownership as sufficient
- Sandbox rebuild/destroy lifecycle and immutable image digest
- Full Deep Agents prompt-injection containment rerun (the direct pinned
  model-plus-fixture path passed; the nested path hit worker quota)
- Complete live budget and dependency-failure matrices (the agent deadline and
  cleanup paths pass)
- Reconcile NemoClaw's generated-policy registry with the reviewed tighter
  effective MCP policy so built-in lifecycle status no longer reports drift
