import { useEffect, useState, useCallback } from "react";
import { useParams, Link } from "react-router-dom";
import { getProject, listTasks, listWorkers, createTask, createEpic, updateTask, deleteTask, assignTask, bulkUpdateTasks, bulkDeleteTasks } from "../api/client";
import type { Project, AnyTask, Worker, TaskCreate, EpicCreate } from "../types";
import { TaskStatus, TaskType, Priority, WorkerStatus } from "../types";
import { useWebSocket, type WebSocketEvent } from "../hooks/useWebSocket";
import { ChatPanel } from "../components/ChatPanel";
import { FileBrowser } from "../components/FileBrowser";
import { TaskInput } from "../components/TaskInput";
import { DecisionPanel } from "../components/DecisionPanel";
import { QuestionPanel } from "../components/QuestionPanel";
import { ValidationPanel } from "../components/ValidationPanel";

export function ProjectDetailPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const [project, setProject] = useState<Project | null>(null);
  const [tasks, setTasks] = useState<AnyTask[]>([]);
  const [workers, setWorkers] = useState<Worker[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showTaskForm, setShowTaskForm] = useState(false);
  const [taskType, setTaskType] = useState<"task" | "epic">("task");
  const [newTask, setNewTask] = useState<TaskCreate | EpicCreate>({ project_id: "", title: "" });
  const [expandedTasks, setExpandedTasks] = useState<Set<string>>(new Set());
  const [selectedTasks, setSelectedTasks] = useState<Set<string>>(new Set());
  const [bulkLoading, setBulkLoading] = useState(false);

  const loadData = useCallback(async () => {
    if (!projectId) return;

    try {
      setLoading(true);
      const [projectData, tasksData, workersData] = await Promise.all([
        getProject(projectId),
        listTasks({ project_id: projectId }),
        listWorkers(),
      ]);
      setProject(projectData);
      setTasks(tasksData);
      setWorkers(workersData);
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

  const handleAssign = async (taskId: string, workerId: string | null) => {
    try {
      await assignTask(taskId, { worker_id: workerId || null });
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to assign task");
    }
  };

  const handleTasksCreated = useCallback(() => {
    // Reload task list when new tasks are created via TaskInput
    loadData();
  }, [loadData]);

  const toggleExpanded = (taskId: string) => {
    setExpandedTasks((prev) => {
      const next = new Set(prev);
      if (next.has(taskId)) {
        next.delete(taskId);
      } else {
        next.add(taskId);
      }
      return next;
    });
  };

  const toggleTaskSelection = (taskId: string) => {
    setSelectedTasks((prev) => {
      const next = new Set(prev);
      if (next.has(taskId)) {
        next.delete(taskId);
      } else {
        next.add(taskId);
      }
      return next;
    });
  };

  const selectAllTasks = () => {
    const allTaskIds = tasks
      .filter((t) => t.type !== TaskType.EPIC)
      .map((t) => t.id);
    setSelectedTasks(new Set(allTaskIds));
  };

  const deselectAllTasks = () => {
    setSelectedTasks(new Set());
  };

  const handleBulkStatusChange = async (status: TaskStatus) => {
    if (selectedTasks.size === 0) return;

    try {
      setBulkLoading(true);
      const result = await bulkUpdateTasks({
        task_ids: Array.from(selectedTasks),
        status,
      });
      if (result.errors.length > 0) {
        setError(`Updated ${result.updated}, failed ${result.failed}: ${result.errors[0]}`);
      }
      await loadData();
      setSelectedTasks(new Set());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Bulk update failed");
    } finally {
      setBulkLoading(false);
    }
  };

  const handleBulkPriorityChange = async (priority: Priority) => {
    if (selectedTasks.size === 0) return;

    try {
      setBulkLoading(true);
      const result = await bulkUpdateTasks({
        task_ids: Array.from(selectedTasks),
        priority,
      });
      if (result.errors.length > 0) {
        setError(`Updated ${result.updated}, failed ${result.failed}: ${result.errors[0]}`);
      }
      await loadData();
      setSelectedTasks(new Set());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Bulk update failed");
    } finally {
      setBulkLoading(false);
    }
  };

  const handleBulkAssign = async (workerId: string | null) => {
    if (selectedTasks.size === 0) return;

    try {
      setBulkLoading(true);
      const result = await bulkUpdateTasks({
        task_ids: Array.from(selectedTasks),
        worker_id: workerId || undefined,
        unassign: !workerId,
      });
      if (result.errors.length > 0) {
        setError(`Updated ${result.updated}, failed ${result.failed}: ${result.errors[0]}`);
      }
      await loadData();
      setSelectedTasks(new Set());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Bulk assign failed");
    } finally {
      setBulkLoading(false);
    }
  };

  const handleBulkDelete = async () => {
    if (selectedTasks.size === 0) return;
    if (!confirm(`Delete ${selectedTasks.size} selected tasks?`)) return;

    try {
      setBulkLoading(true);
      const result = await bulkDeleteTasks({
        task_ids: Array.from(selectedTasks),
      });
      if (result.errors.length > 0) {
        setError(`Deleted ${result.updated}, failed ${result.failed}: ${result.errors[0]}`);
      }
      await loadData();
      setSelectedTasks(new Set());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Bulk delete failed");
    } finally {
      setBulkLoading(false);
    }
  };

  if (loading) {
    return <div className="loading">Loading...</div>;
  }

  if (!project) {
    return <div className="error">Project not found</div>;
  }

  const epics = tasks.filter((t) => t.type === TaskType.EPIC);
  const allTasks = tasks.filter((t) => t.type === TaskType.TASK);
  const subtasks = tasks.filter((t) => t.type === TaskType.SUBTASK);

  // Group tasks by parent epic ID
  const tasksByEpic = new Map<string, typeof allTasks>();
  for (const task of allTasks) {
    if ("parent_id" in task && task.parent_id) {
      const epicId = task.parent_id;
      if (!tasksByEpic.has(epicId)) {
        tasksByEpic.set(epicId, []);
      }
      tasksByEpic.get(epicId)!.push(task);
    }
  }

  // Tasks not belonging to any epic (shown in kanban board)
  const regularTasks = allTasks.filter((t) => !("parent_id" in t && t.parent_id));

  // Group subtasks by parent task ID for nested display
  const subtasksByParent = new Map<string, typeof subtasks>();
  for (const subtask of subtasks) {
    if (subtask.type === TaskType.SUBTASK) {
      const parentId = subtask.parent_id;
      if (!subtasksByParent.has(parentId)) {
        subtasksByParent.set(parentId, []);
      }
      subtasksByParent.get(parentId)!.push(subtask);
    }
  }

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
                {epics.map((epic) => {
                  const epicTasks = tasksByEpic.get(epic.id) || [];
                  const hasChildTasks = epicTasks.length > 0;
                  const isExpanded = expandedTasks.has(epic.id);
                  const doneCount = epicTasks.filter((t) => t.status === TaskStatus.DONE).length;
                  const progressPercent = hasChildTasks ? Math.round((doneCount / epicTasks.length) * 100) : 0;

                  return (
                    <div key={epic.id} className="epic-card">
                      <div className="epic-header">
                        <span className={`priority priority-${epic.priority.toLowerCase()}`}>
                          {epic.priority}
                        </span>
                        <h3>{epic.title}</h3>
                        <span className={`status status-${epic.status}`}>{epic.status}</span>
                      </div>
                      {epic.description && <p className="epic-description">{epic.description}</p>}
                      {hasChildTasks && (
                        <div className="epic-progress">
                          <div className="progress-bar">
                            <div
                              className="progress-fill"
                              style={{ width: `${progressPercent}%` }}
                            />
                          </div>
                          <span className="progress-text">
                            {doneCount}/{epicTasks.length} tasks ({progressPercent}%)
                          </span>
                        </div>
                      )}
                      <div className="epic-actions">
                        {hasChildTasks && (
                          <button
                            className="child-tasks-toggle"
                            onClick={() => toggleExpanded(epic.id)}
                          >
                            {isExpanded ? "▼" : "▶"} {epicTasks.length} task{epicTasks.length !== 1 ? "s" : ""}
                          </button>
                        )}
                        <button onClick={() => handleDeleteTask(epic.id)} className="delete-btn">
                          Delete
                        </button>
                      </div>
                      {hasChildTasks && isExpanded && (
                        <div className="epic-child-tasks">
                          {epicTasks.map((task) => {
                            const taskWorkerId = "worker_id" in task ? task.worker_id : null;
                            const availableWorkers = workers.filter(
                              (w) => w.status !== WorkerStatus.OFFLINE && (w.status === WorkerStatus.IDLE || w.current_task_id === task.id)
                            );
                            const taskSubtasks = subtasksByParent.get(task.id) || [];

                            // Get iteration info for child tasks
                            const childAttempts = "attempts" in task ? task.attempts : 0;
                            const childMaxAttempts = "max_attempts" in task ? task.max_attempts : 5;
                            const showChildIterations = task.status === TaskStatus.IN_PROGRESS && childMaxAttempts > 0;

                            return (
                              <div key={task.id} className={`epic-child-task status-${task.status}`}>
                                <div className="child-task-header">
                                  <span className={`priority priority-${task.priority.toLowerCase()}`}>
                                    {task.priority}
                                  </span>
                                  <span className={`status-badge status-${task.status}`}>
                                    {task.status.replace("_", " ")}
                                  </span>
                                  {showChildIterations && (
                                    <span className="task-iteration" title={`Attempt ${childAttempts + 1} of ${childMaxAttempts}`}>
                                      {childAttempts + 1}/{childMaxAttempts}
                                    </span>
                                  )}
                                  {taskSubtasks.length > 0 && (
                                    <span className="subtask-count" title="Number of subtasks">
                                      [{taskSubtasks.length}]
                                    </span>
                                  )}
                                </div>
                                <span className="child-task-title">{task.title}</span>
                                <div className="child-task-actions">
                                  <select
                                    value={task.status}
                                    onChange={(e) => handleStatusChange(task.id, e.target.value as TaskStatus)}
                                    className="child-task-status-select"
                                  >
                                    {Object.values(TaskStatus).map((s) => (
                                      <option key={s} value={s}>{s}</option>
                                    ))}
                                  </select>
                                  <select
                                    value={taskWorkerId || ""}
                                    onChange={(e) => handleAssign(task.id, e.target.value || null)}
                                    className="child-task-worker-select"
                                    title="Assign to worker"
                                  >
                                    <option value="">-</option>
                                    {availableWorkers.map((worker) => (
                                      <option key={worker.id} value={worker.id}>
                                        {worker.name}
                                      </option>
                                    ))}
                                  </select>
                                  <button
                                    onClick={() => handleDeleteTask(task.id)}
                                    className="child-task-delete-btn"
                                  >
                                    ×
                                  </button>
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          <div className="section">
            <div className="section-header">
              <h2>Tasks</h2>
              <div className="bulk-selection-controls">
                <button onClick={selectAllTasks} className="select-btn">
                  Select All
                </button>
                <button onClick={deselectAllTasks} className="select-btn" disabled={selectedTasks.size === 0}>
                  Deselect All
                </button>
              </div>
            </div>

            {selectedTasks.size > 0 && (
              <div className="bulk-toolbar">
                <span className="bulk-count">{selectedTasks.size} selected</span>
                <div className="bulk-actions">
                  <select
                    onChange={(e) => {
                      if (e.target.value) {
                        handleBulkStatusChange(e.target.value as TaskStatus);
                        e.target.value = "";
                      }
                    }}
                    disabled={bulkLoading}
                    defaultValue=""
                  >
                    <option value="" disabled>Set Status...</option>
                    {Object.values(TaskStatus).map((s) => (
                      <option key={s} value={s}>{s}</option>
                    ))}
                  </select>
                  <select
                    onChange={(e) => {
                      if (e.target.value) {
                        handleBulkPriorityChange(e.target.value as Priority);
                        e.target.value = "";
                      }
                    }}
                    disabled={bulkLoading}
                    defaultValue=""
                  >
                    <option value="" disabled>Set Priority...</option>
                    {Object.values(Priority).map((p) => (
                      <option key={p} value={p}>{p}</option>
                    ))}
                  </select>
                  <select
                    onChange={(e) => {
                      const val = e.target.value;
                      if (val === "__unassign__") {
                        handleBulkAssign(null);
                      } else if (val) {
                        handleBulkAssign(val);
                      }
                      e.target.value = "";
                    }}
                    disabled={bulkLoading}
                    defaultValue=""
                  >
                    <option value="" disabled>Assign to...</option>
                    <option value="__unassign__">Unassign All</option>
                    {workers.filter((w) => w.status === WorkerStatus.IDLE).map((w) => (
                      <option key={w.id} value={w.id}>{w.name}</option>
                    ))}
                  </select>
                  <button onClick={handleBulkDelete} className="delete-btn" disabled={bulkLoading}>
                    Delete Selected
                  </button>
                </div>
                {bulkLoading && <span className="bulk-loading">Updating...</span>}
              </div>
            )}

            <div className="kanban-board">
              {Object.entries(groupedTasks).map(([status, statusTasks]) => (
                <div key={status} className="kanban-column">
                  <h3 className="column-header">
                    {status.replace("_", " ")} ({statusTasks.length})
                  </h3>
                  <div className="column-tasks">
                    {statusTasks.map((task) => {
                      const taskWorkerId = "worker_id" in task ? task.worker_id : null;
                      const availableWorkers = workers.filter(
                        (w) => w.status !== WorkerStatus.OFFLINE && (w.status === WorkerStatus.IDLE || w.current_task_id === task.id)
                      );
                      const taskSubtasks = subtasksByParent.get(task.id) || [];
                      const hasSubtasks = taskSubtasks.length > 0;
                      const isExpanded = expandedTasks.has(task.id);

                      // Get iteration info for Task/Subtask types
                      const taskAttempts = "attempts" in task ? task.attempts : 0;
                      const taskMaxAttempts = "max_attempts" in task ? task.max_attempts : 5;
                      const showIterations = task.status === TaskStatus.IN_PROGRESS && taskMaxAttempts > 0;

                      return (
                        <div key={task.id} className={`task-card ${selectedTasks.has(task.id) ? "selected" : ""}`}>
                          <div className="task-header">
                            <input
                              type="checkbox"
                              checked={selectedTasks.has(task.id)}
                              onChange={() => toggleTaskSelection(task.id)}
                              className="task-checkbox"
                            />
                            <span className={`priority priority-${task.priority.toLowerCase()}`}>
                              {task.priority}
                            </span>
                            <span className="task-id">{task.id}</span>
                            {showIterations && (
                              <span className="task-iteration" title={`Attempt ${taskAttempts + 1} of ${taskMaxAttempts}`}>
                                {taskAttempts + 1}/{taskMaxAttempts}
                              </span>
                            )}
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
                            <select
                              value={taskWorkerId || ""}
                              onChange={(e) => handleAssign(task.id, e.target.value || null)}
                              className="worker-select"
                              title="Assign to worker"
                            >
                              <option value="">Unassigned</option>
                              {availableWorkers.map((worker) => (
                                <option key={worker.id} value={worker.id}>
                                  {worker.name} ({worker.type})
                                </option>
                              ))}
                            </select>
                            <button onClick={() => handleDeleteTask(task.id)} className="delete-btn">
                              X
                            </button>
                          </div>
                          {hasSubtasks && (
                            <div className="subtasks-section">
                              <button
                                className="subtasks-toggle"
                                onClick={() => toggleExpanded(task.id)}
                              >
                                {isExpanded ? "▼" : "▶"} {taskSubtasks.length} subtask{taskSubtasks.length !== 1 ? "s" : ""}
                              </button>
                              {isExpanded && (
                                <div className="subtasks-list">
                                  {taskSubtasks.map((subtask) => {
                                    const subtaskWorkerId = "worker_id" in subtask ? subtask.worker_id : null;
                                    // Get iteration info for subtasks
                                    const subtaskAttempts = "attempts" in subtask ? subtask.attempts : 0;
                                    const subtaskMaxAttempts = "max_attempts" in subtask ? subtask.max_attempts : 3;
                                    const showSubtaskIterations = subtask.status === TaskStatus.IN_PROGRESS && subtaskMaxAttempts > 0;

                                    return (
                                      <div key={subtask.id} className={`subtask-item status-${subtask.status}`}>
                                        <div className="subtask-header">
                                          <span className={`priority priority-${subtask.priority.toLowerCase()}`}>
                                            {subtask.priority}
                                          </span>
                                          <span className={`status-badge status-${subtask.status}`}>
                                            {subtask.status}
                                          </span>
                                          {showSubtaskIterations && (
                                            <span className="task-iteration" title={`Attempt ${subtaskAttempts + 1} of ${subtaskMaxAttempts}`}>
                                              {subtaskAttempts + 1}/{subtaskMaxAttempts}
                                            </span>
                                          )}
                                        </div>
                                        <span className="subtask-title">{subtask.title}</span>
                                        <div className="subtask-actions">
                                          <select
                                            value={subtask.status}
                                            onChange={(e) => handleStatusChange(subtask.id, e.target.value as TaskStatus)}
                                            className="subtask-status-select"
                                          >
                                            {Object.values(TaskStatus).map((s) => (
                                              <option key={s} value={s}>{s}</option>
                                            ))}
                                          </select>
                                          <select
                                            value={subtaskWorkerId || ""}
                                            onChange={(e) => handleAssign(subtask.id, e.target.value || null)}
                                            className="subtask-worker-select"
                                            title="Assign to worker"
                                          >
                                            <option value="">-</option>
                                            {workers.filter((w) => w.status !== WorkerStatus.OFFLINE).map((worker) => (
                                              <option key={worker.id} value={worker.id}>
                                                {worker.name}
                                              </option>
                                            ))}
                                          </select>
                                          <button
                                            onClick={() => handleDeleteTask(subtask.id)}
                                            className="subtask-delete-btn"
                                          >
                                            ×
                                          </button>
                                        </div>
                                      </div>
                                    );
                                  })}
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="project-chat-sidebar">
          {projectId && (
            <>
              <ValidationPanel
                tasks={tasks}
                workingDir={project?.repo_url || undefined}
                onStatusChange={() => loadData()}
              />
              <DecisionPanel
                projectId={projectId}
                onDecisionResolved={() => loadData()}
              />
              <QuestionPanel
                projectId={projectId}
                onQuestionAnswered={() => loadData()}
              />
              <ChatPanel projectId={projectId} />
            </>
          )}
        </div>
      </div>
    </div>
  );
}
