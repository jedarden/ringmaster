import { useState } from "react";
import type { AnyTask, ValidationResponse, ValidationCheck, ValidationStatus } from "../types";
import { TaskStatus } from "../types";
import { validateTask, approveTask, rejectTask } from "../api/client";

interface ValidationPanelProps {
  /** Tasks in REVIEW status that can be validated/approved/rejected */
  tasks: AnyTask[];
  /** Called when a task's status changes after validation */
  onStatusChange?: (taskId: string, newStatus: string) => void;
  /** Optional working directory for running validation commands */
  workingDir?: string;
}

/**
 * Panel for validating, approving, or rejecting tasks in REVIEW status.
 * Shows validation check results and provides approve/reject actions.
 */
export function ValidationPanel({
  tasks,
  onStatusChange,
  workingDir,
}: ValidationPanelProps) {
  const reviewTasks = tasks.filter((t) => t.status === TaskStatus.REVIEW);

  if (reviewTasks.length === 0) {
    return (
      <div className="validation-panel">
        <div className="validation-header">
          <h3>Review Queue</h3>
          <span className="validation-count">0 tasks</span>
        </div>
        <div className="validation-empty">No tasks pending review</div>
      </div>
    );
  }

  return (
    <div className="validation-panel">
      <div className="validation-header">
        <h3>Review Queue</h3>
        <span className="validation-count">{reviewTasks.length} task(s)</span>
      </div>
      <div className="validation-list">
        {reviewTasks.map((task) => (
          <ValidationCard
            key={task.id}
            task={task}
            workingDir={workingDir}
            onStatusChange={onStatusChange}
          />
        ))}
      </div>
    </div>
  );
}

interface ValidationCardProps {
  task: AnyTask;
  workingDir?: string;
  onStatusChange?: (taskId: string, newStatus: string) => void;
}

function ValidationCard({ task, workingDir, onStatusChange }: ValidationCardProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [validationResult, setValidationResult] = useState<ValidationResponse | null>(null);
  const [showRejectForm, setShowRejectForm] = useState(false);
  const [rejectReason, setRejectReason] = useState("");

  const handleValidate = async () => {
    try {
      setLoading(true);
      setError(null);
      const result = await validateTask(task.id, workingDir);
      setValidationResult(result);
      onStatusChange?.(task.id, result.new_status);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Validation failed");
    } finally {
      setLoading(false);
    }
  };

  const handleApprove = async () => {
    try {
      setLoading(true);
      setError(null);
      const result = await approveTask(task.id);
      onStatusChange?.(task.id, result.status);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Approval failed");
    } finally {
      setLoading(false);
    }
  };

  const handleReject = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setLoading(true);
      setError(null);
      const result = await rejectTask(task.id, rejectReason || undefined);
      onStatusChange?.(task.id, result.status);
      setShowRejectForm(false);
      setRejectReason("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Rejection failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="validation-card">
      <div className="validation-task-info">
        <span className="validation-task-title">{task.title}</span>
        <span className="validation-task-id">{task.id}</span>
      </div>

      {task.description && (
        <div className="validation-task-description">
          {task.description.slice(0, 200)}
          {task.description.length > 200 && "..."}
        </div>
      )}

      {error && <div className="validation-error">{error}</div>}

      {validationResult && (
        <ValidationResultDisplay result={validationResult} />
      )}

      {!validationResult && !showRejectForm && (
        <div className="validation-actions">
          <button
            className="btn-validate"
            onClick={handleValidate}
            disabled={loading}
          >
            {loading ? "Running..." : "Run Validation"}
          </button>
          <button
            className="btn-approve"
            onClick={handleApprove}
            disabled={loading}
          >
            Approve
          </button>
          <button
            className="btn-reject"
            onClick={() => setShowRejectForm(true)}
            disabled={loading}
          >
            Reject
          </button>
        </div>
      )}

      {showRejectForm && (
        <form className="validation-reject-form" onSubmit={handleReject}>
          <textarea
            value={rejectReason}
            onChange={(e) => setRejectReason(e.target.value)}
            placeholder="Reason for rejection (optional)..."
            rows={2}
            disabled={loading}
          />
          <div className="reject-form-actions">
            <button type="submit" className="btn-reject" disabled={loading}>
              {loading ? "Rejecting..." : "Confirm Reject"}
            </button>
            <button
              type="button"
              className="btn-cancel"
              onClick={() => {
                setShowRejectForm(false);
                setRejectReason("");
              }}
              disabled={loading}
            >
              Cancel
            </button>
          </div>
        </form>
      )}

      {validationResult && !validationResult.overall_passed && (
        <div className="validation-actions validation-retry">
          <button
            className="btn-validate"
            onClick={handleValidate}
            disabled={loading}
          >
            Re-run Validation
          </button>
          <button
            className="btn-approve"
            onClick={handleApprove}
            disabled={loading}
          >
            Approve Anyway
          </button>
        </div>
      )}
    </div>
  );
}

interface ValidationResultDisplayProps {
  result: ValidationResponse;
}

function ValidationResultDisplay({ result }: ValidationResultDisplayProps) {
  return (
    <div
      className={`validation-result ${
        result.overall_passed ? "passed" : result.needs_human_review ? "review" : "failed"
      }`}
    >
      <div className="validation-result-header">
        <span
          className={`validation-status-icon ${
            result.overall_passed ? "pass" : result.needs_human_review ? "review" : "fail"
          }`}
        >
          {result.overall_passed ? "\u2713" : result.needs_human_review ? "!" : "\u2717"}
        </span>
        <span className="validation-result-summary">{result.summary}</span>
      </div>

      {result.needs_human_review && result.review_reason && (
        <div className="validation-review-reason">
          <strong>Review Required:</strong> {result.review_reason}
        </div>
      )}

      {result.checks.length > 0 && (
        <div className="validation-checks">
          {result.checks.map((check, index) => (
            <ValidationCheckRow key={index} check={check} />
          ))}
        </div>
      )}

      <div className="validation-new-status">
        Status: <span className={`status-badge ${result.new_status}`}>{result.new_status}</span>
      </div>
    </div>
  );
}

interface ValidationCheckRowProps {
  check: ValidationCheck;
}

function ValidationCheckRow({ check }: ValidationCheckRowProps) {
  const statusIcon = getStatusIcon(check.status);
  const statusClass = check.status.toLowerCase();

  return (
    <div className={`validation-check ${statusClass}`}>
      <span className="check-icon">{statusIcon}</span>
      <span className="check-name">{check.name}</span>
      <span className="check-status">{check.status}</span>
      {check.duration_seconds > 0 && (
        <span className="check-duration">{check.duration_seconds.toFixed(1)}s</span>
      )}
      {check.message && <span className="check-message">{check.message}</span>}
    </div>
  );
}

function getStatusIcon(status: ValidationStatus): string {
  switch (status) {
    case "passed":
      return "\u2713";
    case "failed":
      return "\u2717";
    case "skipped":
      return "-";
    case "error":
      return "!";
    default:
      return "?";
  }
}
