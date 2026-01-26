import { useState, useCallback, useEffect, useRef } from "react";
import { submitInput, suggestRelatedTasks } from "../api/client";
import type {
  Priority,
  UserInputResponse,
  RelatedTaskInfo,
  CreatedTaskInfo,
} from "../types";

interface TaskInputProps {
  projectId: string;
  onTasksCreated?: (response: UserInputResponse) => void;
}

const PRIORITIES: { value: Priority; label: string; color: string }[] = [
  { value: "P0", label: "P0 - Critical", color: "#dc2626" },
  { value: "P1", label: "P1 - High", color: "#ea580c" },
  { value: "P2", label: "P2 - Medium", color: "#ca8a04" },
  { value: "P3", label: "P3 - Low", color: "#16a34a" },
  { value: "P4", label: "P4 - Backlog", color: "#6b7280" },
];

export function TaskInput({ projectId, onTasksCreated }: TaskInputProps) {
  const [text, setText] = useState("");
  const [priority, setPriority] = useState<Priority>("P2");
  const [autoDecompose, setAutoDecompose] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<UserInputResponse | null>(null);
  const [relatedTasks, setRelatedTasks] = useState<RelatedTaskInfo[]>([]);
  const [loadingRelated, setLoadingRelated] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const textAreaRef = useRef<HTMLTextAreaElement>(null);
  const debounceTimerRef = useRef<number | null>(null);

  // Auto-resize textarea
  useEffect(() => {
    if (textAreaRef.current) {
      textAreaRef.current.style.height = "auto";
      textAreaRef.current.style.height = `${Math.min(textAreaRef.current.scrollHeight, 200)}px`;
    }
  }, [text]);

  // Debounced search for related tasks
  const searchRelated = useCallback(
    async (searchText: string) => {
      if (searchText.length < 10) {
        setRelatedTasks([]);
        return;
      }

      try {
        setLoadingRelated(true);
        const response = await suggestRelatedTasks({
          project_id: projectId,
          text: searchText,
          max_results: 5,
        });
        setRelatedTasks(response.related_tasks);
      } catch {
        // Silently ignore errors for related task search
        setRelatedTasks([]);
      } finally {
        setLoadingRelated(false);
      }
    },
    [projectId]
  );

  // Handle text change with debounced related search
  const handleTextChange = (value: string) => {
    setText(value);
    setResult(null);
    setError(null);

    // Debounce the related task search
    if (debounceTimerRef.current) {
      window.clearTimeout(debounceTimerRef.current);
    }
    debounceTimerRef.current = window.setTimeout(() => {
      searchRelated(value);
    }, 500);
  };

  // Cleanup timer on unmount
  useEffect(() => {
    return () => {
      if (debounceTimerRef.current) {
        window.clearTimeout(debounceTimerRef.current);
      }
    };
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!text.trim() || submitting) return;

    try {
      setSubmitting(true);
      setError(null);
      setResult(null);

      const response = await submitInput({
        project_id: projectId,
        text: text.trim(),
        priority,
        auto_decompose: autoDecompose,
      });

      setResult(response);
      if (response.success) {
        setText("");
        setRelatedTasks([]);
        onTasksCreated?.(response);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create tasks");
    } finally {
      setSubmitting(false);
    }
  };

  const getTaskTypeIcon = (taskType: string) => {
    switch (taskType) {
      case "epic":
        return "E";
      case "task":
        return "T";
      case "subtask":
        return "S";
      default:
        return "?";
    }
  };

  const formatSimilarity = (similarity: number) => {
    return `${Math.round(similarity * 100)}%`;
  };

  return (
    <div className="task-input">
      <div className="task-input-header">
        <h3>Create Tasks</h3>
        <button
          type="button"
          className="advanced-toggle"
          onClick={() => setShowAdvanced(!showAdvanced)}
        >
          {showAdvanced ? "Hide options" : "Options"}
        </button>
      </div>

      {error && <div className="task-input-error">{error}</div>}

      {result && result.success && (
        <div className="task-input-result">
          <div className="result-header">
            Created {result.created_tasks.length} task(s)
            {result.dependencies_count > 0 && (
              <span className="deps-count">
                {" "}
                with {result.dependencies_count} dependencies
              </span>
            )}
          </div>
          <div className="created-tasks-list">
            {result.created_tasks.map((task: CreatedTaskInfo) => (
              <div key={task.task_id} className="created-task-item">
                <span className={`task-type-badge task-type-${task.task_type}`}>
                  {getTaskTypeIcon(task.task_type)}
                </span>
                <span className="task-title">{task.title}</span>
                {task.was_updated && (
                  <span className="updated-badge">updated</span>
                )}
              </div>
            ))}
          </div>
          {result.messages.length > 0 && (
            <div className="result-messages">
              {result.messages.map((msg, i) => (
                <div key={i} className="result-message">
                  {msg}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      <form onSubmit={handleSubmit} className="task-input-form">
        <textarea
          ref={textAreaRef}
          value={text}
          onChange={(e) => handleTextChange(e.target.value)}
          placeholder="Describe what you want to accomplish...&#10;&#10;Examples:&#10;- Add user authentication with JWT&#10;- Fix the bug where login fails on mobile&#10;- First implement the API, then add tests, finally update docs"
          disabled={submitting}
          className="task-text-input"
          rows={3}
        />

        {showAdvanced && (
          <div className="task-input-options">
            <div className="option-group">
              <label htmlFor="priority-select">Priority</label>
              <select
                id="priority-select"
                value={priority}
                onChange={(e) => setPriority(e.target.value as Priority)}
                disabled={submitting}
                className="priority-select"
                style={{
                  borderColor: PRIORITIES.find((p) => p.value === priority)
                    ?.color,
                }}
              >
                {PRIORITIES.map((p) => (
                  <option key={p.value} value={p.value}>
                    {p.label}
                  </option>
                ))}
              </select>
            </div>

            <div className="option-group checkbox-group">
              <label>
                <input
                  type="checkbox"
                  checked={autoDecompose}
                  onChange={(e) => setAutoDecompose(e.target.checked)}
                  disabled={submitting}
                />
                Auto-decompose large tasks
              </label>
            </div>
          </div>
        )}

        {relatedTasks.length > 0 && (
          <div className="related-tasks">
            <div className="related-header">
              Related existing tasks{" "}
              {loadingRelated && <span className="loading-dot">...</span>}
            </div>
            <div className="related-list">
              {relatedTasks.map((task) => (
                <div key={task.task_id} className="related-task-item">
                  <span className="similarity-badge">
                    {formatSimilarity(task.similarity)}
                  </span>
                  <span className="related-title">{task.title}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="task-input-actions">
          <button
            type="submit"
            disabled={submitting || !text.trim()}
            className="submit-btn"
          >
            {submitting ? "Creating..." : "Create Tasks"}
          </button>
        </div>
      </form>
    </div>
  );
}
