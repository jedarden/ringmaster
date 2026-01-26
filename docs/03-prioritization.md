# Task Prioritization

## Overview

Ringmaster uses graph-based prioritization inspired by [doodlestein's beads_viewer](https://github.com/Dicklesworthstone/beads_viewer) approach: **PageRank + dependency analysis** to identify high-impact tasks that unblock the most downstream work.

## Design Principle

> "LLMs are excellent at semantic reasoning but notoriously unreliable at algorithmic graph traversal."
> — beads_viewer Robot Protocol

Prioritization is **deterministic and algorithmic**, not LLM-driven. The dependency graph is analyzed using well-understood graph algorithms to produce consistent, explainable rankings.

## Graph Algorithms

### 1. PageRank

**What it measures:** Overall importance based on incoming dependencies.

Tasks that many other tasks depend on have higher PageRank scores. Like web pages with many inbound links, these are "authoritative" tasks.

```
PageRank(task) ∝ Σ (PageRank(dependent) / out_degree(dependent))
```

**Use case:** Identify foundational tasks that unlock many others.

### 2. Betweenness Centrality

**What it measures:** How often a task lies on the shortest path between other tasks.

High-scoring tasks are critical junctions where delays ripple across the entire project.

```
Betweenness(task) = Σ (shortest_paths_through(task) / total_shortest_paths)
```

**Use case:** Find bottleneck tasks that would cascade delays if blocked.

### 3. HITS (Hubs & Authorities)

**What it measures:** Two complementary scores:
- **Authority:** Tasks that are depended upon (like PageRank)
- **Hub:** Tasks that depend on many others (integration points)

```
Authority(task) ∝ Σ Hub(dependents)
Hub(task) ∝ Σ Authority(dependencies)
```

**Use case:** Distinguish between foundational work (authorities) and integration work (hubs).

### 4. Critical Path

**What it measures:** The longest chain of sequential dependencies.

Tasks on the critical path directly impact total project duration. Any delay on the critical path delays the entire project.

```
Critical_Path = longest_path(start_nodes, end_nodes)
```

**Use case:** Prioritize tasks that are on the critical path to avoid schedule slip.

### 5. Topological Sort

**What it measures:** Valid execution order respecting dependencies.

```
Topo_Order = DFS-based ordering where dependencies come before dependents
```

**Use case:** Ensure tasks are only assigned when dependencies are complete.

## Combined Priority Score

Ringmaster combines these metrics into a single priority score:

```python
def calculate_priority(task, graph):
    # Weights (configurable)
    W_PAGERANK = 0.30
    W_BETWEENNESS = 0.25
    W_CRITICAL = 0.25
    W_MANUAL = 0.20

    # Normalize each metric to 0-1 range
    pagerank_norm = normalize(pagerank[task], graph)
    betweenness_norm = normalize(betweenness[task], graph)
    critical_norm = 1.0 if task in critical_path else 0.0
    manual_norm = manual_priority_to_score(task.priority)  # P0=1.0, P4=0.0

    # Combine
    score = (
        W_PAGERANK * pagerank_norm +
        W_BETWEENNESS * betweenness_norm +
        W_CRITICAL * critical_norm +
        W_MANUAL * manual_norm
    )

    # Boost for "ready" tasks (all dependencies satisfied)
    if task.status == "ready":
        score *= 1.5

    return score
```

## Priority Queue Structure

```
┌─────────────────────────────────────────────────────────────────────┐
│  PRIORITY QUEUE                                                      │
│                                                                      │
│  ┌─────┬──────────────────────┬───────┬────────────────────────────┐│
│  │Score│ Task                 │Status │ Why High Priority?         ││
│  ├─────┼──────────────────────┼───────┼────────────────────────────┤│
│  │0.92 │ bd-a3f8.1 JWT tokens │ ready │ PageRank: 0.8, Critical    ││
│  │0.85 │ bd-a3f8.0 Auth setup │ ready │ Betweenness: 0.9           ││
│  │0.71 │ bd-b2c1.3 API routes │ ready │ PageRank: 0.6, P1          ││
│  │0.68 │ bd-a3f8.2 Token valid│blocked│ Waiting on bd-a3f8.1       ││
│  │0.55 │ bd-c4d2.1 UI styling │ ready │ Low deps, P2               ││
│  │ ... │ ...                  │ ...   │ ...                        ││
│  └─────┴──────────────────────┴───────┴────────────────────────────┘│
│                                                                      │
│  Only "ready" tasks are eligible for assignment                      │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

## Dependency Unblock Analysis

When a task completes, Ringmaster calculates **unblock impact**:

```python
def unblock_impact(task, graph):
    """How many tasks become ready when this task completes?"""
    direct_unblocks = []

    for dependent in task.dependents:
        remaining_deps = [d for d in dependent.dependencies
                         if d.status != "done" and d != task]
        if len(remaining_deps) == 0:
            direct_unblocks.append(dependent)

    return direct_unblocks
```

This is surfaced in the UI and logs:
```
✓ Completed: bd-a3f8.1 (JWT tokens)
  Unblocked: bd-a3f8.2, bd-a3f8.3, bd-a3f8.4
  Queue depth: 47 → 50 ready tasks
```

## Cycle Detection

Cycles in the dependency graph are **fatal errors**. Ringmaster detects them during:

1. **Task creation** - Reject if adding dependency creates cycle
2. **Import** - Validate imported beads files
3. **Periodic scan** - Background check for corruption

```
⚠ Cycle detected: bd-a3f8.1 → bd-a3f8.3 → bd-a3f8.1
  Resolution required before tasks can be assigned
```

## Parallel Track Planning

Beyond individual priority, Ringmaster identifies **parallel execution tracks**:

```
Track 1: bd-a3f8.0 → bd-a3f8.1 → bd-a3f8.2
Track 2: bd-b2c1.0 → bd-b2c1.1 → bd-b2c1.2 → bd-b2c1.3
Track 3: bd-c4d2.0 → bd-c4d2.1

Workers can execute across tracks simultaneously.
Maximum parallelism: 3 independent tracks
```

## Configuration

```toml
# ringmaster.toml

[prioritization]
# Algorithm weights (must sum to 1.0)
pagerank_weight = 0.30
betweenness_weight = 0.25
critical_path_weight = 0.25
manual_priority_weight = 0.20

# Ready task boost
ready_multiplier = 1.5

# Recompute interval (graph metrics are cached)
recompute_interval_seconds = 60

# Manual priority mapping
[prioritization.manual_scores]
P0 = 1.0   # Critical - do immediately
P1 = 0.75  # High - do soon
P2 = 0.50  # Medium - normal queue
P3 = 0.25  # Low - when convenient
P4 = 0.10  # Backlog - eventually
```

## Integration with beads_viewer

For visualization and debugging, export to beads format and use `bv`:

```bash
# Export current state
ringmaster export --to-beads .beads/beads.jsonl

# View in beads_viewer
bv --robot-insights  # Graph metrics as JSON
bv --robot-plan      # Execution plan with parallel tracks
bv --robot-priority  # Priority recommendations
```

This provides a rich debugging interface while Ringmaster handles actual orchestration.

## References

- [beads_viewer](https://github.com/Dicklesworthstone/beads_viewer) - Graph analytics for beads
- [beads](https://github.com/steveyegge/beads) - Steve Yegge's task management system
- [@doodlestein's work](https://x.com/doodlestein/status/1997797659310956688) - 347 beads with dependency structure
