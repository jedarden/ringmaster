import { useEffect, useState, useCallback } from "react";
import { useParams, Link } from "react-router-dom";
import { getProject, listTasks, createTask, createEpic, updateTask, deleteTask } from "../api/client";
import type { Project, AnyTask, TaskCreate, EpicCreate } from "../types";
import { TaskStatus, TaskType, Priority } from "../types";
import { useWebSocket, type WebSocketEvent } from "../hooks/useWebSocket";
import { ChatPanel } from "../components/ChatPanel";
import { FileBrowser } from "../components/FileBrowser";
import { TaskInput } from "../components/TaskInput";

export function ProjectDetailPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const [project, setProject] = useState<Project | null>(null);
  const [tasks, setTasks] = useState<AnyTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showTaskForm, setShowTaskForm] = useState(false);
  const [taskType, setTaskType] = useState<"task" | "epic">("task");
  const [newTask, setNewTask] = useState<TaskCreate | EpicCreate>({ project_id: "", title: "" });

  const loadData = useCallback(async () => {
    if (!projectId) return;

    try {
      setLoading(true);
      const [projectData, tasksData] = await Promise.all([
        getProject(projectId),
        listTasks({ project_id: projectId }),
      ]);
      setProject(projectData);
      setTasks(tasksData);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load data");
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  // Handle WebSocket events for real-time updates (filtered by project)
  const handleEvent = useCallback((event: WebSocketEvent) => {
    // Only refresh if event is for this project or project-related
    if (event.project_id === projectId || event.type.startsWith("project.")) {
      loadData();
    }
  }, [loadData, projectId]);

  useWebSocket({ projectId, onEvent: handleEvent });

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleCreateTask = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!projectId || !newTask.title.trim()) return;

    try {
      if (taskType === "epic") {
        await createEpic({ ...newTask, project_id: projectId } as EpicCreate);
      } else {
        await createTask({ ...newTask, project_id: projectId, task_type: TaskType.TASK });
      }
      setNewTask({ project_id: "", title: "" });
      setShowTaskForm(false);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create task");
    }
  };

  const handleStatusChange = async (taskId: string, status: TaskStatus) => {
    try {
      await updateTask(taskId, { status });
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update task");
    }
  };

  const handleDeleteTask = async (taskId: string) => {
    if (!confirm("Delete this task?")) return;

    try {
      await deleteTask(taskId);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete task");
    }
  };

  const handleTasksCreated = useCallback(() => {
    // Reload task list when new tasks are created via TaskInput
    loadData();
  }, [loadData]);

  if (loading) {
    return <div className="loading">Loading...</div>;
  }

  if (!project) {
    return <div className="error">Project not found</div>;
  }

  const epics = tasks.filter((t) => t.type === TaskType.EPIC);
  const regularTasks = tasks.filter((t) => t.type === TaskType.TASK);
  // Subtasks shown in future version under their parent tasks
  const _subtasks = tasks.filter((t) => t.type === TaskType.SUBTASK);
  void _subtasks; // suppress unused warning

  const groupedTasks = {
    [TaskStatus.READY]: regularTasks.filter((t) => t.status === TaskStatus.READY),
    [TaskStatus.IN_PROGRESS]: regularTasks.filter((t) => t.status === TaskStatus.IN_PROGRESS),
    [TaskStatus.REVIEW]: regularTasks.filter((t) => t.status === TaskStatus.REVIEW),
    [TaskStatus.DONE]: regularTasks.filter((t) => t.status === TaskStatus.DONE),
    [TaskStatus.BLOCKED]: regularTasks.filter((t) => t.status === TaskStatus.BLOCKED),
  };

  return (
    <div className="project-detail-page">
      <div className="page-header">
        <Link to="/" className="back-link">&larr; Back</Link>
        <h1>{project.name}</h1>
      </div>

      {project.description && <p className="description">{project.description}</p>}

      {error && <div className="error">{error}</div>}

      <div className="project-detail-with-chat">
        <div className="project-main-content">
          {projectId && (
            <TaskInput projectId={projectId} onTasksCreated={handleTasksCreated} />
          )}

          {projectId && <FileBrowser projectId={projectId} />}

          <div className="project-actions">
            <button onClick={() => { setShowTaskForm(!showTaskForm); setTaskType("task"); }}>
              + Manual Task
            </button>
            <button onClick={() => { setShowTaskForm(!showTaskForm); setTaskType("epic"); }}>
              + Manual Epic
            </button>
            <Link to={`/projects/${projectId}/graph`} className="btn-link">
              View Graph
            </Link>
          </div>

          {showTaskForm && (
            <form onSubmit={handleCreateTask} className="create-form">
              <h3>Create {taskType === "epic" ? "Epic" : "Task"}</h3>
              <input
                type="text"
                placeholder="Title"
                value={newTask.title}
                onChange={(e) => setNewTask({ ...newTask, title: e.target.value })}
                required
              />
              <textarea
                placeholder="Description (optional)"
                value={newTask.description || ""}
                onChange={(e) => setNewTask({ ...newTask, description: e.target.value || null })}
              />
              <select
                value={newTask.priority || Priority.P2}
                onChange={(e) => setNewTask({ ...newTask, priority: e.target.value as Priority })}
              >
                <option value={Priority.P0}>P0 - Critical</option>
                <option value={Priority.P1}>P1 - High</option>
                <option value={Priority.P2}>P2 - Medium</option>
                <option value={Priority.P3}>P3 - Low</option>
                <option value={Priority.P4}>P4 - Lowest</option>
              </select>
              <div className="form-actions">
                <button type="submit">Create</button>
                <button type="button" onClick={() => setShowTaskForm(false)}>Cancel</button>
              </div>
            </form>
          )}

          {epics.length > 0 && (
            <div className="section">
              <h2>Epics</h2>
              <div className="epics-list">
                {epics.map((epic) => (
                  <div key={epic.id} className="epic-card">
                    <div className="epic-header">
                      <span className={`priority priority-${epic.priority.toLowerCase()}`}>
                        {epic.priority}
                      </span>
                      <h3>{epic.title}</h3>
                      <span className={`status status-${epic.status}`}>{epic.status}</span>
                    </div>
                    {epic.description && <p>{epic.description}</p>}
                    <button onClick={() => handleDeleteTask(epic.id)} className="delete-btn">
                      Delete
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="section">
            <h2>Tasks</h2>
            <div className="kanban-board">
              {Object.entries(groupedTasks).map(([status, statusTasks]) => (
                <div key={status} className="kanban-column">
                  <h3 className="column-header">
                    {status.replace("_", " ")} ({statusTasks.length})
                  </h3>
                  <div className="column-tasks">
                    {statusTasks.map((task) => (
                      <div key={task.id} className="task-card">
                        <div className="task-header">
                          <span className={`priority priority-${task.priority.toLowerCase()}`}>
                            {task.priority}
                          </span>
                          <span className="task-id">{task.id}</span>
                        </div>
                        <h4>{task.title}</h4>
                        <div className="task-actions">
                          <select
                            value={task.status}
                            onChange={(e) => handleStatusChange(task.id, e.target.value as TaskStatus)}
                          >
                            {Object.values(TaskStatus).map((s) => (
                              <option key={s} value={s}>{s}</option>
                            ))}
                          </select>
                          <button onClick={() => handleDeleteTask(task.id)} className="delete-btn">
                            X
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="project-chat-sidebar">
          {projectId && <ChatPanel projectId={projectId} />}
        </div>
      </div>
    </div>
  );
}
