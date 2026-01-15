# ADR-002: Heuristic-Based Orchestration

## Status

Accepted

## Context

Ringmaster orchestrates AI coding loops and needs to make decisions about:
- State transitions (when to move cards between stages)
- Loop control (when to stop, pause, retry)
- Error recovery (where to route failures)

We could use LLMs for these decisions or rule-based heuristics.

## Decision

Use heuristics (rule-based logic) for all orchestration decisions:
- State machine transitions via lookup tables
- Loop stop conditions via numeric thresholds
- Error recovery via deterministic routing

Reserve LLM usage for:
- RLM context summarization (when history too long)
- Code generation (the actual work)

## Consequences

**Easier:**
- Predictable behavior: same inputs → same decisions
- Debugging: clear audit trail of rules applied
- Cost: no LLM spend on meta-decisions
- Reliability: orchestration works even if LLM API is slow

**Harder:**
- Flexibility: can't adapt decisions based on nuanced understanding
- Must anticipate all cases in rules upfront
