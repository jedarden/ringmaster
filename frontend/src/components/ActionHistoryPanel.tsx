import { useState, useEffect, useCallback } from "react";
import type { ActionResponse } from "../types";
import { getUndoHistory, performUndo, performRedo } from "../api/client";
import { useWebSocket, type WebSocketEvent } from "../hooks/useWebSocket";

interface ActionHistoryPanelProps {
  projectId?: string;
  isOpen: boolean;
  onClose: () => void;
  onActionUndone?: (action: ActionResponse) => void;
}

/**
 * Panel for displaying action history with undo/redo capabilities.
 * Matches the UX spec from docs/07-user-experience.md Reversibility section.
 */
export function ActionHistoryPanel({
  projectId,
  isOpen,
  onClose,
  onActionUndone,
}: ActionHistoryPanelProps) {
  const [actions, setActions] = useState<ActionResponse[]>([]);
  const [canUndo, setCanUndo] = useState(false);
  const [canRedo, setCanRedo] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [undoingId, setUndoingId] = useState<number | null>(null);
  const [redoing, setRedoing] = useState(false);

  const fetchHistory = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const history = await getUndoHistory({
        project_id: projectId,
        limit: 50,
        include_undone: true,
      });
      setActions(history.actions);
      setCanUndo(history.can_undo);
      setCanRedo(history.can_redo);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load history");
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  // Refresh on undo/redo events
  const handleEvent = useCallback(
    (event: WebSocketEvent) => {
      if (
        event.type === "undo.performed" ||
        event.type === "redo.performed" ||
        event.type.startsWith("task.") ||
        event.type.startsWith("worker.")
      ) {
        fetchHistory();
      }
    },
    [fetchHistory]
  );

  useWebSocket({ onEvent: handleEvent });

  useEffect(() => {
    if (isOpen) {
      fetchHistory();
    }
  }, [isOpen, fetchHistory]);

  const handleUndo = async (actionId?: number) => {
    try {
      setUndoingId(actionId || null);
      const response = await performUndo(projectId);
      if (response.success && response.action) {
        onActionUndone?.(response.action);
      }
      await fetchHistory();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Undo failed");
    } finally {
      setUndoingId(null);
    }
  };

  const handleRedo = async () => {
    try {
      setRedoing(true);
      await performRedo(projectId);
      await fetchHistory();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Redo failed");
    } finally {
      setRedoing(false);
    }
  };

  const handleUndoAll = async () => {
    if (!confirm("Undo all actions? This cannot be easily reversed.")) return;

    try {
      setLoading(true);
      // Undo actions one by one until none left
      let hasMore = true;
      while (hasMore) {
        const response = await performUndo(projectId);
        hasMore = response.success;
      }
      await fetchHistory();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Undo all failed");
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="action-history-overlay" onClick={onClose}>
      <div className="action-history-panel" onClick={(e) => e.stopPropagation()}>
        <div className="action-history-header">
          <h2>Recent Actions</h2>
          <div className="action-history-controls">
            {canRedo && (
              <button
                className="redo-btn"
                onClick={handleRedo}
                disabled={redoing}
                title="Redo last undone action (Cmd+Shift+Z)"
              >
                {redoing ? "..." : "Redo"}
              </button>
            )}
            {canUndo && (
              <button
                className="undo-all-btn"
                onClick={handleUndoAll}
                disabled={loading}
                title="Undo all actions"
              >
                Undo All
              </button>
            )}
            <button className="close-btn" onClick={onClose} title="Close">
              ×
            </button>
          </div>
        </div>

        {error && (
          <div className="action-history-error">
            <span>{error}</span>
            <button onClick={fetchHistory}>Retry</button>
          </div>
        )}

        {loading && actions.length === 0 ? (
          <div className="action-history-loading">Loading history...</div>
        ) : actions.length === 0 ? (
          <div className="action-history-empty">No recent actions</div>
        ) : (
          <div className="action-history-list">
            {actions.map((action) => (
              <ActionCard
                key={action.id}
                action={action}
                isUndoing={undoingId === action.id}
                canUndoThis={canUndo && !action.undone && action.id === actions.find((a) => !a.undone)?.id}
                onUndo={() => handleUndo(action.id)}
              />
            ))}
          </div>
        )}

        <div className="action-history-footer">
          <span className="keyboard-hint">
            <kbd>Cmd+Z</kbd> undo · <kbd>Cmd+Shift+Z</kbd> redo
          </span>
        </div>
      </div>
    </div>
  );
}

interface ActionCardProps {
  action: ActionResponse;
  isUndoing: boolean;
  canUndoThis: boolean;
  onUndo: () => void;
}

function ActionCard({ action, isUndoing, canUndoThis, onUndo }: ActionCardProps) {
  const timeAgo = formatTimeAgo(action.created_at);
  const icon = getActionIcon(action.action_type, action.entity_type);

  return (
    <div className={`action-card ${action.undone ? "undone" : ""}`}>
      <div className="action-icon">{icon}</div>
      <div className="action-content">
        <div className="action-description">{action.description}</div>
        <div className="action-meta">
          <span className="action-time">{timeAgo}</span>
          {action.actor_id && (
            <span className="action-actor">by {action.actor_id}</span>
          )}
        </div>
      </div>
      <div className="action-actions">
        {action.undone ? (
          <span className="undone-badge">Undone</span>
        ) : canUndoThis ? (
          <button
            className="undo-btn"
            onClick={onUndo}
            disabled={isUndoing}
            title="Undo this action"
          >
            {isUndoing ? "..." : "Undo"}
          </button>
        ) : null}
      </div>
    </div>
  );
}

function getActionIcon(actionType: string, entityType: string): string {
  // Entity-based icons
  if (entityType === "task") {
    if (actionType.includes("created")) return "+";
    if (actionType.includes("deleted")) return "−";
    if (actionType.includes("status")) return "→";
    return "✎";
  }
  if (entityType === "worker") {
    return "⚡";
  }
  if (entityType === "dependency") {
    return "↔";
  }
  if (entityType === "project") {
    return "📁";
  }
  return "•";
}

function formatTimeAgo(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffMins < 1) return "just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString();
}
