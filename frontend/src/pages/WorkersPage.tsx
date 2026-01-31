import { useEffect, useState, useCallback, useRef } from "react";
import {
  listWorkersWithTasks,
  createWorker,
  updateWorker,
  activateWorker,
  deactivateWorker,
  deleteWorker,
  cancelWorkerTask,
  pauseWorker,
  pauseAllWorkers,
  spawnWorker,
  killWorker,
  listWorkerSessions,
  getWorkerHealth,
  naturalLanguageToSettings,
} from "../api/client";
import type { TmuxSessionResponse, SpawnWorkerRequest, WorkerHealthResponse } from "../types";
import { WorkerOutputPanel } from "../components/WorkerOutputPanel";
import type { WorkerWithTask, WorkerCreate } from "../types";
import { WorkerStatus, LivenessStatus, RecoveryUrgency } from "../types";
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
  // Modal state: null = closed, "new" = create mode, worker ID = edit mode
  const [showWorkerModal, setShowWorkerModal] = useState<string | null>(null);
  const [workerFormData, setWorkerFormData] = useState<WorkerCreate & { generated_script?: string }>({
    name: "",
    type: "claude-code",
    capabilities: [],
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
  // Health status for busy workers
  const [workerHealth, setWorkerHealth] = useState<Record<string, WorkerHealthResponse>>({});
  // AI settings generation
  const [aiLoading, setAiLoading] = useState(false);
  const [naturalLanguage, setNaturalLanguage] = useState("");

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

      // Fetch health data for busy workers
      const busyWorkers = workersData.filter(w => w.status === WorkerStatus.BUSY);
      if (busyWorkers.length > 0) {
        const healthPromises = busyWorkers.map(w =>
          getWorkerHealth(w.id).catch(() => null)
        );
        const healthResults = await Promise.all(healthPromises);
        const healthMap: Record<string, WorkerHealthResponse> = {};
        busyWorkers.forEach((w, i) => {
          if (healthResults[i]) {
            healthMap[w.id] = healthResults[i]!;
          }
        });
        setWorkerHealth(healthMap);
      } else {
        setWorkerHealth({});
      }
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
    enabled: !showWorkerModal,
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

  // Open modal for creating a new worker
  const handleOpenCreate = () => {
    setWorkerFormData({
      name: "",
      type: "claude-code",
      capabilities: [],
      description: undefined,
      generated_script: undefined,
    });
    setNaturalLanguage("");
    setShowWorkerModal("new");
  };

  // Open modal for editing an existing worker (pre-filled)
  const handleOpenEdit = (id: string) => {
    const worker = workers.find(w => w.id === id);
    if (!worker) return;

    setWorkerFormData({
      name: worker.name,
      type: worker.type,
      capabilities: worker.capabilities || [],
      description: worker.description || undefined,
      generated_script: worker.generated_script || undefined,
    });
    setNaturalLanguage("");
    setShowWorkerModal(id);
  };

  // Handle form submission for both create and edit
  const handleWorkerSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!workerFormData.name.trim()) return;

    try {
      if (showWorkerModal === "new") {
        // Create new worker
        await createWorker(workerFormData);
      } else {
        // Update existing worker
        await updateWorker(showWorkerModal!, {
          name: workerFormData.name,
          description: workerFormData.description,
          generated_script: workerFormData.generated_script,
          capabilities: workerFormData.capabilities,
        });
      }
      setShowWorkerModal(null);
      setWorkerFormData({ name: "", type: "claude-code", capabilities: [] });
      setNaturalLanguage("");
      await loadWorkers();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save worker");
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

  const handleAIGenerate = async () => {
    if (!naturalLanguage.trim()) {
      setError("Please enter a description of the worker");
      return;
    }

    setAiLoading(true);
    try {
      const response = await naturalLanguageToSettings({
        natural_language: naturalLanguage,
        settings_type: "worker",
      });

      if (response.success && response.worker_settings) {
        const settings = response.worker_settings;
        // Update the form with AI-generated settings
        setWorkerFormData((prev) => ({
          ...prev,
          name: settings.name || prev.name,
          description: settings.description || prev.description,
          type: settings.type || prev.type,
          generated_script: settings.generated_script || prev.generated_script,
          capabilities: settings.capabilities || prev.capabilities,
        }));
        setError(null);
      } else {
        setError(response.error || "Failed to generate settings from AI");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate settings");
    } finally {
      setAiLoading(false);
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

  const [pauseAllLoading, setPauseAllLoading] = useState(false);

  const handlePauseAll = async () => {
    if (!confirm("Pause all active workers? They will complete their current tasks and then stop.")) return;

    try {
      setPauseAllLoading(true);
      const result = await pauseAllWorkers();
      if (result.paused_count > 0) {
        await loadWorkers();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to pause all workers");
    } finally {
      setPauseAllLoading(false);
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

  const getLivenessColor = (status: string) => {
    switch (status) {
      case LivenessStatus.ACTIVE:
        return "health-active";
      case LivenessStatus.THINKING:
        return "health-thinking";
      case LivenessStatus.SLOW:
        return "health-slow";
      case LivenessStatus.LIKELY_HUNG:
        return "health-hung";
      case LivenessStatus.DEGRADED:
        return "health-degraded";
      default:
        return "health-unknown";
    }
  };

  const getLivenessIcon = (status: string) => {
    switch (status) {
      case LivenessStatus.ACTIVE:
        return "🟢";
      case LivenessStatus.THINKING:
        return "🤔";
      case LivenessStatus.SLOW:
        return "🐢";
      case LivenessStatus.LIKELY_HUNG:
        return "⚠️";
      case LivenessStatus.DEGRADED:
        return "🔴";
      default:
        return "❓";
    }
  };

  const getRecoveryUrgencyColor = (urgency: string) => {
    switch (urgency) {
      case RecoveryUrgency.LOW:
        return "urgency-low";
      case RecoveryUrgency.MEDIUM:
        return "urgency-medium";
      case RecoveryUrgency.HIGH:
        return "urgency-high";
      case RecoveryUrgency.CRITICAL:
        return "urgency-critical";
      default:
        return "";
    }
  };

  if (loading) {
    return <div className="loading">Loading workers...</div>;
  }

  const activeWorkers = workers.filter((w) => w.status !== WorkerStatus.OFFLINE);
  const offlineWorkers = workers.filter((w) => w.status === WorkerStatus.OFFLINE);

  // For keyboard selection, we need flat index mapping
  const getWorkerIndex = (worker: WorkerWithTask) => workers.findIndex(w => w.id === worker.id);

  // Check if there are any active workers to pause
  const hasActiveWorkers = activeWorkers.length > 0;

  return (
    <div className="workers-page">
      <div className="page-header">
        <h1>Workers</h1>
        <div className="header-actions">
          {hasActiveWorkers && (
            <button
              onClick={handlePauseAll}
              disabled={pauseAllLoading}
              className="pause-all-btn"
            >
              {pauseAllLoading ? "Pausing..." : "Pause All"}
            </button>
          )}
          <button onClick={handleOpenCreate}>
            + New Worker
          </button>
        </div>
      </div>

      {error && <div className="error">{error}</div>}

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
                            {workerHealth[worker.id] && (
                              <div className="worker-health-status">
                                <span className={`health-badge ${getLivenessColor(workerHealth[worker.id].liveness_status)}`}>
                                  {getLivenessIcon(workerHealth[worker.id].liveness_status)} {workerHealth[worker.id].liveness_status}
                                </span>
                                {workerHealth[worker.id].degradation.is_degraded && (
                                  <span className="degraded-badge" title={`Repetition: ${workerHealth[worker.id].degradation.repetition_score.toFixed(2)}, Apologies: ${workerHealth[worker.id].degradation.apology_count}, Retries: ${workerHealth[worker.id].degradation.retry_count}`}>
                                    Degraded
                                  </span>
                                )}
                                {workerHealth[worker.id].recommended_action.action !== "none" && (
                                  <span className={`recovery-badge ${getRecoveryUrgencyColor(workerHealth[worker.id].recommended_action.urgency)}`} title={workerHealth[worker.id].recommended_action.reason}>
                                    {workerHealth[worker.id].recommended_action.action.replace("_", " ")}
                                  </span>
                                )}
                                <span className="health-meta">
                                  {workerHealth[worker.id].total_output_lines} lines
                                </span>
                              </div>
                            )}
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
                        <button
                          onClick={() => handleOpenEdit(worker.id)}
                          className="edit-btn"
                          title="Edit worker configuration"
                        >
                          Edit
                        </button>
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
                          onClick={() => handleOpenEdit(worker.id)}
                          className="edit-btn"
                          title="Edit worker configuration"
                        >
                          Edit
                        </button>
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

      {/* Create/Edit Worker Modal */}
      {showWorkerModal && (
        <div className="modal-overlay" onClick={() => setShowWorkerModal(null)}>
          <div className="modal edit-modal" onClick={(e) => e.stopPropagation()}>
            <h2>{showWorkerModal === "new" ? "New Worker" : `Edit Worker: ${workers.find(w => w.id === showWorkerModal)?.name}`}</h2>
            <form onSubmit={handleWorkerSubmit}>
              <div className="form-wrapper">
                {/* AI Settings Generation Section */}
                <div className="form-group ai-section">
                  <label>Describe your worker (AI-powered)</label>
                  <textarea
                    placeholder="e.g., 'A Claude Code worker for Python development using my existing Claude Code Pro subscription' or 'A GitHub Copilot worker that uses my monthly plan'"
                    value={naturalLanguage}
                    onChange={(e) => setNaturalLanguage(e.target.value)}
                    rows={3}
                    className="ai-textarea"
                    autoFocus={showWorkerModal === "new"}
                  />
                  <button
                    type="button"
                    onClick={handleAIGenerate}
                    disabled={aiLoading || !naturalLanguage.trim()}
                    className="ai-generate-btn"
                  >
                    {aiLoading ? "Generating..." : "Generate Script from AI"}
                  </button>
                  <small>Describe the worker in plain English. Works with API keys, monthly plans (Claude Code Pro, Cursor, Copilot), or existing CLI auth.</small>
                </div>

                <div className="form-group">
                  <label>Name</label>
                  <input
                    type="text"
                    value={workerFormData.name || ""}
                    onChange={(e) => setWorkerFormData({ ...workerFormData, name: e.target.value })}
                    required
                  />
                </div>

                <div className="form-group">
                  <label>Description</label>
                  <textarea
                    placeholder="What does this worker do?"
                    value={workerFormData.description || ""}
                    onChange={(e) => setWorkerFormData({ ...workerFormData, description: e.target.value || undefined })}
                    rows={2}
                  />
                </div>

                <div className="form-group">
                  <label>Capabilities (comma-separated)</label>
                  <input
                    type="text"
                    placeholder="python, typescript, security"
                    value={workerFormData.capabilities?.join(", ") || ""}
                    onChange={(e) =>
                      setWorkerFormData({
                        ...workerFormData,
                        capabilities: e.target.value
                          .split(",")
                          .map((s) => s.trim())
                          .filter(Boolean),
                      })
                    }
                  />
                  <small>Used for task-worker matching (AI can infer this too)</small>
                </div>

                <div className="form-group">
                  <label>Generated Start Script</label>
                  <textarea
                    placeholder="#!/bin/bash&#10;# The AI-generated bash script will appear here&#10;# Or write your own complete worker script"
                    value={workerFormData.generated_script || ""}
                    onChange={(e) => setWorkerFormData({ ...workerFormData, generated_script: e.target.value || undefined })}
                    rows={12}
                    style={{ fontFamily: 'monospace', fontSize: '0.85rem' }}
                  />
                  <small>Complete bash script with shebang, signal handling, task polling, and AI tool execution</small>
                </div>
              </div>
              <div className="modal-actions">
                <button
                  type="button"
                  onClick={() => {
                    setShowWorkerModal(null);
                    setWorkerFormData({ name: "", type: "claude-code", capabilities: [] });
                    setNaturalLanguage("");
                  }}
                  className="secondary"
                >
                  Cancel
                </button>
                <button type="submit" className="primary">
                  {showWorkerModal === "new" ? "Create Worker" : "Save Changes"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Keyboard navigation hint */}
      {workers.length > 0 && !showWorkerModal && (
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
