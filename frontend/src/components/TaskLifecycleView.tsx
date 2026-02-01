import { useCallback, useEffect, useState } from "react";
import type {
  TaskLifecycle,
  LifecycleStep,
  LifecycleStepName,
  StepStatus,
  DeploymentModel,
} from "../types";
import { getLifecycle, createLifecycle } from "../api/client";

interface TaskLifecycleViewProps {
  taskId: string;
  projectId: string;
  taskTitle?: string;
  deploymentModel?: DeploymentModel;
  onClose?: () => void;
}

const STEP_LABELS: Record<LifecycleStepName, string> = {
  created: "Created",
  assigned: "Assigned",
  prompt_built: "Prompt Built",
  executing: "Executing",
  changes_made: "Changes Made",
  committed: "Committed",
  pushed: "Pushed",
  pr_created: "PR Created",
  ci_running: "CI Running",
  ci_passed: "CI Passed",
  ci_failed: "CI Failed",
  merged: "Merged",
  reloading: "Reloading",
  health_check: "Health Check",
  deploying: "Deploying",
  deploy_success: "Deploy Success",
  deploy_failed: "Deploy Failed",
  rolled_back: "Rolled Back",
  done: "Done",
  failed: "Failed",
};

const STATUS_ICONS: Record<StepStatus, string> = {
  pending: "○",
  in_progress: "◐",
  completed: "●",
  failed: "✗",
  skipped: "⊘",
};

const MODEL_LABELS: Record<DeploymentModel, string> = {
  none: "Local",
  hot_reload: "Hot Reload",
  ci_cd: "CI/CD",
  gitops: "GitOps",
  manual: "Manual",
  webhook: "Webhook",
};

function formatTime(isoString: string | null): string {
  if (!isoString) return "";
  const date = new Date(isoString);
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function formatDuration(start: string | null, end: string | null): string {
  if (!start) return "";
  const startDate = new Date(start);
  const endDate = end ? new Date(end) : new Date();
  const diffMs = endDate.getTime() - startDate.getTime();

  if (diffMs < 1000) return "<1s";
  if (diffMs < 60000) return `${Math.round(diffMs / 1000)}s`;
  if (diffMs < 3600000) return `${Math.round(diffMs / 60000)}m`;
  return `${Math.round(diffMs / 3600000)}h`;
}

interface StepItemProps {
  step: LifecycleStep;
  isLast: boolean;
}

function StepItem({ step, isLast }: StepItemProps) {
  const [expanded, setExpanded] = useState(false);
  const hasMetadata = Object.keys(step.metadata).length > 0;
  const hasError = !!step.error;
  const isClickable = hasMetadata || hasError;

  return (
    <div className={`lifecycle-step lifecycle-step--${step.status}`}>
      <div className="lifecycle-step__connector">
        <span className={`lifecycle-step__icon lifecycle-step__icon--${step.status}`}>
          {STATUS_ICONS[step.status]}
        </span>
        {!isLast && <div className="lifecycle-step__line" />}
      </div>

      <div className="lifecycle-step__content">
        <div
          className={`lifecycle-step__header ${isClickable ? "lifecycle-step__header--clickable" : ""}`}
          onClick={() => isClickable && setExpanded(!expanded)}
        >
          <span className="lifecycle-step__name">
            {STEP_LABELS[step.name] || step.name}
          </span>
          <span className="lifecycle-step__time">
            {step.started_at && formatTime(step.started_at)}
            {step.started_at && step.completed_at && (
              <span className="lifecycle-step__duration">
                ({formatDuration(step.started_at, step.completed_at)})
              </span>
            )}
            {step.status === "in_progress" && step.started_at && (
              <span className="lifecycle-step__duration lifecycle-step__duration--active">
                ({formatDuration(step.started_at, null)}...)
              </span>
            )}
          </span>
          {isClickable && (
            <span className="lifecycle-step__expand">
              {expanded ? "▼" : "▶"}
            </span>
          )}
        </div>

        {expanded && (
          <div className="lifecycle-step__details">
            {hasError && (
              <div className="lifecycle-step__error">
                <strong>Error:</strong> {step.error}
              </div>
            )}
            {hasMetadata && (
              <div className="lifecycle-step__metadata">
                {Object.entries(step.metadata).map(([key, value]) => (
                  <div key={key} className="lifecycle-step__meta-item">
                    <span className="lifecycle-step__meta-key">{key}:</span>
                    <span className="lifecycle-step__meta-value">
                      {typeof value === "object" ? JSON.stringify(value) : String(value)}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export function TaskLifecycleView({
  taskId,
  projectId,
  taskTitle,
  deploymentModel = "none",
  onClose,
}: TaskLifecycleViewProps) {
  const [lifecycle, setLifecycle] = useState<TaskLifecycle | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadLifecycle = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await getLifecycle(taskId);
      setLifecycle(data);
    } catch (err) {
      // If not found, try to create one
      if (err instanceof Error && err.message.includes("404")) {
        try {
          const data = await createLifecycle(taskId, projectId, deploymentModel);
          setLifecycle(data);
        } catch (createErr) {
          setError(createErr instanceof Error ? createErr.message : "Failed to create lifecycle");
        }
      } else {
        setError(err instanceof Error ? err.message : "Failed to load lifecycle");
      }
    } finally {
      setLoading(false);
    }
  }, [taskId, projectId, deploymentModel]);

  useEffect(() => {
    loadLifecycle();
  }, [loadLifecycle]);

  // Auto-refresh when in progress
  useEffect(() => {
    if (!lifecycle || lifecycle.is_complete || lifecycle.has_failed) return;

    const interval = setInterval(loadLifecycle, 5000);
    return () => clearInterval(interval);
  }, [lifecycle, loadLifecycle]);

  if (loading) {
    return (
      <div className="lifecycle-view lifecycle-view--loading">
        <div className="lifecycle-view__spinner" />
        <span>Loading lifecycle...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="lifecycle-view lifecycle-view--error">
        <span className="lifecycle-view__error-icon">!</span>
        <span>{error}</span>
        <button onClick={loadLifecycle} className="lifecycle-view__retry">
          Retry
        </button>
      </div>
    );
  }

  if (!lifecycle) {
    return (
      <div className="lifecycle-view lifecycle-view--empty">
        <span>No lifecycle data available</span>
      </div>
    );
  }

  const progressPercent = Math.round(
    (lifecycle.steps.filter((s) => s.status === "completed" || s.status === "skipped").length /
      lifecycle.steps.length) *
      100
  );

  return (
    <div className="lifecycle-view">
      <div className="lifecycle-view__header">
        <div className="lifecycle-view__title">
          <h3>{taskTitle || `Task ${taskId}`}</h3>
          <span className={`lifecycle-view__model lifecycle-view__model--${lifecycle.deployment_model}`}>
            {MODEL_LABELS[lifecycle.deployment_model]}
          </span>
        </div>
        {onClose && (
          <button onClick={onClose} className="lifecycle-view__close">
            ×
          </button>
        )}
      </div>

      <div className="lifecycle-view__progress">
        <div className="lifecycle-view__progress-bar">
          <div
            className={`lifecycle-view__progress-fill ${lifecycle.has_failed ? "lifecycle-view__progress-fill--failed" : ""}`}
            style={{ width: `${progressPercent}%` }}
          />
        </div>
        <span className="lifecycle-view__progress-text">
          {lifecycle.is_complete
            ? "Complete"
            : lifecycle.has_failed
            ? "Failed"
            : `${progressPercent}%`}
        </span>
      </div>

      <div className="lifecycle-view__steps">
        {lifecycle.steps.map((step, index) => (
          <StepItem
            key={step.name}
            step={step}
            isLast={index === lifecycle.steps.length - 1}
          />
        ))}
      </div>

      <div className="lifecycle-view__footer">
        <span className="lifecycle-view__updated">
          Updated: {new Date(lifecycle.updated_at).toLocaleString()}
        </span>
        <button onClick={loadLifecycle} className="lifecycle-view__refresh">
          Refresh
        </button>
      </div>
    </div>
  );
}

export default TaskLifecycleView;
