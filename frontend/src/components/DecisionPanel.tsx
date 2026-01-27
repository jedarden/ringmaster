import { useState, useEffect, useCallback } from "react";
import type { Decision, DecisionStats } from "../types";
import { listDecisions, resolveDecision, getDecisionStats } from "../api/client";

interface DecisionPanelProps {
  projectId: string;
  taskId?: string;
  onDecisionResolved?: (decision: Decision) => void;
}

/**
 * Panel for displaying and resolving human-in-the-loop decisions.
 * Decisions block task progress until resolved.
 */
export function DecisionPanel({
  projectId,
  taskId,
  onDecisionResolved,
}: DecisionPanelProps) {
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [stats, setStats] = useState<DecisionStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [resolvingId, setResolvingId] = useState<string | null>(null);

  const fetchDecisions = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const [decisionsData, statsData] = await Promise.all([
        listDecisions({
          project_id: projectId,
          blocks_id: taskId,
          pending_only: true,
        }),
        getDecisionStats(projectId),
      ]);
      setDecisions(decisionsData);
      setStats(statsData);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load decisions");
    } finally {
      setLoading(false);
    }
  }, [projectId, taskId]);

  useEffect(() => {
    fetchDecisions();
  }, [fetchDecisions]);

  const handleResolve = async (decisionId: string, resolution: string) => {
    try {
      setResolvingId(decisionId);
      const resolved = await resolveDecision(decisionId, { resolution });
      setDecisions((prev) => prev.filter((d) => d.id !== decisionId));
      if (stats) {
        setStats({
          ...stats,
          pending: stats.pending - 1,
          resolved: stats.resolved + 1,
        });
      }
      onDecisionResolved?.(resolved);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to resolve decision");
    } finally {
      setResolvingId(null);
    }
  };

  if (loading) {
    return <div className="decision-panel loading">Loading decisions...</div>;
  }

  if (error) {
    return (
      <div className="decision-panel error">
        <span>{error}</span>
        <button onClick={fetchDecisions}>Retry</button>
      </div>
    );
  }

  return (
    <div className="decision-panel">
      <div className="decision-header">
        <h3>Decisions Needed</h3>
        {stats && (
          <span className="decision-stats">
            {stats.pending} pending / {stats.total} total
          </span>
        )}
      </div>

      {decisions.length === 0 ? (
        <div className="decision-empty">
          No pending decisions
        </div>
      ) : (
        <div className="decision-list">
          {decisions.map((decision) => (
            <DecisionCard
              key={decision.id}
              decision={decision}
              isResolving={resolvingId === decision.id}
              onResolve={(resolution) => handleResolve(decision.id, resolution)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

interface DecisionCardProps {
  decision: Decision;
  isResolving: boolean;
  onResolve: (resolution: string) => void;
}

function DecisionCard({ decision, isResolving, onResolve }: DecisionCardProps) {
  const [customAnswer, setCustomAnswer] = useState("");
  const [showCustomInput, setShowCustomInput] = useState(false);

  const handleOptionClick = (option: string) => {
    if (!isResolving) {
      onResolve(option);
    }
  };

  const handleCustomSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (customAnswer.trim() && !isResolving) {
      onResolve(customAnswer.trim());
    }
  };

  const timeAgo = formatTimeAgo(decision.created_at);

  return (
    <div className="decision-card">
      <div className="decision-question">
        <span className="decision-icon">?</span>
        <span className="decision-text">{decision.question}</span>
      </div>

      {decision.context && (
        <div className="decision-context">{decision.context}</div>
      )}

      <div className="decision-meta">
        <span className="decision-time">{timeAgo}</span>
        <span className="decision-task">Task: {decision.blocks_id}</span>
      </div>

      {decision.options.length > 0 ? (
        <div className="decision-options">
          {decision.options.map((option, index) => (
            <button
              key={index}
              className={`decision-option ${
                decision.recommendation === option ? "recommended" : ""
              }`}
              onClick={() => handleOptionClick(option)}
              disabled={isResolving}
            >
              {option}
              {decision.recommendation === option && (
                <span className="recommended-badge">Recommended</span>
              )}
            </button>
          ))}
          <button
            className="decision-option other"
            onClick={() => setShowCustomInput(true)}
            disabled={isResolving}
          >
            Other...
          </button>
        </div>
      ) : (
        <div className="decision-input">
          <form onSubmit={handleCustomSubmit}>
            <input
              type="text"
              value={customAnswer}
              onChange={(e) => setCustomAnswer(e.target.value)}
              placeholder="Enter your answer..."
              disabled={isResolving}
            />
            <button type="submit" disabled={isResolving || !customAnswer.trim()}>
              {isResolving ? "Resolving..." : "Submit"}
            </button>
          </form>
        </div>
      )}

      {showCustomInput && decision.options.length > 0 && (
        <div className="decision-custom-input">
          <form onSubmit={handleCustomSubmit}>
            <input
              type="text"
              value={customAnswer}
              onChange={(e) => setCustomAnswer(e.target.value)}
              placeholder="Enter custom answer..."
              disabled={isResolving}
              autoFocus
            />
            <div className="custom-input-actions">
              <button type="submit" disabled={isResolving || !customAnswer.trim()}>
                Submit
              </button>
              <button
                type="button"
                className="cancel"
                onClick={() => {
                  setShowCustomInput(false);
                  setCustomAnswer("");
                }}
              >
                Cancel
              </button>
            </div>
          </form>
        </div>
      )}

      {isResolving && (
        <div className="decision-resolving">
          Resolving...
        </div>
      )}
    </div>
  );
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
