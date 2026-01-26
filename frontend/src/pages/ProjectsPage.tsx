import { useEffect, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import { listProjects, createProject, deleteProject } from "../api/client";
import type { Project, ProjectCreate } from "../types";
import { useWebSocket, type WebSocketEvent } from "../hooks/useWebSocket";

export function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [newProject, setNewProject] = useState<ProjectCreate>({ name: "" });

  const loadProjects = useCallback(async () => {
    try {
      setLoading(true);
      const data = await listProjects();
      setProjects(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load projects");
    } finally {
      setLoading(false);
    }
  }, []);

  // Handle WebSocket events for real-time updates
  const handleEvent = useCallback((event: WebSocketEvent) => {
    if (event.type.startsWith("project.")) {
      loadProjects();
    }
  }, [loadProjects]);

  useWebSocket({ onEvent: handleEvent });

  useEffect(() => {
    loadProjects();
  }, [loadProjects]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newProject.name.trim()) return;

    try {
      await createProject(newProject);
      setNewProject({ name: "" });
      setShowCreateForm(false);
      await loadProjects();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create project");
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
          <input
            type="text"
            placeholder="Project name"
            value={newProject.name}
            onChange={(e) => setNewProject({ ...newProject, name: e.target.value })}
            required
          />
          <input
            type="text"
            placeholder="Description (optional)"
            value={newProject.description || ""}
            onChange={(e) =>
              setNewProject({ ...newProject, description: e.target.value || null })
            }
          />
          <button type="submit">Create Project</button>
        </form>
      )}

      {projects.length === 0 ? (
        <div className="empty-state">
          <p>No projects yet. Create one to get started!</p>
        </div>
      ) : (
        <div className="projects-list">
          {projects.map((project) => (
            <div key={project.id} className="project-card">
              <Link to={`/projects/${project.id}`} className="project-link">
                <h3>{project.name}</h3>
                {project.description && <p>{project.description}</p>}
                {project.tech_stack.length > 0 && (
                  <div className="tech-stack">
                    {project.tech_stack.map((tech) => (
                      <span key={tech} className="tech-badge">
                        {tech}
                      </span>
                    ))}
                  </div>
                )}
              </Link>
              <button
                className="delete-btn"
                onClick={(e) => {
                  e.preventDefault();
                  handleDelete(project.id);
                }}
              >
                Delete
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
