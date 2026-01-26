import { useEffect, useState, useCallback } from "react";
import { getQueueStats, getReadyTasks } from "../api/client";
import type { QueueStats, Task } from "../types";
import { useWebSocket, type WebSocketEvent } from "../hooks/useWebSocket";

export function QueuePage() {
  const [stats, setStats] = useState<QueueStats | null>(null);
  const [readyTasks, setReadyTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      const [statsData, tasksData] = await Promise.all([
        getQueueStats(),
        getReadyTasks(),
      ]);
      setStats(statsData);
      setReadyTasks(tasksData);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load queue data");
    } finally {
      setLoading(false);
    }
  }, []);

  // Handle WebSocket events for real-time updates
  const handleEvent = useCallback((event: WebSocketEvent) => {
    // Refresh on task or queue events
    if (event.type.startsWith("task.") || event.type.startsWith("queue.") || event.type.startsWith("worker.")) {
      loadData();
    }
  }, [loadData]);

  useWebSocket({ onEvent: handleEvent });

  useEffect(() => {
    loadData();
  }, [loadData]);

  if (loading && !stats) {
    return <div className="loading">Loading queue...</div>;
  }

  return (
    <div className="queue-page">
      <div className="page-header">
        <h1>Queue</h1>
        <button onClick={loadData}>Refresh</button>
      </div>

      {error && <div className="error">{error}</div>}

      {stats && (
        <div className="stats-grid">
          <div className="stat-card">
            <h3>Total Tasks</h3>
            <span className="stat-value">{stats.total_tasks}</span>
          </div>
          <div className="stat-card ready">
            <h3>Ready</h3>
            <span className="stat-value">{stats.ready_tasks}</span>
          </div>
          <div className="stat-card in-progress">
            <h3>In Progress</h3>
            <span className="stat-value">{stats.in_progress_tasks}</span>
          </div>
          <div className="stat-card blocked">
            <h3>Blocked</h3>
            <span className="stat-value">{stats.blocked_tasks}</span>
          </div>
          <div className="stat-card completed">
            <h3>Completed</h3>
            <span className="stat-value">{stats.completed_tasks}</span>
          </div>
          <div className="stat-card failed">
            <h3>Failed</h3>
            <span className="stat-value">{stats.failed_tasks}</span>
          </div>
        </div>
      )}

      {stats && (
        <div className="workers-summary">
          <h2>Workers</h2>
          <div className="stats-row">
            <div className="stat-item">
              <span className="label">Total:</span>
              <span className="value">{stats.total_workers}</span>
            </div>
            <div className="stat-item">
              <span className="label">Idle:</span>
              <span className="value idle">{stats.idle_workers}</span>
            </div>
            <div className="stat-item">
              <span className="label">Busy:</span>
              <span className="value busy">{stats.busy_workers}</span>
            </div>
          </div>
        </div>
      )}

      <div className="section">
        <h2>Ready Tasks ({readyTasks.length})</h2>
        {readyTasks.length === 0 ? (
          <p className="empty-state">No tasks ready for assignment</p>
        ) : (
          <div className="ready-tasks-list">
            {readyTasks.map((task) => (
              <div key={task.id} className="task-row">
                <span className={`priority priority-${task.priority.toLowerCase()}`}>
                  {task.priority}
                </span>
                <span className="task-id">{task.id}</span>
                <span className="task-title">{task.title}</span>
                <span className="task-score" title="Combined priority score">
                  Score: {task.combined_priority.toFixed(2)}
                </span>
                {task.on_critical_path && (
                  <span className="critical-path-badge">Critical Path</span>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
