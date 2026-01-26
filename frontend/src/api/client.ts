import type {
  Project,
  ProjectCreate,
  ProjectUpdate,
  AnyTask,
  Task,
  Epic,
  TaskCreate,
  EpicCreate,
  TaskUpdate,
  Dependency,
  DependencyCreate,
  Worker,
  WorkerCreate,
  WorkerUpdate,
  QueueStats,
  EnqueueRequest,
  CompleteRequest,
  RecalculateRequest,
  TaskStatus,
  TaskType,
  WorkerStatus,
} from "../types";

// Use relative path in dev mode (Vite proxy), absolute URL in production
const API_BASE = import.meta.env.VITE_API_URL || "/api";

class ApiError extends Error {
  status: number;
  statusText: string;
  detail?: string;

  constructor(status: number, statusText: string, detail?: string) {
    super(detail || `${status} ${statusText}`);
    this.name = "ApiError";
    this.status = status;
    this.statusText = statusText;
    this.detail = detail;
  }
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail: string | undefined;
    try {
      const body = await response.json();
      detail = body.detail;
    } catch {
      // Ignore JSON parsing errors
    }
    throw new ApiError(response.status, response.statusText, detail);
  }

  // Handle 204 No Content
  if (response.status === 204) {
    return undefined as T;
  }

  return response.json();
}

// Projects API

export async function listProjects(
  limit = 100,
  offset = 0
): Promise<Project[]> {
  const params = new URLSearchParams({
    limit: limit.toString(),
    offset: offset.toString(),
  });
  const response = await fetch(`${API_BASE}/projects?${params}`);
  return handleResponse<Project[]>(response);
}

export async function createProject(data: ProjectCreate): Promise<Project> {
  const response = await fetch(`${API_BASE}/projects`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return handleResponse<Project>(response);
}

export async function getProject(id: string): Promise<Project> {
  const response = await fetch(`${API_BASE}/projects/${id}`);
  return handleResponse<Project>(response);
}

export async function updateProject(
  id: string,
  data: ProjectUpdate
): Promise<Project> {
  const response = await fetch(`${API_BASE}/projects/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return handleResponse<Project>(response);
}

export async function deleteProject(id: string): Promise<void> {
  const response = await fetch(`${API_BASE}/projects/${id}`, {
    method: "DELETE",
  });
  return handleResponse<void>(response);
}

// Tasks API

export interface ListTasksParams {
  project_id?: string;
  parent_id?: string;
  status?: TaskStatus;
  task_type?: TaskType;
  limit?: number;
  offset?: number;
}

export async function listTasks(params: ListTasksParams = {}): Promise<AnyTask[]> {
  const searchParams = new URLSearchParams();
  if (params.project_id) searchParams.set("project_id", params.project_id);
  if (params.parent_id) searchParams.set("parent_id", params.parent_id);
  if (params.status) searchParams.set("status", params.status);
  if (params.task_type) searchParams.set("task_type", params.task_type);
  searchParams.set("limit", (params.limit || 100).toString());
  searchParams.set("offset", (params.offset || 0).toString());

  const response = await fetch(`${API_BASE}/tasks?${searchParams}`);
  return handleResponse<AnyTask[]>(response);
}

export async function createTask(data: TaskCreate): Promise<Task> {
  const response = await fetch(`${API_BASE}/tasks`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return handleResponse<Task>(response);
}

export async function createEpic(data: EpicCreate): Promise<Epic> {
  const response = await fetch(`${API_BASE}/tasks/epics`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return handleResponse<Epic>(response);
}

export async function getTask(id: string): Promise<AnyTask> {
  const response = await fetch(`${API_BASE}/tasks/${id}`);
  return handleResponse<AnyTask>(response);
}

export async function updateTask(id: string, data: TaskUpdate): Promise<AnyTask> {
  const response = await fetch(`${API_BASE}/tasks/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return handleResponse<AnyTask>(response);
}

export async function deleteTask(id: string): Promise<void> {
  const response = await fetch(`${API_BASE}/tasks/${id}`, {
    method: "DELETE",
  });
  return handleResponse<void>(response);
}

export async function getTaskDependencies(taskId: string): Promise<Dependency[]> {
  const response = await fetch(`${API_BASE}/tasks/${taskId}/dependencies`);
  return handleResponse<Dependency[]>(response);
}

export async function addTaskDependency(
  taskId: string,
  data: DependencyCreate
): Promise<Dependency> {
  const response = await fetch(`${API_BASE}/tasks/${taskId}/dependencies`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return handleResponse<Dependency>(response);
}

export async function getTaskDependents(taskId: string): Promise<Dependency[]> {
  const response = await fetch(`${API_BASE}/tasks/${taskId}/dependents`);
  return handleResponse<Dependency[]>(response);
}

// Workers API

export interface ListWorkersParams {
  status?: WorkerStatus;
  worker_type?: string;
  limit?: number;
  offset?: number;
}

export async function listWorkers(
  params: ListWorkersParams = {}
): Promise<Worker[]> {
  const searchParams = new URLSearchParams();
  if (params.status) searchParams.set("status", params.status);
  if (params.worker_type) searchParams.set("worker_type", params.worker_type);
  searchParams.set("limit", (params.limit || 100).toString());
  searchParams.set("offset", (params.offset || 0).toString());

  const response = await fetch(`${API_BASE}/workers?${searchParams}`);
  return handleResponse<Worker[]>(response);
}

export async function createWorker(data: WorkerCreate): Promise<Worker> {
  const response = await fetch(`${API_BASE}/workers`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return handleResponse<Worker>(response);
}

export async function getWorker(id: string): Promise<Worker> {
  const response = await fetch(`${API_BASE}/workers/${id}`);
  return handleResponse<Worker>(response);
}

export async function updateWorker(id: string, data: WorkerUpdate): Promise<Worker> {
  const response = await fetch(`${API_BASE}/workers/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return handleResponse<Worker>(response);
}

export async function deleteWorker(id: string): Promise<void> {
  const response = await fetch(`${API_BASE}/workers/${id}`, {
    method: "DELETE",
  });
  return handleResponse<void>(response);
}

export async function activateWorker(id: string): Promise<Worker> {
  const response = await fetch(`${API_BASE}/workers/${id}/activate`, {
    method: "POST",
  });
  return handleResponse<Worker>(response);
}

export async function deactivateWorker(id: string): Promise<Worker> {
  const response = await fetch(`${API_BASE}/workers/${id}/deactivate`, {
    method: "POST",
  });
  return handleResponse<Worker>(response);
}

// Queue API

export async function getQueueStats(): Promise<QueueStats> {
  const response = await fetch(`${API_BASE}/queue/stats`);
  return handleResponse<QueueStats>(response);
}

export async function getReadyTasks(projectId?: string): Promise<Task[]> {
  const params = projectId ? `?project_id=${projectId}` : "";
  const response = await fetch(`${API_BASE}/queue/ready${params}`);
  return handleResponse<Task[]>(response);
}

export async function enqueueTask(data: EnqueueRequest): Promise<{ status: string; task_id: string }> {
  const response = await fetch(`${API_BASE}/queue/enqueue`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return handleResponse<{ status: string; task_id: string }>(response);
}

export async function completeTask(
  data: CompleteRequest
): Promise<{ status: string; task_id: string }> {
  const response = await fetch(`${API_BASE}/queue/complete`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return handleResponse<{ status: string; task_id: string }>(response);
}

export async function recalculatePriorities(
  data: RecalculateRequest
): Promise<{ status: string; tasks_updated: number }> {
  const response = await fetch(`${API_BASE}/queue/recalculate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return handleResponse<{ status: string; tasks_updated: number }>(response);
}

// Health Check

export async function healthCheck(): Promise<{ status: string }> {
  const response = await fetch(`${API_BASE}/health`);
  return handleResponse<{ status: string }>(response);
}

// WebSocket for real-time events

export function connectWebSocket(
  projectId?: string,
  onMessage?: (event: MessageEvent) => void,
  onError?: (event: Event) => void,
  onClose?: (event: CloseEvent) => void
): WebSocket {
  const wsBase = API_BASE.replace(/^http/, "ws").replace(/\/api$/, "");
  const params = projectId ? `?project_id=${projectId}` : "";
  const ws = new WebSocket(`${wsBase}/ws${params}`);

  if (onMessage) ws.addEventListener("message", onMessage);
  if (onError) ws.addEventListener("error", onError);
  if (onClose) ws.addEventListener("close", onClose);

  return ws;
}

export { ApiError };
