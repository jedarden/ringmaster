// Domain types matching backend models

export const Priority = {
  P0: "P0",
  P1: "P1",
  P2: "P2",
  P3: "P3",
  P4: "P4",
} as const;
export type Priority = (typeof Priority)[keyof typeof Priority];

export const TaskStatus = {
  DRAFT: "draft",
  READY: "ready",
  ASSIGNED: "assigned",
  IN_PROGRESS: "in_progress",
  BLOCKED: "blocked",
  REVIEW: "review",
  DONE: "done",
  FAILED: "failed",
} as const;
export type TaskStatus = (typeof TaskStatus)[keyof typeof TaskStatus];

export const TaskType = {
  EPIC: "epic",
  TASK: "task",
  SUBTASK: "subtask",
  DECISION: "decision",
  QUESTION: "question",
} as const;
export type TaskType = (typeof TaskType)[keyof typeof TaskType];

export const WorkerStatus = {
  IDLE: "idle",
  BUSY: "busy",
  OFFLINE: "offline",
} as const;
export type WorkerStatus = (typeof WorkerStatus)[keyof typeof WorkerStatus];

export interface Project {
  id: string;
  name: string;
  description: string | null;
  tech_stack: string[];
  repo_url: string | null;
  settings: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface ProjectCreate {
  name: string;
  description?: string | null;
  tech_stack?: string[];
  repo_url?: string | null;
}

export interface ProjectUpdate {
  name?: string | null;
  description?: string | null;
  tech_stack?: string[] | null;
  repo_url?: string | null;
}

export interface TaskBase {
  id: string;
  project_id: string;
  title: string;
  description: string | null;
  priority: Priority;
  status: TaskStatus;
  created_at: string;
  updated_at: string;
  prompt_path: string | null;
  output_path: string | null;
  context_hash: string | null;
}

export interface Epic extends TaskBase {
  type: typeof TaskType.EPIC;
  acceptance_criteria: string[];
  context: string | null;
  child_ids: string[];
}

export interface Task extends TaskBase {
  type: typeof TaskType.TASK;
  parent_id: string | null;
  worker_id: string | null;
  attempts: number;
  max_attempts: number;
  started_at: string | null;
  completed_at: string | null;
  pagerank_score: number;
  betweenness_score: number;
  on_critical_path: boolean;
  combined_priority: number;
  subtask_ids: string[];
}

export interface Subtask extends TaskBase {
  type: typeof TaskType.SUBTASK;
  parent_id: string;
  worker_id: string | null;
  attempts: number;
  max_attempts: number;
}

export type AnyTask = Epic | Task | Subtask;

export interface TaskCreate {
  project_id: string;
  title: string;
  description?: string | null;
  priority?: Priority;
  parent_id?: string | null;
  task_type?: TaskType;
}

export interface EpicCreate {
  project_id: string;
  title: string;
  description?: string | null;
  priority?: Priority;
  acceptance_criteria?: string[];
}

export interface TaskUpdate {
  title?: string | null;
  description?: string | null;
  priority?: Priority | null;
  status?: TaskStatus | null;
}

export interface Dependency {
  child_id: string;
  parent_id: string;
  created_at: string;
}

export interface DependencyCreate {
  parent_id: string;
}

export interface Worker {
  id: string;
  name: string;
  type: string;
  status: WorkerStatus;
  current_task_id: string | null;
  command: string;
  args: string[];
  prompt_flag: string;
  working_dir: string | null;
  timeout_seconds: number;
  env_vars: Record<string, string>;
  tasks_completed: number;
  tasks_failed: number;
  avg_completion_seconds: number | null;
  created_at: string;
  last_active_at: string | null;
}

export interface WorkerCreate {
  name: string;
  type: string;
  command: string;
  args?: string[];
  prompt_flag?: string;
  working_dir?: string | null;
  timeout_seconds?: number;
  env_vars?: Record<string, string>;
}

export interface WorkerUpdate {
  name?: string | null;
  status?: WorkerStatus | null;
  command?: string | null;
  args?: string[] | null;
  prompt_flag?: string | null;
  working_dir?: string | null;
  timeout_seconds?: number | null;
  env_vars?: Record<string, string> | null;
}

export interface QueueStats {
  total_tasks: number;
  ready_tasks: number;
  in_progress_tasks: number;
  blocked_tasks: number;
  completed_tasks: number;
  failed_tasks: number;
  total_workers: number;
  idle_workers: number;
  busy_workers: number;
}

export interface EnqueueRequest {
  task_id: string;
}

export interface CompleteRequest {
  task_id: string;
  success?: boolean;
  output_path?: string | null;
}

export interface RecalculateRequest {
  project_id: string;
}

// Chat types

export interface ChatMessage {
  id: number | null;
  project_id: string;
  task_id: string | null;
  role: "user" | "assistant" | "system";
  content: string;
  media_type: string | null;
  media_path: string | null;
  token_count: number | null;
  created_at: string;
}

export interface MessageCreate {
  project_id: string;
  task_id?: string | null;
  role: "user" | "assistant" | "system";
  content: string;
  media_type?: string | null;
  media_path?: string | null;
  token_count?: number | null;
}

export interface Summary {
  id: number | null;
  project_id: string;
  task_id: string | null;
  message_range_start: number;
  message_range_end: number;
  summary: string;
  key_decisions: string[];
  token_count: number | null;
  created_at: string;
}

export interface HistoryContextRequest {
  task_id?: string | null;
  recent_verbatim?: number;
  summary_threshold?: number;
  chunk_size?: number;
  max_context_tokens?: number;
}

export interface HistoryContextResponse {
  recent_messages: ChatMessage[];
  summaries: Summary[];
  key_decisions: string[];
  total_messages: number;
  estimated_tokens: number;
  formatted_prompt: string;
}

// File browser types

export interface FileEntry {
  name: string;
  path: string;
  is_dir: boolean;
  size: number | null;
  modified_at: number | null;
}

export interface DirectoryListing {
  path: string;
  entries: FileEntry[];
  parent_path: string | null;
}

export interface FileContent {
  path: string;
  content: string;
  size: number;
  mime_type: string | null;
  is_binary: boolean;
}

// Metrics types

export interface TaskStats {
  total: number;
  draft: number;
  ready: number;
  assigned: number;
  in_progress: number;
  blocked: number;
  review: number;
  done: number;
  failed: number;
}

export interface WorkerMetrics {
  total: number;
  idle: number;
  busy: number;
  offline: number;
  total_completed: number;
  total_failed: number;
}

export interface RecentEvent {
  id: number;
  event_type: string;
  entity_type: string;
  entity_id: string;
  data: Record<string, unknown> | null;
  created_at: string;
}

export interface ActivitySummary {
  tasks_completed: number;
  tasks_failed: number;
  tasks_created: number;
}

export interface MetricsResponse {
  timestamp: string;
  task_stats: TaskStats;
  worker_stats: WorkerMetrics;
  recent_events: RecentEvent[];
  activity_24h: ActivitySummary;
  activity_7d: ActivitySummary;
}
