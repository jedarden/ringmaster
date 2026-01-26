import { useEffect, useState, useCallback } from "react";
import { getMetrics } from "../api/client";
import type { MetricsResponse, RecentEvent } from "../types";
import { useWebSocket, type WebSocketEvent } from "../hooks/useWebSocket";

function formatTimeAgo(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const seconds = Math.floor((now.getTime() - date.getTime()) / 1000);

  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

function getEventIcon(eventType: string): string {
  if (eventType.includes("completed")) return "+";
  if (eventType.includes("failed")) return "x";
  if (eventType.includes("assigned")) return ">";
  if (eventType.includes("created")) return "*";
  return "-";
}

function getEventClass(eventType: string): string {
  if (eventType.includes("completed")) return "event-success";
  if (eventType.includes("failed")) return "event-error";
  if (eventType.includes("assigned")) return "event-warning";
  return "event-info";
}

interface MetricsDashboardProps {
  autoRefresh?: boolean;
  refreshInterval?: number;
}

export function MetricsDashboard({
  autoRefresh = true,
  refreshInterval = 30000,
}: MetricsDashboardProps) {
  const [metrics, setMetrics] = useState<MetricsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadMetrics = useCallback(async () => {
    try {
      const data = await getMetrics(15);
      setMetrics(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load metrics");
    } finally {
      setLoading(false);
    }
  }, []);

  // Handle WebSocket events for real-time updates
  const handleEvent = useCallback(
    (event: WebSocketEvent) => {
      // Refresh on any task, worker, or queue event
      if (
        event.type.startsWith("task.") ||
        event.type.startsWith("worker.") ||
        event.type.startsWith("queue.")
      ) {
        loadMetrics();
      }
    },
    [loadMetrics]
  );

  useWebSocket({ onEvent: handleEvent });

  useEffect(() => {
    loadMetrics();
  }, [loadMetrics]);

  // Auto-refresh on interval
  useEffect(() => {
    if (!autoRefresh) return;

    const interval = setInterval(loadMetrics, refreshInterval);
    return () => clearInterval(interval);
  }, [autoRefresh, refreshInterval, loadMetrics]);

  if (loading && !metrics) {
    return <div className="metrics-dashboard loading">Loading metrics...</div>;
  }

  if (error) {
    return (
      <div className="metrics-dashboard error">
        <p>Error loading metrics: {error}</p>
        <button onClick={loadMetrics}>Retry</button>
      </div>
    );
  }

  if (!metrics) return null;

  const { task_stats, worker_stats, recent_events, activity_24h, activity_7d } =
    metrics;

  // Calculate completion rate
  const totalProcessed =
    worker_stats.total_completed + worker_stats.total_failed;
  const successRate =
    totalProcessed > 0
      ? Math.round((worker_stats.total_completed / totalProcessed) * 100)
      : 100;

  return (
    <div className="metrics-dashboard">
      <div className="metrics-header">
        <h2>Dashboard</h2>
        <button onClick={loadMetrics} className="refresh-btn">
          Refresh
        </button>
      </div>

      {/* Task Overview */}
      <section className="metrics-section">
        <h3>Tasks</h3>
        <div className="metrics-grid">
          <div className="metric-card total">
            <span className="metric-value">{task_stats.total}</span>
            <span className="metric-label">Total</span>
          </div>
          <div className="metric-card ready">
            <span className="metric-value">{task_stats.ready}</span>
            <span className="metric-label">Ready</span>
          </div>
          <div className="metric-card in-progress">
            <span className="metric-value">
              {task_stats.in_progress + task_stats.assigned}
            </span>
            <span className="metric-label">Active</span>
          </div>
          <div className="metric-card blocked">
            <span className="metric-value">{task_stats.blocked}</span>
            <span className="metric-label">Blocked</span>
          </div>
          <div className="metric-card completed">
            <span className="metric-value">{task_stats.done}</span>
            <span className="metric-label">Done</span>
          </div>
          <div className="metric-card failed">
            <span className="metric-value">{task_stats.failed}</span>
            <span className="metric-label">Failed</span>
          </div>
        </div>
      </section>

      {/* Worker Overview */}
      <section className="metrics-section">
        <h3>Workers</h3>
        <div className="metrics-row">
          <div className="metric-inline">
            <span className="metric-value idle">{worker_stats.idle}</span>
            <span className="metric-label">Idle</span>
          </div>
          <div className="metric-inline">
            <span className="metric-value busy">{worker_stats.busy}</span>
            <span className="metric-label">Busy</span>
          </div>
          <div className="metric-inline">
            <span className="metric-value offline">{worker_stats.offline}</span>
            <span className="metric-label">Offline</span>
          </div>
        </div>
        <div className="worker-totals">
          <span>
            Total completed: <strong>{worker_stats.total_completed}</strong>
          </span>
          <span className="divider">|</span>
          <span>
            Failed: <strong>{worker_stats.total_failed}</strong>
          </span>
          <span className="divider">|</span>
          <span>
            Success rate:{" "}
            <strong className={successRate >= 90 ? "success" : "warning"}>
              {successRate}%
            </strong>
          </span>
        </div>
      </section>

      {/* Activity Summary */}
      <section className="metrics-section">
        <h3>Activity</h3>
        <div className="activity-comparison">
          <div className="activity-period">
            <h4>Last 24 Hours</h4>
            <div className="activity-stats">
              <div className="activity-stat">
                <span className="value created">{activity_24h.tasks_created}</span>
                <span className="label">Created</span>
              </div>
              <div className="activity-stat">
                <span className="value completed">
                  {activity_24h.tasks_completed}
                </span>
                <span className="label">Completed</span>
              </div>
              <div className="activity-stat">
                <span className="value failed">{activity_24h.tasks_failed}</span>
                <span className="label">Failed</span>
              </div>
            </div>
          </div>
          <div className="activity-period">
            <h4>Last 7 Days</h4>
            <div className="activity-stats">
              <div className="activity-stat">
                <span className="value created">{activity_7d.tasks_created}</span>
                <span className="label">Created</span>
              </div>
              <div className="activity-stat">
                <span className="value completed">
                  {activity_7d.tasks_completed}
                </span>
                <span className="label">Completed</span>
              </div>
              <div className="activity-stat">
                <span className="value failed">{activity_7d.tasks_failed}</span>
                <span className="label">Failed</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Recent Events */}
      <section className="metrics-section">
        <h3>Recent Events</h3>
        {recent_events.length === 0 ? (
          <p className="no-events">No recent events</p>
        ) : (
          <div className="events-list">
            {recent_events.map((event: RecentEvent) => (
              <div
                key={event.id}
                className={`event-item ${getEventClass(event.event_type)}`}
              >
                <span className="event-icon">{getEventIcon(event.event_type)}</span>
                <span className="event-type">{event.event_type}</span>
                <span className="event-entity">
                  {event.entity_type}:{" "}
                  <code>{event.entity_id.substring(0, 8)}...</code>
                </span>
                <span className="event-time">
                  {formatTimeAgo(event.created_at)}
                </span>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
