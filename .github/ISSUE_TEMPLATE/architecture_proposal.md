---
name: Architecture Proposal
about: Propose a significant architectural change requiring an ADR
title: "[Architecture] "
labels: architecture
assignees: ''
---

## Summary

One-paragraph description of the proposed change.

## Motivation

Why is this change needed? What problem does it solve?

## Current Architecture

How does the relevant part of the system work today?

## Proposed Architecture

How should it work after this change?

## Design Details

### Components Affected

- [ ] `ceramic/server.py` (CeramicFastMCP)
- [ ] `ceramic/middleware/` (pipeline)
- [ ] `ceramic/auth/` (OAuth/OIDC)
- [ ] `ceramic/config.py` (configuration models)
- [ ] `ceramic/identity.py` (identity propagation)
- [ ] `ceramic/resilience.py` (circuit breaker)
- [ ] `ceramic/security.py` (TLS/redaction)
- [ ] Public API (`ceramic/__init__.py`)
- [ ] Other: 

### Migration Path

How do existing users migrate? Is it backward compatible?

### Security Impact

Does this change affect authentication, authorization, or data protection?

## ADR Draft

```markdown
# ADR-XXX: [Title]

## Status
Proposed

## Context
[Why this decision is needed]

## Decision
[What was decided]

## Rationale
[Why this approach over alternatives]

## Consequences
[Positive and negative effects]
```

## Risks

What could go wrong? How do we mitigate it?

## Alternatives Rejected

Other approaches considered and why they don't fit.
