import { useEffect, useState, useCallback, useRef } from "react";
import { Link, useNavigate } from "react-router-dom";
import { listProjectsWithSummaries, createProject, deleteProject, pinProject, unpinProject } from "../api/client";
import type { ProjectCreate, ProjectSummary } from "../types";
import { useWebSocket, type WebSocketEvent } from "../hooks/useWebSocket";
import { useListNavigation } from "../hooks/useKeyboardShortcuts";

// Helper to format time ago
function formatTimeAgo(dateString: string | null): string {
  if (!dateString) return "No activity";

  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffMins < 1) return "Just now";
  if (diffMins < 60) return `${diffMins} min ago`;
  if (diffHours < 24) return `${diffHours} hr ago`;
  if (diffDays === 1) return "Yesterday";
  return `${diffDays} days ago`;
}

// Determine project status for indicator
function getProjectStatus(
  summary: ProjectSummary
): "needs_attention" | "in_progress" | "complete" | "idle" {
  const { task_counts, pending_decisions, active_workers, total_tasks } = summary;

  // Needs attention: has pending decisions, blocked tasks, or failed tasks
  if (pending_decisions > 0 || task_counts.blocked > 0 || task_counts.failed > 0) {
    return "needs_attention";
  }

  // In progress: has active workers or tasks in progress
  if (active_workers > 0 || task_counts.in_progress > 0 || task_counts.assigned > 0) {
    return "in_progress";
  }

  // Complete: has tasks and all are done
  if (total_tasks > 0 && task_counts.done === total_tasks) {
    return "complete";
  }

  // Idle: no activity
  return "idle";
}

// Get status indicator emoji and color class
function getStatusIndicator(status: ReturnType<typeof getProjectStatus>): {
  emoji: string;
  className: string;
  label: string;
} {
  switch (status) {
    case "needs_attention":
      return { emoji: "", className: "status-attention", label: "Needs attention" };
    case "in_progress":
      return { emoji: "", className: "status-progress", label: "In progress" };
    case "complete":
      return { emoji: "", className: "status-complete", label: "Complete" };
    case "idle":
      return { emoji: "", className: "status-idle", label: "Idle" };
  }
}

export function ProjectsPage() {
  const navigate = useNavigate();
  const [summaries, setSummaries] = useState<ProjectSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [newProject, setNewProject] = useState<ProjectCreate>({ name: "", tech_stack: [] });
  const [techStackInput, setTechStackInput] = useState("");
  const listRef = useRef<HTMLDivElement>(null);

  const loadProjects = useCallback(async () => {
    try {
      setLoading(true);
      const data = await listProjectsWithSummaries();
      setSummaries(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load projects");
    } finally {
      setLoading(false);
    }
  }, []);

  // Handle WebSocket events for real-time updates
  const handleEvent = useCallback(
    (event: WebSocketEvent) => {
      if (
        event.type.startsWith("project.") ||
        event.type.startsWith("task.") ||
        event.type.startsWith("worker.") ||
        event.type.startsWith("decision.")
      ) {
        loadProjects();
      }
    },
    [loadProjects]
  );

  useWebSocket({ onEvent: handleEvent });

  useEffect(() => {
    loadProjects();
  }, [loadProjects]);

  // Keyboard navigation for project list
  const { selectedIndex, setSelectedIndex } = useListNavigation({
    items: summaries,
    enabled: !showCreateForm,
    onSelect: (_summary, index) => {
      // Scroll selected item into view
      const items = listRef.current?.querySelectorAll(".project-card");
      if (items?.[index]) {
        items[index].scrollIntoView({ block: "nearest", behavior: "smooth" });
      }
    },
    onOpen: (summary) => {
      navigate(`/projects/${summary.project.id}`);
    },
  });

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newProject.name.trim()) return;

    try {
      await createProject(newProject);
      setNewProject({ name: "", tech_stack: [] });
      setTechStackInput("");
      setShowCreateForm(false);
      await loadProjects();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create project");
    }
  };

  const handleAddTechStack = () => {
    const tech = techStackInput.trim();
    if (tech && !(newProject.tech_stack || []).includes(tech)) {
      setNewProject({
        ...newProject,
        tech_stack: [...(newProject.tech_stack || []), tech],
      });
      setTechStackInput("");
    }
  };

  const handleRemoveTechStack = (tech: string) => {
    setNewProject({
      ...newProject,
      tech_stack: (newProject.tech_stack || []).filter((t) => t !== tech),
    });
  };

  const handleTechStackKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.preventDefault();
      handleAddTechStack();
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("Are you sure you want to delete this project?")) return;

    try {
      await deleteProject(id);
      await loadProjects();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete project");
    }
  };

  const handleTogglePin = async (id: string, currentlyPinned: boolean) => {
    try {
      if (currentlyPinned) {
        await unpinProject(id);
      } else {
        await pinProject(id);
      }
      await loadProjects();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to toggle pin");
    }
  };

  if (loading) {
    return <div className="loading">Loading projects...</div>;
  }

  return (
    <div className="projects-page">
      <div className="page-header">
        <h1>Projects</h1>
        <button onClick={() => setShowCreateForm(!showCreateForm)}>
          {showCreateForm ? "Cancel" : "+ New Project"}
        </button>
      </div>

      {error && <div className="error">{error}</div>}

      {showCreateForm && (
        <form onSubmit={handleCreate} className="create-form">
          <div className="form-group">
            <label htmlFor="project-name">Project Name *</label>
            <input
              id="project-name"
              type="text"
              placeholder="My Awesome Project"
              value={newProject.name}
              onChange={(e) => setNewProject({ ...newProject, name: e.target.value })}
              required
              autoFocus
            />
          </div>

          <div className="form-group">
            <label htmlFor="project-description">Description</label>
            <input
              id="project-description"
              type="text"
              placeholder="A brief description of the project"
              value={newProject.description || ""}
              onChange={(e) =>
                setNewProject({ ...newProject, description: e.target.value || null })
              }
            />
          </div>

          <div className="form-group">
            <label htmlFor="project-repo">Repository URL</label>
            <input
              id="project-repo"
              type="text"
              placeholder="https://github.com/org/repo or /path/to/local/repo"
              value={newProject.repo_url || ""}
              onChange={(e) =>
                setNewProject({ ...newProject, repo_url: e.target.value || null })
              }
            />
          </div>

          <div className="form-group">
            <label htmlFor="project-tech">Tech Stack</label>
            <div className="tech-stack-input-wrapper">
              <input
                id="project-tech"
                type="text"
                placeholder="Add technology (e.g., Python, React)"
                value={techStackInput}
                onChange={(e) => setTechStackInput(e.target.value)}
                onKeyDown={handleTechStackKeyDown}
              />
              <button
                type="button"
                onClick={handleAddTechStack}
                className="add-tech-btn"
                disabled={!techStackInput.trim()}
              >
                Add
              </button>
            </div>
            {(newProject.tech_stack || []).length > 0 && (
              <div className="tech-stack-tags">
                {(newProject.tech_stack || []).map((tech) => (
                  <span key={tech} className="tech-tag">
                    {tech}
                    <button
                      type="button"
                      className="remove-tech-btn"
                      onClick={() => handleRemoveTechStack(tech)}
                      aria-label={`Remove ${tech}`}
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>
            )}
          </div>

          <div className="form-actions">
            <button type="submit">Create Project</button>
            <button
              type="button"
              onClick={() => {
                setShowCreateForm(false);
                setNewProject({ name: "", tech_stack: [] });
                setTechStackInput("");
              }}
              className="cancel-btn"
            >
              Cancel
            </button>
          </div>
        </form>
      )}

      {summaries.length === 0 ? (
        <div className="empty-state">
          <p>No projects yet. Create one to get started!</p>
        </div>
      ) : (
        <div className="projects-list" ref={listRef}>
          {summaries.map((summary, index) => {
            const { project, task_counts, total_tasks, active_workers, pending_decisions, pending_questions, latest_activity } = summary;
            const status = getProjectStatus(summary);
            const { className: statusClass, label: statusLabel } = getStatusIndicator(status);
            const completedTasks = task_counts.done;
            const progressPercent = total_tasks > 0 ? Math.round((completedTasks / total_tasks) * 100) : 0;

            return (
              <div
                key={project.id}
                className={`project-card ${statusClass} ${index === selectedIndex ? "keyboard-selected" : ""}`}
                onClick={() => setSelectedIndex(index)}
              >
                <Link to={`/projects/${project.id}`} className="project-link">
                  <div className="project-card-header">
                    <div className="project-status-indicator" title={statusLabel}>
                      <span className={`status-dot ${statusClass}`} />
                    </div>
                    {project.pinned && <span className="pin-indicator" title="Pinned">&#128204;</span>}
                    <h3>{project.name}</h3>
                    <span className="time-ago">{formatTimeAgo(latest_activity)}</span>
                  </div>

                  <div className="project-card-body">
                    {/* Activity summary line */}
                    <div className="activity-summary">
                      {active_workers > 0 && (
                        <span className="activity-item workers">
                          <span className="icon">&#9889;</span>
                          {active_workers} agent{active_workers !== 1 ? "s" : ""} working
                        </span>
                      )}
                      {pending_decisions > 0 && (
                        <span className="activity-item decisions">
                          <span className="icon">&#10067;</span>
                          {pending_decisions} decision{pending_decisions !== 1 ? "s" : ""} needed
                        </span>
                      )}
                      {pending_questions > 0 && (
                        <span className="activity-item questions">
                          <span className="icon">&#128172;</span>
                          {pending_questions} question{pending_questions !== 1 ? "s" : ""}
                        </span>
                      )}
                      {active_workers === 0 && pending_decisions === 0 && pending_questions === 0 && total_tasks === 0 && (
                        <span className="activity-item idle">No activity yet</span>
                      )}
                    </div>

                    {/* Task progress */}
                    {total_tasks > 0 && (
                      <div className="task-progress">
                        <div className="progress-bar">
                          <div
                            className="progress-fill"
                            style={{ width: `${progressPercent}%` }}
                          />
                        </div>
                        <span className="progress-text">
                          {completedTasks}/{total_tasks} tasks ({progressPercent}%)
                        </span>
                      </div>
                    )}

                    {/* Description */}
                    {project.description && (
                      <p className="project-description">{project.description}</p>
                    )}

                    {/* Tech stack badges */}
                    {project.tech_stack.length > 0 && (
                      <div className="tech-stack">
                        {project.tech_stack.map((tech) => (
                          <span key={tech} className="tech-badge">
                            {tech}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </Link>
                <div className="project-card-actions">
                  <button
                    className={`pin-btn ${project.pinned ? "pinned" : ""}`}
                    onClick={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      handleTogglePin(project.id, project.pinned);
                    }}
                    title={project.pinned ? "Unpin project" : "Pin project to top"}
                  >
                    {project.pinned ? "Unpin" : "Pin"}
                  </button>
                  <button
                    className="delete-btn"
                    onClick={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      handleDelete(project.id);
                    }}
                  >
                    Delete
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Keyboard navigation hint */}
      {summaries.length > 0 && !showCreateForm && (
        <div
          style={{
            marginTop: "1rem",
            fontSize: "0.8rem",
            color: "var(--color-text-muted)",
          }}
        >
          Use{" "}
          <kbd
            style={{
              background: "var(--color-surface)",
              padding: "0.1rem 0.4rem",
              borderRadius: "3px",
            }}
          >
            j
          </kbd>
          /
          <kbd
            style={{
              background: "var(--color-surface)",
              padding: "0.1rem 0.4rem",
              borderRadius: "3px",
            }}
          >
            k
          </kbd>{" "}
          to navigate,{" "}
          <kbd
            style={{
              background: "var(--color-surface)",
              padding: "0.1rem 0.4rem",
              borderRadius: "3px",
            }}
          >
            Enter
          </kbd>{" "}
          to open
        </div>
      )}
    </div>
  );
}
