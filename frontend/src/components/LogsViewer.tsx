import { useEffect, useState, useCallback, useRef } from "react";
import { listLogs, getLogStats, getRecentLogs } from "../api/client";
import type { LogEntry, LogStats, LogLevel, LogComponent } from "../types";
import { LogLevel as LogLevelEnum, LogComponent as LogComponentEnum } from "../types";
import { useWebSocket, type WebSocketEvent } from "../hooks/useWebSocket";

function formatTimestamp(isoString: string): string {
  const date = new Date(isoString);
  return date.toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

function formatDate(isoString: string): string {
  const date = new Date(isoString);
  return date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
}

function getLevelClass(level: string): string {
  switch (level) {
    case "debug":
      return "log-level-debug";
    case "info":
      return "log-level-info";
    case "warning":
      return "log-level-warning";
    case "error":
      return "log-level-error";
    case "critical":
      return "log-level-critical";
    default:
      return "";
  }
}

function getLevelIcon(level: string): string {
  switch (level) {
    case "debug":
      return "~";
    case "info":
      return "i";
    case "warning":
      return "!";
    case "error":
      return "x";
    case "critical":
      return "X";
    default:
      return "-";
  }
}

interface LogsViewerProps {
  taskId?: string;
  workerId?: string;
  projectId?: string;
  autoRefresh?: boolean;
  refreshInterval?: number;
}

export function LogsViewer({
  taskId,
  workerId,
  projectId,
  autoRefresh = true,
  refreshInterval = 5000,
}: LogsViewerProps) {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [stats, setStats] = useState<LogStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [limit] = useState(100);

  // Filter state
  const [levelFilter, setLevelFilter] = useState<LogLevel | "">("");
  const [componentFilter, setComponentFilter] = useState<LogComponent | "">("");
  const [searchQuery, setSearchQuery] = useState("");
  const [liveMode, setLiveMode] = useState(true);

  // Expanded log details
  const [expandedLogId, setExpandedLogId] = useState<number | null>(null);

  // Track seen log IDs to prevent duplicates from both WS and REST
  const seenLogIds = useRef<Set<number>>(new Set());

  // WebSocket handler for real-time log updates
  const handleLogEvent = useCallback(
    (event: WebSocketEvent) => {
      if (event.type !== "log.created" || !liveMode) return;

      const data = event.data as {
        id: number;
        timestamp: string;
        level: string;
        component: string;
        message: string;
        task_id?: string | null;
        worker_id?: string | null;
        data?: Record<string, unknown> | null;
      };

      // Check if we've already seen this log (from initial load or duplicate WS message)
      if (seenLogIds.current.has(data.id)) return;
      seenLogIds.current.add(data.id);

      // Apply filters
      if (levelFilter && data.level !== levelFilter) return;
      if (componentFilter && data.component !== componentFilter) return;
      if (taskId && data.task_id !== taskId) return;
      if (workerId && data.worker_id !== workerId) return;
      if (projectId && event.project_id !== projectId) return;

      // Create log entry from event data
      const newLog: LogEntry = {
        id: data.id,
        timestamp: data.timestamp,
        level: data.level as LogLevel,
        component: data.component as LogComponent,
        message: data.message,
        task_id: data.task_id ?? null,
        worker_id: data.worker_id ?? null,
        project_id: event.project_id ?? null,
        data: data.data ?? null,
      };

      // Prepend new log to list (newest first)
      setLogs((prev) => [newLog, ...prev].slice(0, limit));
      setTotal((prev) => prev + 1);
    },
    [liveMode, levelFilter, componentFilter, taskId, workerId, projectId, limit]
  );

  // Connect to WebSocket for real-time updates
  const { connected } = useWebSocket({
    projectId,
    onEvent: handleLogEvent,
  });

  const loadLogs = useCallback(async () => {
    try {
      if (liveMode) {
        // In live mode, get recent logs
        const recentLogs = await getRecentLogs(60, limit);
        // Apply client-side filtering for live mode
        let filtered = recentLogs;
        if (levelFilter) {
          filtered = filtered.filter((l) => l.level === levelFilter);
        }
        if (componentFilter) {
          filtered = filtered.filter((l) => l.component === componentFilter);
        }
        if (taskId) {
          filtered = filtered.filter((l) => l.task_id === taskId);
        }
        if (workerId) {
          filtered = filtered.filter((l) => l.worker_id === workerId);
        }
        if (projectId) {
          filtered = filtered.filter((l) => l.project_id === projectId);
        }
        // Track seen log IDs to prevent duplicates from WebSocket
        seenLogIds.current = new Set(filtered.map((l) => l.id));
        setLogs(filtered);
        setTotal(filtered.length);
      } else {
        // In paginated mode, use list endpoint with filters
        const response = await listLogs({
          level: levelFilter || undefined,
          component: componentFilter || undefined,
          task_id: taskId,
          worker_id: workerId,
          project_id: projectId,
          search: searchQuery || undefined,
          offset,
          limit,
        });
        setLogs(response.logs);
        setTotal(response.total);
      }
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load logs");
    } finally {
      setLoading(false);
    }
  }, [
    liveMode,
    levelFilter,
    componentFilter,
    searchQuery,
    taskId,
    workerId,
    projectId,
    offset,
    limit,
  ]);

  const loadStats = useCallback(async () => {
    try {
      const statsData = await getLogStats(24);
      setStats(statsData);
    } catch {
      // Stats are optional, don't set error
    }
  }, []);

  useEffect(() => {
    loadLogs();
    loadStats();
  }, [loadLogs, loadStats]);

  // Auto-refresh in live mode
  useEffect(() => {
    if (!autoRefresh || !liveMode) return;

    const interval = setInterval(loadLogs, refreshInterval);
    return () => clearInterval(interval);
  }, [autoRefresh, liveMode, refreshInterval, loadLogs]);

  // Reset offset when filters change
  useEffect(() => {
    setOffset(0);
  }, [levelFilter, componentFilter, searchQuery]);

  const toggleLogExpanded = (logId: number) => {
    setExpandedLogId(expandedLogId === logId ? null : logId);
  };

  if (loading && logs.length === 0) {
    return <div className="logs-viewer loading">Loading logs...</div>;
  }

  if (error) {
    return (
      <div className="logs-viewer error">
        <p>Error loading logs: {error}</p>
        <button onClick={loadLogs}>Retry</button>
      </div>
    );
  }

  return (
    <div className="logs-viewer">
      {/* Stats Bar */}
      {stats && (
        <div className="logs-stats-bar">
          <span className="stat">
            Total (24h): <strong>{stats.total}</strong>
          </span>
          <span className="stat errors">
            Errors: <strong>{stats.errors}</strong>
          </span>
          {Object.entries(stats.by_level).map(([level, count]) => (
            <span key={level} className={`stat ${getLevelClass(level)}`}>
              {level}: <strong>{count}</strong>
            </span>
          ))}
        </div>
      )}

      {/* Filters */}
      <div className="logs-filters">
        <div className="filter-group">
          <label>Level:</label>
          <select
            value={levelFilter}
            onChange={(e) => setLevelFilter(e.target.value as LogLevel | "")}
          >
            <option value="">All</option>
            {Object.values(LogLevelEnum).map((level) => (
              <option key={level} value={level}>
                {level}
              </option>
            ))}
          </select>
        </div>

        <div className="filter-group">
          <label>Component:</label>
          <select
            value={componentFilter}
            onChange={(e) => setComponentFilter(e.target.value as LogComponent | "")}
          >
            <option value="">All</option>
            {Object.values(LogComponentEnum).map((comp) => (
              <option key={comp} value={comp}>
                {comp}
              </option>
            ))}
          </select>
        </div>

        <div className="filter-group search">
          <label>Search:</label>
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search messages..."
            disabled={liveMode}
          />
        </div>

        <div className="filter-group toggle">
          <label>
            <input
              type="checkbox"
              checked={liveMode}
              onChange={(e) => setLiveMode(e.target.checked)}
            />
            Live mode
          </label>
        </div>

        <button onClick={loadLogs} className="refresh-btn">
          Refresh
        </button>
      </div>

      {/* Log Count */}
      <div className="logs-count">
        Showing {logs.length} of {total} logs
        {liveMode && (
          <span className={`live-indicator ${connected ? "connected" : "disconnected"}`}>
            {" "}
            ({connected ? "live" : "reconnecting..."})
          </span>
        )}
      </div>

      {/* Log List */}
      <div className="logs-list">
        {logs.length === 0 ? (
          <div className="no-logs">No logs found</div>
        ) : (
          logs.map((log) => (
            <div
              key={log.id}
              className={`log-entry ${getLevelClass(log.level)} ${
                expandedLogId === log.id ? "expanded" : ""
              }`}
              onClick={() => toggleLogExpanded(log.id)}
            >
              <div className="log-header">
                <span className="log-icon">{getLevelIcon(log.level)}</span>
                <span className="log-timestamp">
                  {formatDate(log.timestamp)} {formatTimestamp(log.timestamp)}
                </span>
                <span className={`log-level ${getLevelClass(log.level)}`}>
                  {log.level.toUpperCase()}
                </span>
                <span className="log-component">[{log.component}]</span>
                <span className="log-message">{log.message}</span>
              </div>
              {expandedLogId === log.id && (
                <div className="log-details">
                  {log.task_id && (
                    <div className="log-detail">
                      <strong>Task:</strong> <code>{log.task_id}</code>
                    </div>
                  )}
                  {log.worker_id && (
                    <div className="log-detail">
                      <strong>Worker:</strong> <code>{log.worker_id}</code>
                    </div>
                  )}
                  {log.project_id && (
                    <div className="log-detail">
                      <strong>Project:</strong> <code>{log.project_id}</code>
                    </div>
                  )}
                  {log.data && (
                    <div className="log-detail data">
                      <strong>Data:</strong>
                      <pre>{JSON.stringify(log.data, null, 2)}</pre>
                    </div>
                  )}
                </div>
              )}
            </div>
          ))
        )}
      </div>

      {/* Pagination (only in non-live mode) */}
      {!liveMode && total > limit && (
        <div className="logs-pagination">
          <button
            disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - limit))}
          >
            Previous
          </button>
          <span>
            Page {Math.floor(offset / limit) + 1} of {Math.ceil(total / limit)}
          </span>
          <button
            disabled={offset + limit >= total}
            onClick={() => setOffset(offset + limit)}
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
