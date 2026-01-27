import { useEffect, useState, useCallback, useRef } from "react";
import {
  listWorkers,
  createWorker,
  activateWorker,
  deactivateWorker,
  deleteWorker,
} from "../api/client";
import type { Worker, WorkerCreate } from "../types";
import { WorkerStatus } from "../types";
import { useWebSocket, type WebSocketEvent } from "../hooks/useWebSocket";
import { useListNavigation } from "../hooks/useKeyboardShortcuts";
import { WorkerOutputPanel } from "../components/WorkerOutputPanel";

export function WorkersPage() {
  const [workers, setWorkers] = useState<Worker[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [newWorker, setNewWorker] = useState<WorkerCreate>({
    name: "",
    type: "claude-code",
    command: "claude",
  });
  const [selectedWorkerForOutput, setSelectedWorkerForOutput] = useState<string | null>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const loadWorkers = useCallback(async () => {
    try {
      setLoading(true);
      const data = await listWorkers();
      setWorkers(data);
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
  const getWorkerIndex = (worker: Worker) => workers.findIndex(w => w.id === worker.id);

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
                        {worker.current_task_id && (
                          <p>Current task: {worker.current_task_id}</p>
                        )}
                        <p>
                          Stats: {worker.tasks_completed} completed / {worker.tasks_failed} failed
                        </p>
                      </div>
                      <div className="worker-actions">
                        {worker.status === WorkerStatus.IDLE ? (
                          <button onClick={() => handleDeactivate(worker.id)}>
                            Deactivate
                          </button>
                        ) : worker.status === WorkerStatus.BUSY ? (
                          <span className="busy-note">Working...</span>
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
    </div>
  );
}
