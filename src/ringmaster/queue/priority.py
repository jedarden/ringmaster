"""Priority calculation using graph algorithms.

Based on docs/03-prioritization.md:
- PageRank for importance in dependency graph
- Betweenness centrality for bottleneck detection
- Critical path for deadline-driven scheduling
"""

import logging
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from uuid import UUID

from ringmaster.db import Database, TaskRepository
from ringmaster.domain import Priority, Task

logger = logging.getLogger(__name__)

# Priority weights
PRIORITY_WEIGHTS = {
    Priority.P0: 1.0,
    Priority.P1: 0.8,
    Priority.P2: 0.6,
    Priority.P3: 0.4,
    Priority.P4: 0.2,
}


class PriorityCalculator:
    """Calculate task priorities using graph algorithms."""

    def __init__(self, db: Database):
        self.db = db
        self.task_repo = TaskRepository(db)

    async def recalculate_priorities(self, project_id: UUID) -> int:
        """Recalculate priorities for all tasks in a project.

        Returns the number of tasks updated.
        """
        # Load all tasks and dependencies
        tasks = await self.task_repo.list_tasks(project_id=project_id)
        task_map = {t.id: t for t in tasks}

        # Build adjacency lists
        dependents: dict[str, list[str]] = defaultdict(list)  # task -> tasks that depend on it
        dependencies: dict[str, list[str]] = defaultdict(list)  # task -> tasks it depends on

        for task in tasks:
            if isinstance(task, Task):
                deps = await self.task_repo.get_dependencies(task.id)
                for dep in deps:
                    dependents[dep.parent_id].append(dep.child_id)
                    dependencies[dep.child_id].append(dep.parent_id)

        # Calculate PageRank
        pagerank = self._calculate_pagerank(task_map, dependents)

        # Calculate betweenness centrality
        betweenness = self._calculate_betweenness(task_map, dependents, dependencies)

        # Find critical path
        critical_path = self._find_critical_path(task_map, dependents, dependencies)

        # Calculate base combined priority for all tasks
        combined_priorities: dict[str, float] = {}
        for task_id, task in task_map.items():
            if not isinstance(task, Task):
                continue

            base_priority = PRIORITY_WEIGHTS.get(task.priority, 0.5)
            combined_priorities[task_id] = (
                base_priority * 0.4
                + pagerank.get(task_id, 0) * 0.3
                + betweenness.get(task_id, 0) * 0.2
                + (0.1 if task_id in critical_path else 0)
            )

        # Apply priority inheritance: blockers inherit priority from blocked tasks
        inherited_priorities = self._apply_priority_inheritance(
            task_map, combined_priorities, dependents, dependencies
        )

        # Update tasks with new scores
        updated = 0
        for task_id, task in task_map.items():
            if not isinstance(task, Task):
                continue

            task.pagerank_score = pagerank.get(task_id, 0)
            task.betweenness_score = betweenness.get(task_id, 0)
            task.on_critical_path = task_id in critical_path
            task.combined_priority = inherited_priorities.get(task_id, combined_priorities.get(task_id, 0))

            await self.task_repo.update_task(task)
            updated += 1

        logger.info(f"Recalculated priorities for {updated} tasks in project {project_id}")
        return updated

    def _apply_priority_inheritance(
        self,
        task_map: dict[str, Task],
        base_priorities: dict[str, float],
        dependents: dict[str, list[str]],
        dependencies: dict[str, list[str]],
    ) -> dict[str, float]:
        """Apply priority inheritance: blockers inherit priority from blocked tasks.

        If a high-priority task is blocked by a lower-priority task, the blocker
        inherits the higher priority. This prevents queue starvation where important
        tasks get stuck behind their lower-priority dependencies.

        Per docs/09-remaining-decisions.md Section 9.

        Args:
            task_map: Map of task_id to Task objects.
            base_priorities: Calculated combined priority scores.
            dependents: Map of task_id to tasks that depend on it.
            dependencies: Map of task_id to tasks it depends on.

        Returns:
            Updated priority scores with inheritance applied.
        """
        from ringmaster.domain import TaskStatus

        # Start with base priorities
        inherited = base_priorities.copy()

        # Find blocked tasks and propagate their priority to blockers
        # We need to iterate until no more changes (transitive inheritance)
        changed = True
        max_iterations = 100  # Prevent infinite loops
        iteration = 0

        while changed and iteration < max_iterations:
            changed = False
            iteration += 1

            for task_id, task in task_map.items():
                if not isinstance(task, Task):
                    continue

                # Check if task is blocked (has incomplete dependencies)
                if task.status != TaskStatus.BLOCKED:
                    continue

                task_priority = inherited.get(task_id, 0)

                # Propagate priority to all incomplete blockers
                for blocker_id in dependencies.get(task_id, []):
                    if blocker_id not in task_map:
                        continue

                    blocker = task_map[blocker_id]
                    if not isinstance(blocker, Task):
                        continue

                    # Only inherit if blocker is not completed
                    if blocker.status in (TaskStatus.DONE, TaskStatus.FAILED):
                        continue

                    blocker_priority = inherited.get(blocker_id, 0)

                    # If blocked task has higher priority, blocker inherits it
                    if task_priority > blocker_priority:
                        inherited[blocker_id] = task_priority
                        changed = True
                        logger.debug(
                            f"Priority inheritance: {blocker_id} inherits {task_priority:.3f} "
                            f"from blocked {task_id} (was {blocker_priority:.3f})"
                        )

        if iteration >= max_iterations:
            logger.warning("Priority inheritance reached max iterations - possible cycle in dependencies")

        return inherited

    def _calculate_pagerank(
        self,
        task_map: dict[str, Task],
        dependents: dict[str, list[str]],
        damping: float = 0.85,
        iterations: int = 20,
    ) -> dict[str, float]:
        """Calculate PageRank scores for tasks.

        Tasks with many dependents (blockers) get higher scores.
        """
        n = len(task_map)
        if n == 0:
            return {}

        # Initialize scores
        scores = dict.fromkeys(task_map, 1.0 / n)

        for _ in range(iterations):
            new_scores = {}
            for task_id in task_map:
                # Base score from damping
                score = (1 - damping) / n

                # Add contributions from tasks that depend on this one
                for dep_id in dependents.get(task_id, []):
                    if dep_id in task_map:
                        out_degree = len(dependents.get(dep_id, [])) or 1
                        score += damping * scores[dep_id] / out_degree

                new_scores[task_id] = score

            scores = new_scores

        # Normalize to 0-1 range
        max_score = max(scores.values()) if scores else 1
        return {k: v / max_score for k, v in scores.items()}

    def _calculate_betweenness(
        self,
        task_map: dict[str, Task],
        dependents: dict[str, list[str]],
        dependencies: dict[str, list[str]],
    ) -> dict[str, float]:
        """Calculate betweenness centrality.

        Tasks that lie on many shortest paths get higher scores (bottlenecks).
        """
        betweenness = dict.fromkeys(task_map, 0.0)

        for source in task_map:
            # BFS to find shortest paths
            distances: dict[str, int] = {source: 0}
            paths: dict[str, list[list[str]]] = {source: [[source]]}
            queue = [source]

            while queue:
                current = queue.pop(0)
                current_dist = distances[current]

                # Follow dependencies (edges)
                for neighbor in dependents.get(current, []):
                    if neighbor not in task_map:
                        continue

                    if neighbor not in distances:
                        distances[neighbor] = current_dist + 1
                        paths[neighbor] = []
                        queue.append(neighbor)

                    if distances[neighbor] == current_dist + 1:
                        for path in paths[current]:
                            paths[neighbor].append(path + [neighbor])

            # Count paths through each node
            for target in task_map:
                if target == source:
                    continue
                for path in paths.get(target, []):
                    for node in path[1:-1]:  # Exclude source and target
                        betweenness[node] += 1

        # Normalize
        max_score = max(betweenness.values()) if betweenness else 1
        if max_score > 0:
            return {k: v / max_score for k, v in betweenness.items()}
        return betweenness

    def _find_critical_path(
        self,
        task_map: dict[str, Task],
        dependents: dict[str, list[str]],
        dependencies: dict[str, list[str]],
    ) -> set[str]:
        """Find tasks on the critical path (longest path through DAG)."""
        # Find sources (tasks with no dependencies)
        sources = [
            task_id for task_id in task_map
            if not dependencies.get(task_id)
        ]

        # Find sinks (tasks with no dependents)
        sinks = [
            task_id for task_id in task_map
            if not dependents.get(task_id)
        ]

        if not sources or not sinks:
            return set()

        # Calculate longest path from each source using dynamic programming
        longest_to: dict[str, int] = {}
        predecessor: dict[str, str | None] = {}

        def get_longest_path_to(task_id: str) -> int:
            if task_id in longest_to:
                return longest_to[task_id]

            deps = dependencies.get(task_id, [])
            if not deps:
                longest_to[task_id] = 0
                predecessor[task_id] = None
                return 0

            max_len = 0
            best_pred = None
            for dep_id in deps:
                if dep_id in task_map:
                    path_len = get_longest_path_to(dep_id) + 1
                    if path_len > max_len:
                        max_len = path_len
                        best_pred = dep_id

            longest_to[task_id] = max_len
            predecessor[task_id] = best_pred
            return max_len

        # Find the sink with the longest path
        max_path_len = 0
        critical_sink = None
        for sink in sinks:
            path_len = get_longest_path_to(sink)
            if path_len > max_path_len:
                max_path_len = path_len
                critical_sink = sink

        # Trace back the critical path
        critical_path = set()
        current = critical_sink
        while current:
            critical_path.add(current)
            current = predecessor.get(current)

        return critical_path


class DeadlineCalculator:
    """Calculate deadlines based on critical path analysis."""

    @staticmethod
    def estimate_completion(
        task: Task,
        avg_task_duration: timedelta = timedelta(hours=2),
    ) -> datetime:
        """Estimate completion time for a task based on its position."""
        # Simple estimation: base duration * (1 + attempts) for retry buffer
        buffer_factor = 1 + (task.attempts * 0.5)
        estimated_duration = avg_task_duration * buffer_factor

        if task.started_at:
            return task.started_at + estimated_duration
        return datetime.now(UTC) + estimated_duration
