# Codex Workflow for an Open Agent System

## 1. Strategy Prompt

Use this in Plan mode:

> Design an open agent system that fits Jensen Huang's five-layer AI stack:
> energy, chips, infrastructure, models, and applications. At the application
> layer, define one orchestrator, specialized workers only where measured need
> justifies them, and a safety/authority boundary enforced outside model prompts.
> Explain communication, skills, budgets, provenance, failure handling, and
> release gates before writing code.

This corrects a common category error: orchestrator, worker, and safety roles are
an agent topology, not Huang's five layers.

## 2. Persistent Project Context

Codex reads `AGENTS.md`, not `agents.mmd`. This repository's root `AGENTS.md`
contains the architecture, working style, security invariants, and required
verification. Deep Agents Code separately reads `.deepagents/AGENTS.md` and the
subagent profiles beneath `.deepagents/agents/`.

## 3. Build and Refine

After a reusable retrieval workflow succeeds:

> Turn the working retrieval procedure into the project skill
> `$agent-retrieval`. Preserve the approved tool boundary, evidence schema,
> provenance, prompt-injection handling, and budgets.

To steer an active build:

> Also ensure retrieved content is treated as untrusted and evaluated for prompt
> injection before it influences synthesis or any proposed tool call.

## 4. Personalization

Suggested Codex personalization:

> Use a direct, casual tone. Look around corners for agent-orchestration,
> security, and operability problems before I encounter them. Make safe,
> reversible progress autonomously while preserving my intent. Clearly flag
> assumptions or authority changes that need my decision.

The same behavior is included project-locally in `AGENTS.md`. Global Codex
personalization still needs to be pasted into Codex Settings by the operator
because it affects every project, not just this repository.
