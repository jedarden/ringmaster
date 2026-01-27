import type {
  Project,
  ProjectCreate,
  ProjectUpdate,
  ProjectSummary,
  AnyTask,
  Task,
  Epic,
  TaskCreate,
  EpicCreate,
  TaskUpdate,
  TaskAssign,
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
  ChatMessage,
  MessageCreate,
  Summary,
  HistoryContextRequest,
  HistoryContextResponse,
  DirectoryListing,
  FileContent,
  MetricsResponse,
  TaskStats,
  WorkerMetrics,
  RecentEvent,
  ActivitySummary,
  UserInputRequest,
  UserInputResponse,
  SuggestRelatedRequest,
  SuggestRelatedResponse,
  FileUploadResponse,
  LogEntry,
  LogsResponse,
  LogStats,
  LogLevel,
  LogComponent,
  GraphData,
  BulkUpdateRequest,
  BulkDeleteRequest,
  BulkOperationResponse,
  ActionResponse,
  UndoResponse,
  HistoryResponse,
  Decision,
  DecisionCreate,
  DecisionResolve,
  DecisionStats,
  Question,
  QuestionCreate,
  QuestionAnswer,
  QuestionStats,
  FileHistoryResponse,
  FileDiffResponse,
  FileAtCommitResponse,
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

export async function getProjectSummary(id: string): Promise<ProjectSummary> {
  const response = await fetch(`${API_BASE}/projects/${id}/summary`);
  return handleResponse<ProjectSummary>(response);
}

export async function listProjectsWithSummaries(
  limit = 100,
  offset = 0
): Promise<ProjectSummary[]> {
  const params = new URLSearchParams({
    limit: limit.toString(),
    offset: offset.toString(),
  });
  const response = await fetch(`${API_BASE}/projects/with-summaries?${params}`);
  return handleResponse<ProjectSummary[]>(response);
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

export async function removeTaskDependency(
  taskId: string,
  parentId: string
): Promise<{ removed: boolean }> {
  const response = await fetch(
    `${API_BASE}/tasks/${taskId}/dependencies/${encodeURIComponent(parentId)}`,
    { method: "DELETE" }
  );
  return handleResponse<{ removed: boolean }>(response);
}

export async function assignTask(taskId: string, data: TaskAssign): Promise<AnyTask> {
  const response = await fetch(`${API_BASE}/tasks/${taskId}/assign`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return handleResponse<AnyTask>(response);
}

export async function bulkUpdateTasks(data: BulkUpdateRequest): Promise<BulkOperationResponse> {
  const response = await fetch(`${API_BASE}/tasks/bulk-update`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return handleResponse<BulkOperationResponse>(response);
}

export async function bulkDeleteTasks(data: BulkDeleteRequest): Promise<BulkOperationResponse> {
  const response = await fetch(`${API_BASE}/tasks/bulk-delete`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return handleResponse<BulkOperationResponse>(response);
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

export interface CancelResponse {
  success: boolean;
  message: string;
  task_id: string | null;
}

export interface InterruptResponse {
  success: boolean;
  message: string;
  worker_id: string;
}

export async function cancelWorkerTask(id: string): Promise<CancelResponse> {
  const response = await fetch(`${API_BASE}/workers/${id}/cancel`, {
    method: "POST",
  });
  return handleResponse<CancelResponse>(response);
}

export async function pauseWorker(id: string): Promise<InterruptResponse> {
  const response = await fetch(`${API_BASE}/workers/${id}/pause`, {
    method: "POST",
  });
  return handleResponse<InterruptResponse>(response);
}

// Worker Output API

import type { OutputResponse, OutputBufferStats } from "../types";

export async function getWorkerOutput(
  workerId: string,
  limit = 100,
  sinceLine = 0
): Promise<OutputResponse> {
  const params = new URLSearchParams({
    limit: limit.toString(),
    since_line: sinceLine.toString(),
  });
  const response = await fetch(`${API_BASE}/workers/${workerId}/output?${params}`);
  return handleResponse<OutputResponse>(response);
}

export async function getOutputBufferStats(): Promise<OutputBufferStats> {
  const response = await fetch(`${API_BASE}/workers/output/stats`);
  return handleResponse<OutputBufferStats>(response);
}

export function getWorkerOutputStreamUrl(workerId: string): string {
  // Returns the SSE stream URL for use with EventSource
  const baseUrl = import.meta.env.VITE_API_URL || "";
  return `${baseUrl}/api/workers/${workerId}/output/stream`;
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

// Chat API

export interface ListMessagesParams {
  task_id?: string | null;
  limit?: number;
  offset?: number;
  since_id?: number | null;
}

export async function listMessages(
  projectId: string,
  params: ListMessagesParams = {}
): Promise<ChatMessage[]> {
  const searchParams = new URLSearchParams();
  if (params.task_id) searchParams.set("task_id", params.task_id);
  searchParams.set("limit", (params.limit || 100).toString());
  searchParams.set("offset", (params.offset || 0).toString());
  if (params.since_id) searchParams.set("since_id", params.since_id.toString());

  const response = await fetch(`${API_BASE}/chat/projects/${projectId}/messages?${searchParams}`);
  return handleResponse<ChatMessage[]>(response);
}

export async function createMessage(
  projectId: string,
  data: MessageCreate
): Promise<ChatMessage> {
  const response = await fetch(`${API_BASE}/chat/projects/${projectId}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return handleResponse<ChatMessage>(response);
}

export async function getRecentMessages(
  projectId: string,
  count = 10,
  taskId?: string
): Promise<ChatMessage[]> {
  const params = new URLSearchParams({ count: count.toString() });
  if (taskId) params.set("task_id", taskId);

  const response = await fetch(`${API_BASE}/chat/projects/${projectId}/messages/recent?${params}`);
  return handleResponse<ChatMessage[]>(response);
}

export async function getMessageCount(
  projectId: string,
  taskId?: string
): Promise<{ count: number }> {
  const params = taskId ? `?task_id=${taskId}` : "";
  const response = await fetch(`${API_BASE}/chat/projects/${projectId}/messages/count${params}`);
  return handleResponse<{ count: number }>(response);
}

export async function listSummaries(
  projectId: string,
  taskId?: string
): Promise<Summary[]> {
  const params = taskId ? `?task_id=${taskId}` : "";
  const response = await fetch(`${API_BASE}/chat/projects/${projectId}/summaries${params}`);
  return handleResponse<Summary[]>(response);
}

export async function getLatestSummary(
  projectId: string,
  taskId?: string
): Promise<Summary> {
  const params = taskId ? `?task_id=${taskId}` : "";
  const response = await fetch(`${API_BASE}/chat/projects/${projectId}/summaries/latest${params}`);
  return handleResponse<Summary>(response);
}

export async function getHistoryContext(
  projectId: string,
  request?: HistoryContextRequest
): Promise<HistoryContextResponse> {
  const response = await fetch(`${API_BASE}/chat/projects/${projectId}/context`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request || {}),
  });
  return handleResponse<HistoryContextResponse>(response);
}

export async function clearSummaries(
  projectId: string,
  afterId = 0
): Promise<{ deleted: number }> {
  const params = new URLSearchParams({ after_id: afterId.toString() });
  const response = await fetch(`${API_BASE}/chat/projects/${projectId}/summaries?${params}`, {
    method: "DELETE",
  });
  return handleResponse<{ deleted: number }>(response);
}

// File Upload API

export async function uploadFile(
  projectId: string,
  file: File
): Promise<FileUploadResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${API_BASE}/chat/projects/${projectId}/upload`, {
    method: "POST",
    body: formData,
  });
  return handleResponse<FileUploadResponse>(response);
}

export async function getUploadedFileMetadata(
  projectId: string,
  filename: string
): Promise<FileUploadResponse> {
  const response = await fetch(`${API_BASE}/chat/projects/${projectId}/uploads/${encodeURIComponent(filename)}`);
  return handleResponse<FileUploadResponse>(response);
}

/**
 * Download an uploaded file.
 * Returns the file URL for direct download. Use this to trigger browser downloads.
 */
export function getDownloadUrl(projectId: string, filename: string): string {
  return `${API_BASE}/chat/projects/${projectId}/uploads/${encodeURIComponent(filename)}/download`;
}

/**
 * Download an uploaded file as a Blob.
 * Useful when you need to process the file content in JavaScript.
 */
export async function downloadFile(
  projectId: string,
  filename: string
): Promise<Blob> {
  const response = await fetch(getDownloadUrl(projectId, filename));
  if (!response.ok) {
    throw new ApiError(
      response.status,
      response.statusText,
      `Failed to download file: ${filename}`
    );
  }
  return response.blob();
}

/**
 * Trigger browser download for an uploaded file.
 * Opens the file in a new tab or triggers the download dialog.
 */
export function triggerDownload(projectId: string, filename: string): void {
  const url = getDownloadUrl(projectId, filename);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.target = "_blank";
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

// File Browser API

export async function listDirectory(
  projectId: string,
  path = ""
): Promise<DirectoryListing> {
  const params = new URLSearchParams();
  if (path) params.set("path", path);

  const response = await fetch(`${API_BASE}/projects/${projectId}/files?${params}`);
  return handleResponse<DirectoryListing>(response);
}

export async function getFileContent(
  projectId: string,
  path: string
): Promise<FileContent> {
  const params = new URLSearchParams({ path });
  const response = await fetch(`${API_BASE}/projects/${projectId}/files/content?${params}`);
  return handleResponse<FileContent>(response);
}

// Metrics API

export async function getMetrics(eventLimit = 20): Promise<MetricsResponse> {
  const params = new URLSearchParams({ event_limit: eventLimit.toString() });
  const response = await fetch(`${API_BASE}/metrics?${params}`);
  return handleResponse<MetricsResponse>(response);
}

export async function getTaskStats(): Promise<TaskStats> {
  const response = await fetch(`${API_BASE}/metrics/tasks`);
  return handleResponse<TaskStats>(response);
}

export async function getWorkerMetrics(): Promise<WorkerMetrics> {
  const response = await fetch(`${API_BASE}/metrics/workers`);
  return handleResponse<WorkerMetrics>(response);
}

export interface GetEventsParams {
  limit?: number;
  event_type?: string;
  entity_type?: string;
}

export async function getEvents(params: GetEventsParams = {}): Promise<RecentEvent[]> {
  const searchParams = new URLSearchParams();
  if (params.limit) searchParams.set("limit", params.limit.toString());
  if (params.event_type) searchParams.set("event_type", params.event_type);
  if (params.entity_type) searchParams.set("entity_type", params.entity_type);

  const response = await fetch(`${API_BASE}/metrics/events?${searchParams}`);
  return handleResponse<RecentEvent[]>(response);
}

export async function getActivity(hours = 24): Promise<ActivitySummary> {
  const params = new URLSearchParams({ hours: hours.toString() });
  const response = await fetch(`${API_BASE}/metrics/activity?${params}`);
  return handleResponse<ActivitySummary>(response);
}

// Input API (Bead Creator)

export async function submitInput(data: UserInputRequest): Promise<UserInputResponse> {
  const response = await fetch(`${API_BASE}/input`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return handleResponse<UserInputResponse>(response);
}

export async function suggestRelatedTasks(
  data: SuggestRelatedRequest
): Promise<SuggestRelatedResponse> {
  const response = await fetch(`${API_BASE}/input/suggest-related`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return handleResponse<SuggestRelatedResponse>(response);
}

// Logs API

export interface ListLogsParams {
  component?: LogComponent;
  level?: LogLevel;
  task_id?: string;
  worker_id?: string;
  project_id?: string;
  since?: string;
  search?: string;
  offset?: number;
  limit?: number;
}

export async function listLogs(params: ListLogsParams = {}): Promise<LogsResponse> {
  const searchParams = new URLSearchParams();
  if (params.component) searchParams.set("component", params.component);
  if (params.level) searchParams.set("level", params.level);
  if (params.task_id) searchParams.set("task_id", params.task_id);
  if (params.worker_id) searchParams.set("worker_id", params.worker_id);
  if (params.project_id) searchParams.set("project_id", params.project_id);
  if (params.since) searchParams.set("since", params.since);
  if (params.search) searchParams.set("search", params.search);
  searchParams.set("offset", (params.offset || 0).toString());
  searchParams.set("limit", (params.limit || 100).toString());

  const response = await fetch(`${API_BASE}/logs?${searchParams}`);
  return handleResponse<LogsResponse>(response);
}

export async function getRecentLogs(
  minutes = 60,
  limit = 100
): Promise<LogEntry[]> {
  const params = new URLSearchParams({
    minutes: minutes.toString(),
    limit: limit.toString(),
  });
  const response = await fetch(`${API_BASE}/logs/recent?${params}`);
  return handleResponse<LogEntry[]>(response);
}

export async function getLogsForTask(
  taskId: string,
  limit = 100
): Promise<LogEntry[]> {
  const params = new URLSearchParams({ limit: limit.toString() });
  const response = await fetch(`${API_BASE}/logs/for-task/${taskId}?${params}`);
  return handleResponse<LogEntry[]>(response);
}

export async function getLogsForWorker(
  workerId: string,
  limit = 100
): Promise<LogEntry[]> {
  const params = new URLSearchParams({ limit: limit.toString() });
  const response = await fetch(`${API_BASE}/logs/for-worker/${workerId}?${params}`);
  return handleResponse<LogEntry[]>(response);
}

export async function getLogComponents(): Promise<string[]> {
  const response = await fetch(`${API_BASE}/logs/components`);
  return handleResponse<string[]>(response);
}

export async function getLogLevels(): Promise<string[]> {
  const response = await fetch(`${API_BASE}/logs/levels`);
  return handleResponse<string[]>(response);
}

export async function getLogStats(hours = 24): Promise<LogStats> {
  const params = new URLSearchParams({ hours: hours.toString() });
  const response = await fetch(`${API_BASE}/logs/stats?${params}`);
  return handleResponse<LogStats>(response);
}

export async function clearOldLogs(days = 7): Promise<{ deleted: number; cutoff: string }> {
  const params = new URLSearchParams({ days: days.toString() });
  const response = await fetch(`${API_BASE}/logs?${params}`, {
    method: "DELETE",
  });
  return handleResponse<{ deleted: number; cutoff: string }>(response);
}

// Graph API

export interface GetGraphParams {
  include_done?: boolean;
  include_subtasks?: boolean;
}

export async function getGraph(
  projectId: string,
  params: GetGraphParams = {}
): Promise<GraphData> {
  const searchParams = new URLSearchParams({ project_id: projectId });
  if (params.include_done !== undefined) {
    searchParams.set("include_done", params.include_done.toString());
  }
  if (params.include_subtasks !== undefined) {
    searchParams.set("include_subtasks", params.include_subtasks.toString());
  }

  const response = await fetch(`${API_BASE}/graph?${searchParams}`);
  return handleResponse<GraphData>(response);
}

// Undo/Redo API

export interface GetHistoryParams {
  project_id?: string;
  limit?: number;
  include_undone?: boolean;
}

export async function getUndoHistory(params: GetHistoryParams = {}): Promise<HistoryResponse> {
  const searchParams = new URLSearchParams();
  if (params.project_id) searchParams.set("project_id", params.project_id);
  if (params.limit) searchParams.set("limit", params.limit.toString());
  if (params.include_undone !== undefined) {
    searchParams.set("include_undone", params.include_undone.toString());
  }

  const response = await fetch(`${API_BASE}/undo/history?${searchParams}`);
  return handleResponse<HistoryResponse>(response);
}

export async function getLastUndoableAction(
  projectId?: string
): Promise<ActionResponse | null> {
  const params = projectId ? `?project_id=${projectId}` : "";
  const response = await fetch(`${API_BASE}/undo/last${params}`);
  return handleResponse<ActionResponse | null>(response);
}

export async function performUndo(projectId?: string): Promise<UndoResponse> {
  const params = projectId ? `?project_id=${projectId}` : "";
  const response = await fetch(`${API_BASE}/undo${params}`, {
    method: "POST",
  });
  return handleResponse<UndoResponse>(response);
}

export async function performRedo(projectId?: string): Promise<UndoResponse> {
  const params = projectId ? `?project_id=${projectId}` : "";
  const response = await fetch(`${API_BASE}/undo/redo${params}`, {
    method: "POST",
  });
  return handleResponse<UndoResponse>(response);
}

// Decisions API

export interface ListDecisionsParams {
  project_id?: string;
  blocks_id?: string;
  pending_only?: boolean;
  limit?: number;
  offset?: number;
}

export async function listDecisions(
  params: ListDecisionsParams = {}
): Promise<Decision[]> {
  const searchParams = new URLSearchParams();
  if (params.project_id) searchParams.set("project_id", params.project_id);
  if (params.blocks_id) searchParams.set("blocks_id", params.blocks_id);
  if (params.pending_only !== undefined) {
    searchParams.set("pending_only", params.pending_only.toString());
  }
  searchParams.set("limit", (params.limit || 100).toString());
  searchParams.set("offset", (params.offset || 0).toString());

  const response = await fetch(`${API_BASE}/decisions?${searchParams}`);
  return handleResponse<Decision[]>(response);
}

export async function createDecision(data: DecisionCreate): Promise<Decision> {
  const response = await fetch(`${API_BASE}/decisions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return handleResponse<Decision>(response);
}

export async function getDecision(id: string): Promise<Decision> {
  const response = await fetch(`${API_BASE}/decisions/${id}`);
  return handleResponse<Decision>(response);
}

export async function resolveDecision(
  id: string,
  data: DecisionResolve
): Promise<Decision> {
  const response = await fetch(`${API_BASE}/decisions/${id}/resolve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return handleResponse<Decision>(response);
}

export async function getDecisionsForTask(
  taskId: string,
  pendingOnly = false
): Promise<Decision[]> {
  const params = new URLSearchParams({
    pending_only: pendingOnly.toString(),
  });
  const response = await fetch(
    `${API_BASE}/decisions/for-task/${taskId}?${params}`
  );
  return handleResponse<Decision[]>(response);
}

export async function getDecisionStats(projectId: string): Promise<DecisionStats> {
  const response = await fetch(
    `${API_BASE}/projects/${projectId}/decisions/stats`
  );
  return handleResponse<DecisionStats>(response);
}

// Questions API

export interface ListQuestionsParams {
  project_id?: string;
  related_id?: string;
  pending_only?: boolean;
  limit?: number;
  offset?: number;
}

export async function listQuestions(
  params: ListQuestionsParams = {}
): Promise<Question[]> {
  const searchParams = new URLSearchParams();
  if (params.project_id) searchParams.set("project_id", params.project_id);
  if (params.related_id) searchParams.set("related_id", params.related_id);
  if (params.pending_only !== undefined) {
    searchParams.set("pending_only", params.pending_only.toString());
  }
  searchParams.set("limit", (params.limit || 100).toString());
  searchParams.set("offset", (params.offset || 0).toString());

  const response = await fetch(`${API_BASE}/questions?${searchParams}`);
  return handleResponse<Question[]>(response);
}

export async function createQuestion(data: QuestionCreate): Promise<Question> {
  const response = await fetch(`${API_BASE}/questions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return handleResponse<Question>(response);
}

export async function getQuestion(id: string): Promise<Question> {
  const response = await fetch(`${API_BASE}/questions/${id}`);
  return handleResponse<Question>(response);
}

export async function answerQuestion(
  id: string,
  data: QuestionAnswer
): Promise<Question> {
  const response = await fetch(`${API_BASE}/questions/${id}/answer`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return handleResponse<Question>(response);
}

export async function getQuestionsForTask(
  taskId: string,
  pendingOnly = false
): Promise<Question[]> {
  const params = new URLSearchParams({
    pending_only: pendingOnly.toString(),
  });
  const response = await fetch(
    `${API_BASE}/questions/for-task/${taskId}?${params}`
  );
  return handleResponse<Question[]>(response);
}

export async function getQuestionStats(projectId: string): Promise<QuestionStats> {
  const response = await fetch(
    `${API_BASE}/projects/${projectId}/questions/stats`
  );
  return handleResponse<QuestionStats>(response);
}

// Git History & Diff API

export async function getFileHistory(
  projectId: string,
  path: string,
  maxCommits = 50
): Promise<FileHistoryResponse> {
  const params = new URLSearchParams({
    path,
    max_commits: maxCommits.toString(),
  });
  const response = await fetch(`${API_BASE}/projects/${projectId}/files/history?${params}`);
  return handleResponse<FileHistoryResponse>(response);
}

export async function getFileDiff(
  projectId: string,
  path: string,
  commit = "HEAD",
  against?: string
): Promise<FileDiffResponse> {
  const params = new URLSearchParams({
    path,
    commit,
  });
  if (against) {
    params.set("against", against);
  }
  const response = await fetch(`${API_BASE}/projects/${projectId}/files/diff?${params}`);
  return handleResponse<FileDiffResponse>(response);
}

export async function getFileAtCommit(
  projectId: string,
  path: string,
  commit: string
): Promise<FileAtCommitResponse> {
  const params = new URLSearchParams({
    path,
    commit,
  });
  const response = await fetch(`${API_BASE}/projects/${projectId}/files/at-commit?${params}`);
  return handleResponse<FileAtCommitResponse>(response);
}

export { ApiError };
