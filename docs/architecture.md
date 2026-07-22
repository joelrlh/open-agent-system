# Architecture

## Placement in the Five-Layer AI Stack

Jensen Huang describes the AI industrial stack as energy, chips,
infrastructure, models, and applications. This repository is an application-layer
reference system. It consumes NVIDIA-hosted model infrastructure and does not
claim that orchestrators, workers, and guardrails are the five layers.

## Runtime Topology

```text
operator
  -> NemoClaw managed Deep Agents Code orchestrator
      -> researcher subagent (maximum one delegation)
          -> managed HTTPS MCP: research.search / research.fetch
              -> deterministic checked-in corpus

authority surrounds the flow:
  Deep Agents instructions < interactive approval < OpenShell policy
```

The repository contributes only supported declarative extension points:

- `.deepagents/AGENTS.md` — orchestrator behavior
- `.deepagents/agents/researcher/AGENTS.md` — specialist behavior
- `.deepagents/skills/agent-retrieval/SKILL.md` — evidence procedure
- a NemoClaw-managed HTTPS MCP registration — deterministic read tools
- OpenShell policy and executable acceptance evidence

`src/open_agent_system` validates these contracts and serializes bounded,
redacted evidence. It never calls `create_deep_agent(...)` and is not an
alternate launcher.

## Control and Data Boundaries

The model may propose a tool call. The registered tool surface, MCP server input
validation, and OpenShell policy decide whether it can happen. Tool output is
untrusted model input. Provenance returned by the fixture is preserved through
the specialist and orchestrator result.

Default budgets are one delegation, 12 model turns, 8 tool calls, 30 seconds per
tool, 180 seconds total, 10 evidence records of 4 KiB, and an 8 KiB final answer.
