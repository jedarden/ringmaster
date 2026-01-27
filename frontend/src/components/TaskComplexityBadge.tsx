import { useState, useEffect } from "react";
import { getTaskRouting } from "../api/client";
import type { RoutingRecommendation, TaskComplexity, ModelTier } from "../types";

interface TaskComplexityBadgeProps {
  taskId: string;
}

// Cache routing info to avoid repeated API calls
const routingCache = new Map<string, RoutingRecommendation>();

const complexityColors: Record<TaskComplexity, string> = {
  simple: "#22c55e",    // green
  moderate: "#f59e0b",  // yellow
  complex: "#ef4444",   // red
};

const complexityIcons: Record<TaskComplexity, string> = {
  simple: "○",    // single circle
  moderate: "◐",  // half circle
  complex: "●",   // filled circle
};

const tierDescriptions: Record<ModelTier, string> = {
  fast: "Fast model (Haiku-class)",
  balanced: "Balanced model (Sonnet-class)",
  powerful: "Powerful model (Opus-class)",
};

export function TaskComplexityBadge({ taskId }: TaskComplexityBadgeProps) {
  const [routing, setRouting] = useState<RoutingRecommendation | null>(null);
  const [loading, setLoading] = useState(false);
  const [showTooltip, setShowTooltip] = useState(false);

  const loadRouting = async () => {
    // Check cache first
    if (routingCache.has(taskId)) {
      setRouting(routingCache.get(taskId)!);
      return;
    }

    setLoading(true);
    try {
      const data = await getTaskRouting(taskId);
      routingCache.set(taskId, data);
      setRouting(data);
    } catch (err) {
      console.warn(`Failed to load routing for task ${taskId}:`, err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    // Load immediately (don't wait for hover)
    loadRouting();
  }, [taskId]);

  if (loading) {
    return (
      <span className="complexity-badge loading" title="Loading complexity...">
        ⋯
      </span>
    );
  }

  if (!routing) {
    return null;
  }

  const color = complexityColors[routing.complexity];
  const icon = complexityIcons[routing.complexity];
  const tierDesc = tierDescriptions[routing.tier];

  return (
    <span
      className={`complexity-badge complexity-${routing.complexity}`}
      style={{ color }}
      onMouseEnter={() => setShowTooltip(true)}
      onMouseLeave={() => setShowTooltip(false)}
      title={`${routing.complexity} task → ${tierDesc}`}
    >
      {icon}
      {showTooltip && (
        <div className="complexity-tooltip">
          <div className="tooltip-header">
            <strong>{routing.complexity.charAt(0).toUpperCase() + routing.complexity.slice(1)}</strong>
            <span className="tier-badge">{routing.tier}</span>
          </div>
          <div className="tooltip-reasoning">{routing.reasoning}</div>
          {routing.suggested_models.length > 0 && (
            <div className="tooltip-models">
              Suggested: {routing.suggested_models.join(", ")}
            </div>
          )}
          <div className="tooltip-signals">
            {routing.signals.is_epic && <span className="signal">Epic</span>}
            {routing.signals.is_subtask && <span className="signal">Subtask</span>}
            {routing.signals.is_critical && <span className="signal">Critical</span>}
            {routing.signals.dependency_count > 0 && (
              <span className="signal">{routing.signals.dependency_count} deps</span>
            )}
            {routing.signals.file_count > 0 && (
              <span className="signal">{routing.signals.file_count} files</span>
            )}
          </div>
        </div>
      )}
    </span>
  );
}

// CSS styles for the complexity badge
export const complexityBadgeStyles = `
.complexity-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: bold;
  margin-left: 4px;
  cursor: help;
  position: relative;
  min-width: 14px;
}

.complexity-badge.loading {
  color: #888;
}

.complexity-tooltip {
  position: absolute;
  top: 100%;
  left: 50%;
  transform: translateX(-50%);
  background: #1a1a2e;
  border: 1px solid #333;
  border-radius: 6px;
  padding: 8px 12px;
  min-width: 220px;
  z-index: 1000;
  font-size: 11px;
  font-weight: normal;
  color: #e0e0e0;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
  text-align: left;
  margin-top: 4px;
}

.complexity-tooltip .tooltip-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.complexity-tooltip .tier-badge {
  background: #333;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 10px;
  text-transform: uppercase;
}

.complexity-tooltip .tooltip-reasoning {
  color: #aaa;
  margin-bottom: 6px;
}

.complexity-tooltip .tooltip-models {
  color: #7aa2f7;
  font-size: 10px;
  margin-bottom: 6px;
}

.complexity-tooltip .tooltip-signals {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.complexity-tooltip .signal {
  background: #2a2a3e;
  padding: 2px 6px;
  border-radius: 3px;
  font-size: 10px;
}
`;
