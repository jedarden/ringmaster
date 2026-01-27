import { useEffect, useState, useCallback, useRef } from "react";
import {
  listWorkersWithTasks,
  createWorker,
  activateWorker,
  deactivateWorker,
  deleteWorker,
  cancelWorkerTask,
  pauseWorker,
  spawnWorker,
  killWorker,
  listWorkerSessions,
} from "../api/client";
import type { TmuxSessionResponse, SpawnWorkerRequest } from "../types";
import { WorkerOutputPanel } from "../components/WorkerOutputPanel";
import type { WorkerWithTask, WorkerCreate } from "../types";
import { WorkerStatus } from "../types";
import { useWebSocket, type WebSocketEvent } from "../hooks/useWebSocket";
import { useListNavigation } from "../hooks/useKeyboardShortcuts";

// Helper to format elapsed time
function formatDuration(startedAt: string | null): string {
  if (!startedAt) return "";
  const start = new Date(startedAt).getTime();
  const now = Date.now();
  const diffMs = now - start;

  if (diffMs < 0) return "";

  const seconds = Math.floor(diffMs / 1000);
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);

  if (hours > 0) {
    return `${hours}h ${minutes % 60}m`;
  } else if (minutes > 0) {
    return `${minutes}m ${seconds % 60}s`;
  } else {
    return `${seconds}s`;
  }
}

export function WorkersPage() {
  const [workers, setWorkers] = useState<WorkerWithTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [newWorker, setNewWorker] = useState<WorkerCreate>({
    name: "",
    type: "claude-code",
    command: "claude",
  });
  const listRef = useRef<HTMLDivElement>(null);
  const [outputPanelWorkerId, setOutputPanelWorkerId] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [tmuxSessions, setTmuxSessions] = useState<TmuxSessionResponse[]>([]);
  const [showSpawnModal, setShowSpawnModal] = useState<string | null>(null);
  const [spawnConfig, setSpawnConfig] = useState<SpawnWorkerRequest>({
    worker_type: "claude-code",
    capabilities: [],
  });
  // Timer to update duration display for busy workers
  const [, setTick] = useState(0);

  const loadWorkers = useCallback(async () => {
    try {
      setLoading(true);
      const [workersData, sessionsData] = await Promise.all([
        listWorkersWithTasks(),
        listWorkerSessions().catch(() => []),
      ]);
      setWorkers(workersData);
      setTmuxSessions(sessionsData);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load workers");
    } finally {
      setLoading(false);
    }
  }, []);

  // Handle WebSocket events for real-time updates
  const handleEvent = useCallback((event: WebSocketEvent) => {
    if (event.type.startsWith("worker.")) {
      loadWorkers();
    }
  }, [loadWorkers]);

  useWebSocket({ onEvent: handleEvent });

  useEffect(() => {
    loadWorkers();
  }, [loadWorkers]);

  // Timer to update duration display for busy workers every second
  useEffect(() => {
    const hasBusyWorkers = workers.some((w) => w.status === WorkerStatus.BUSY);
    if (!hasBusyWorkers) return;

    const interval = setInterval(() => {
      setTick((t) => t + 1);
    }, 1000);

    return () => clearInterval(interval);
  }, [workers]);

  // Keyboard navigation for workers list
  const { selectedIndex, setSelectedIndex } = useListNavigation({
    items: workers,
    enabled: !showCreateForm,
    onSelect: (_worker, index) => {
      // Scroll selected item into view
      const items = listRef.current?.querySelectorAll(".worker-card");
      if (items?.[index]) {
        items[index].scrollIntoView({ block: "nearest", behavior: "smooth" });
      }
    },
    onOpen: (worker) => {
      // Toggle activation on Enter
      if (worker.status === WorkerStatus.OFFLINE) {
        handleActivate(worker.id);
      } else if (worker.status === WorkerStatus.IDLE) {
        handleDeactivate(worker.id);
      }
    },
  });

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newWorker.name.trim()) return;

    try {
      await createWorker(newWorker);
      setNewWorker({ name: "", type: "claude-code", command: "claude" });
      setShowCreateForm(false);
      await loadWorkers();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create worker");
    }
  };

  const handleActivate = async (id: string) => {
    try {
      await activateWorker(id);
      await loadWorkers();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to activate worker");
    }
  };

  const handleDeactivate = async (id: string) => {
    try {
      await deactivateWorker(id);
      await loadWorkers();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to deactivate worker");
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("Delete this worker?")) return;

    try {
      await deleteWorker(id);
      await loadWorkers();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete worker");
    }
  };

  const handleCancel = async (id: string) => {
    if (!confirm("Cancel the current task? The task will be marked as failed.")) return;

    try {
      setActionLoading(id);
      await cancelWorkerTask(id);
      await loadWorkers();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to cancel task");
    } finally {
      setActionLoading(null);
    }
  };

  const handlePause = async (id: string) => {
    try {
      setActionLoading(id);
      await pauseWorker(id);
      await loadWorkers();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to pause worker");
    } finally {
      setActionLoading(null);
    }
  };

  const handleSpawn = async (id: string) => {
    try {
      setActionLoading(id);
      await spawnWorker(id, spawnConfig);
      setShowSpawnModal(null);
      setSpawnConfig({ worker_type: "claude-code", capabilities: [] });
      await loadWorkers();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to spawn worker");
    } finally {
      setActionLoading(null);
    }
  };

  const handleKill = async (id: string) => {
    if (!confirm("Kill this worker's tmux session? This will terminate any running task.")) return;

    try {
      setActionLoading(id);
      await killWorker(id);
      await loadWorkers();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to kill worker");
    } finally {
      setActionLoading(null);
    }
  };

  // Check if a worker has an active tmux session
  const hasSession = (workerId: string) => {
    return tmuxSessions.some((s) => s.worker_id === workerId);
  };

  const getSession = (workerId: string) => {
    return tmuxSessions.find((s) => s.worker_id === workerId);
  };

  const getStatusColor = (status: WorkerStatus) => {
    switch (status) {
      case WorkerStatus.IDLE:
        return "status-idle";
      case WorkerStatus.BUSY:
        return "status-busy";
      case WorkerStatus.OFFLINE:
        return "status-offline";
    }
  };

  if (loading) {
    return <div className="loading">Loading workers...</div>;
  }

  const activeWorkers = workers.filter((w) => w.status !== WorkerStatus.OFFLINE);
  const offlineWorkers = workers.filter((w) => w.status === WorkerStatus.OFFLINE);

  // For keyboard selection, we need flat index mapping
  const getWorkerIndex = (worker: WorkerWithTask) => workers.findIndex(w => w.id === worker.id);

  return (
    <div className="workers-page">
      <div className="page-header">
        <h1>Workers</h1>
        <button onClick={() => setShowCreateForm(!showCreateForm)}>
          {showCreateForm ? "Cancel" : "+ New Worker"}
        </button>
      </div>

      {error && <div className="error">{error}</div>}

      {showCreateForm && (
        <form onSubmit={handleCreate} className="create-form">
          <input
            type="text"
            placeholder="Worker name"
            value={newWorker.name}
            onChange={(e) => setNewWorker({ ...newWorker, name: e.target.value })}
            required
            autoFocus
          />
          <select
            value={newWorker.type}
            onChange={(e) => setNewWorker({ ...newWorker, type: e.target.value })}
          >
            <option value="claude-code">Claude Code</option>
            <option value="aider">Aider</option>
            <option value="codex">Codex</option>
            <option value="goose">Goose</option>
            <option value="custom">Custom</option>
          </select>
          <input
            type="text"
            placeholder="Command (e.g., claude)"
            value={newWorker.command}
            onChange={(e) => setNewWorker({ ...newWorker, command: e.target.value })}
            required
          />
          <button type="submit">Create Worker</button>
        </form>
      )}

      {workers.length === 0 ? (
        <div className="empty-state">
          <p>No workers configured. Add one to get started!</p>
        </div>
      ) : (
        <div ref={listRef}>
          {activeWorkers.length > 0 && (
            <div className="section">
              <h2>Active Workers ({activeWorkers.length})</h2>
              <div className="workers-list">
                {activeWorkers.map((worker) => {
                  const idx = getWorkerIndex(worker);
                  return (
                    <div
                      key={worker.id}
                      className={`worker-card ${idx === selectedIndex ? "keyboard-selected" : ""}`}
                      onClick={() => setSelectedIndex(idx)}
                    >
                      <div className="worker-header">
                        <span className={`status-badge ${getStatusColor(worker.status)}`}>
                          {worker.status}
                        </span>
                        <h3>{worker.name}</h3>
                        <span className="worker-type">{worker.type}</span>
                      </div>
                      <div className="worker-info">
                        <p>Command: <code>{worker.command}</code></p>
                        {worker.current_task && (
                          <div className="current-task-info">
                            <p className="task-title">
                              <strong>Task:</strong> {worker.current_task.title}
                            </p>
                            <p className="task-meta">
                              <span className="iteration">
                                Iteration {worker.current_task.attempts}/{worker.current_task.max_attempts}
                              </span>
                              {worker.current_task.started_at && (
                                <span className="duration">
                                  Duration: {formatDuration(worker.current_task.started_at)}
                                </span>
                              )}
                            </p>
                          </div>
                        )}
                        {!worker.current_task && worker.current_task_id && (
                          <p>Current task: {worker.current_task_id}</p>
                        )}
                        <p>
                          Stats: {worker.tasks_completed} completed / {worker.tasks_failed} failed
                        </p>
                        {hasSession(worker.id) && (
                          <p className="tmux-info">
                            <span className="tmux-badge">tmux</span>
                            <code>{getSession(worker.id)?.attach_command}</code>
                          </p>
                        )}
                      </div>
                      <div className="worker-actions">
                        {worker.status === WorkerStatus.IDLE ? (
                          <>
                            {hasSession(worker.id) ? (
                              <button
                                onClick={() => handleKill(worker.id)}
                                disabled={actionLoading === worker.id}
                                className="kill-btn"
                                title="Kill tmux session"
                              >
                                {actionLoading === worker.id ? "..." : "Kill Session"}
                              </button>
                            ) : (
                              <button
                                onClick={() => setShowSpawnModal(worker.id)}
                                className="spawn-btn"
                                title="Spawn worker in tmux session"
                              >
                                Spawn
                              </button>
                            )}
                            <button onClick={() => handleDeactivate(worker.id)}>
                              Deactivate
                            </button>
                          </>
                        ) : worker.status === WorkerStatus.BUSY ? (
                          <>
                            <button
                              onClick={() => setOutputPanelWorkerId(worker.id)}
                              className="view-output-btn"
                              title="View live output"
                            >
                              View Output
                            </button>
                            <button
                              onClick={() => handlePause(worker.id)}
                              disabled={actionLoading === worker.id}
                              className="pause-btn"
                              title="Pause worker after current iteration"
                            >
                              {actionLoading === worker.id ? "..." : "Pause"}
                            </button>
                            <button
                              onClick={() => handleCancel(worker.id)}
                              disabled={actionLoading === worker.id}
                              className="cancel-btn"
                              title="Cancel current task immediately"
                            >
                              {actionLoading === worker.id ? "..." : "Cancel"}
                            </button>
                            {hasSession(worker.id) && (
                              <button
                                onClick={() => handleKill(worker.id)}
                                disabled={actionLoading === worker.id}
                                className="kill-btn"
                                title="Kill tmux session"
                              >
                                {actionLoading === worker.id ? "..." : "Kill"}
                              </button>
                            )}
                          </>
                        ) : null}
                        <button
                          onClick={() => handleDelete(worker.id)}
                          className="delete-btn"
                        >
                          Delete
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {offlineWorkers.length > 0 && (
            <div className="section">
              <h2>Offline Workers ({offlineWorkers.length})</h2>
              <div className="workers-list">
                {offlineWorkers.map((worker) => {
                  const idx = getWorkerIndex(worker);
                  return (
                    <div
                      key={worker.id}
                      className={`worker-card offline ${idx === selectedIndex ? "keyboard-selected" : ""}`}
                      onClick={() => setSelectedIndex(idx)}
                    >
                      <div className="worker-header">
                        <span className={`status-badge ${getStatusColor(worker.status)}`}>
                          {worker.status}
                        </span>
                        <h3>{worker.name}</h3>
                        <span className="worker-type">{worker.type}</span>
                      </div>
                      <div className="worker-actions">
                        <button
                          onClick={() => setShowSpawnModal(worker.id)}
                          className="spawn-btn"
                          title="Spawn worker in tmux session"
                        >
                          Spawn in Tmux
                        </button>
                        <button onClick={() => handleActivate(worker.id)}>
                          Activate
                        </button>
                        <button
                          onClick={() => handleDelete(worker.id)}
                          className="delete-btn"
                        >
                          Delete
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Spawn Worker Modal */}
      {showSpawnModal && (
        <div className="modal-overlay" onClick={() => setShowSpawnModal(null)}>
          <div className="modal spawn-modal" onClick={(e) => e.stopPropagation()}>
            <h2>Spawn Worker: {showSpawnModal}</h2>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                handleSpawn(showSpawnModal);
              }}
            >
              <div className="form-group">
                <label>Worker Type</label>
                <select
                  value={spawnConfig.worker_type}
                  onChange={(e) =>
                    setSpawnConfig({ ...spawnConfig, worker_type: e.target.value })
                  }
                >
                  <option value="claude-code">Claude Code</option>
                  <option value="aider">Aider</option>
                  <option value="codex">Codex</option>
                  <option value="goose">Goose</option>
                  <option value="generic">Generic (custom command)</option>
                </select>
              </div>
              <div className="form-group">
                <label>Capabilities (comma-separated)</label>
                <input
                  type="text"
                  placeholder="python, typescript, security"
                  value={spawnConfig.capabilities?.join(", ") || ""}
                  onChange={(e) =>
                    setSpawnConfig({
                      ...spawnConfig,
                      capabilities: e.target.value
                        .split(",")
                        .map((s) => s.trim())
                        .filter(Boolean),
                    })
                  }
                />
              </div>
              {spawnConfig.worker_type === "generic" && (
                <div className="form-group">
                  <label>Custom Command</label>
                  <input
                    type="text"
                    placeholder="my-tool --auto"
                    value={spawnConfig.custom_command || ""}
                    onChange={(e) =>
                      setSpawnConfig({ ...spawnConfig, custom_command: e.target.value })
                    }
                  />
                </div>
              )}
              <div className="form-group">
                <label>Worktree Path (optional)</label>
                <input
                  type="text"
                  placeholder="/workspace/project"
                  value={spawnConfig.worktree_path || ""}
                  onChange={(e) =>
                    setSpawnConfig({
                      ...spawnConfig,
                      worktree_path: e.target.value || null,
                    })
                  }
                />
              </div>
              <div className="modal-actions">
                <button
                  type="button"
                  onClick={() => setShowSpawnModal(null)}
                  className="secondary"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={actionLoading === showSpawnModal}
                  className="primary spawn-btn"
                >
                  {actionLoading === showSpawnModal ? "Spawning..." : "Spawn Worker"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Keyboard navigation hint */}
      {workers.length > 0 && !showCreateForm && (
        <div
          style={{
            marginTop: "1rem",
            fontSize: "0.8rem",
            color: "var(--color-text-muted)",
          }}
        >
          Use <kbd style={{ background: "var(--color-surface)", padding: "0.1rem 0.4rem", borderRadius: "3px" }}>j</kbd>/<kbd style={{ background: "var(--color-surface)", padding: "0.1rem 0.4rem", borderRadius: "3px" }}>k</kbd> to navigate, <kbd style={{ background: "var(--color-surface)", padding: "0.1rem 0.4rem", borderRadius: "3px" }}>Enter</kbd> to toggle
        </div>
      )}

      {/* Worker Output Panel */}
      {outputPanelWorkerId && (
        <WorkerOutputPanel
          workerId={outputPanelWorkerId}
          isOpen={!!outputPanelWorkerId}
          onClose={() => setOutputPanelWorkerId(null)}
        />
      )}
    </div>
  );
}
