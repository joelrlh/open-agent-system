# TODOS

## Agent Runtime

### Add a local-inference profile

**What:** Add an optional local OpenAI-compatible inference profile after the hosted NVIDIA reference path is stable.

**Why:** Let users run the system without sending tasks to a hosted provider, improving privacy, offline operation, and control over model costs.

**Context:** v0.1 uses a pinned NVIDIA-hosted inference path because it is closest to the source architecture and gives the first live acceptance test one controlled target. A local profile adds model downloads, hardware sizing, performance tuning, and model-specific tool-call compatibility. Start from the accepted v0.1 contracts and add a separate NemoClaw onboarding profile without weakening OpenShell credential or network policy.

**Effort:** L
**Priority:** P2
**Depends on:** Stable hosted v0.1 reference integration and passing live acceptance suite

### Add specialist agents from measured workflow boundaries

**What:** Add new specialist agents only when evaluation evidence shows a distinct context, tool, or permission boundary.

**Why:** Expand domain capability without creating overlapping agent roles, unnecessary routing, or excess context sharing.

**Context:** v0.1 has one read-only research/retrieval specialist. Candidate future roles should begin with a real workflow and evaluation cases demonstrating why the existing specialist cannot safely or clearly own it. Each new role needs its own skill, allowed tools, data scope, budget, and routing/evaluation cases.

**Effort:** M per specialist
**Priority:** P3
**Depends on:** v0.1 usage evidence and a failing or missing evaluation case

## Maintenance

### Add scheduled upstream compatibility checks

**What:** Run scheduled compatibility tests against newer NemoClaw, OpenShell, Deep Agents, and model-profile releases.

**Why:** Detect upstream breakage and security-policy drift before a manual upgrade is attempted.

**Context:** v0.1 records one exact known-good version and image-digest matrix plus a manual compatibility command. Scheduled checks should test upgrades in isolation, publish a report, and open review work when needed. They must never automatically update the pinned runtime, generated lockfiles, or security policy.

**Effort:** M
**Priority:** P2
**Depends on:** Known-good v0.1 version matrix and stable live acceptance tests

## Observability

### Add privacy-reviewed remote trace export

**What:** Add opt-in export from local redacted traces to an authenticated remote OpenTelemetry collector.

**Why:** Support centralized debugging and operational monitoring for shared or long-running deployments.

**Context:** v0.1 keeps traces local because prompts, retrieved content, tool arguments, and responses can contain sensitive information, while pattern-based redaction is not exhaustive. Before enabling export, define allowlisted fields, collector authentication, OpenShell network policy, retention and deletion, access control, delivery monitoring, and failure behavior. A successful agent task must not be treated as proof that trace delivery succeeded.

**Effort:** L
**Priority:** P2
**Depends on:** v0.1 local trace schema and a separate privacy/security review

## Completed

_No completed deferred items yet._
