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
  pinned: boolean;
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
  settings?: Record<string, string | number | boolean | null>;
}

// Project summary for mailbox view
export interface TaskStatusCounts {
  draft: number;
  ready: number;
  assigned: number;
  in_progress: number;
  blocked: number;
  review: number;
  done: number;
  failed: number;
}

export interface LatestMessage {
  content: string;
  role: string;
  created_at: string;
}

export interface ProjectSummary {
  project: Project;
  task_counts: TaskStatusCounts;
  total_tasks: number;
  active_workers: number;
  pending_decisions: number;
  pending_questions: number;
  latest_activity: string | null;
  latest_message: LatestMessage | null;
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

export interface TaskAssign {
  worker_id: string | null;
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

// Current task info for busy workers
export interface CurrentTaskInfo {
  task_id: string;
  title: string;
  status: string;
  started_at: string | null;
  attempts: number;
  max_attempts: number;
}

// Worker with enriched task information
export interface WorkerWithTask extends Worker {
  current_task: CurrentTaskInfo | null;
  capabilities: string[];
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

// Input API types (Bead Creator)

export interface UserInputRequest {
  project_id: string;
  text: string;
  priority?: Priority;
  auto_decompose?: boolean;
}

export interface CreatedTaskInfo {
  task_id: string;
  title: string;
  task_type: string;
  was_updated: boolean;
  matched_task_id: string | null;
}

export interface UserInputResponse {
  success: boolean;
  epic_id: string | null;
  created_tasks: CreatedTaskInfo[];
  dependencies_count: number;
  messages: string[];
}

export interface RelatedTaskInfo {
  task_id: string;
  title: string;
  similarity: number;
}

export interface SuggestRelatedRequest {
  project_id: string;
  text: string;
  max_results?: number;
}

export interface SuggestRelatedResponse {
  related_tasks: RelatedTaskInfo[];
}

// File upload types

export interface FileUploadResponse {
  path: string;
  filename: string;
  size: number;
  mime_type: string;
  media_type: "image" | "document" | "code" | "archive" | "file";
}

// Logs types

export const LogLevel = {
  DEBUG: "debug",
  INFO: "info",
  WARNING: "warning",
  ERROR: "error",
  CRITICAL: "critical",
} as const;
export type LogLevel = (typeof LogLevel)[keyof typeof LogLevel];

export const LogComponent = {
  API: "api",
  QUEUE: "queue",
  ENRICHER: "enricher",
  SCHEDULER: "scheduler",
  WORKER: "worker",
  RELOAD: "reload",
  CREATOR: "creator",
} as const;
export type LogComponent = (typeof LogComponent)[keyof typeof LogComponent];

export interface LogEntry {
  id: number;
  timestamp: string;
  level: LogLevel;
  component: LogComponent;
  message: string;
  task_id: string | null;
  worker_id: string | null;
  project_id: string | null;
  data: Record<string, unknown> | null;
}

export interface LogsResponse {
  logs: LogEntry[];
  total: number;
  offset: number;
  limit: number;
}

export interface LogStats {
  period_hours: number;
  total: number;
  errors: number;
  by_level: Record<string, number>;
  by_component: Record<string, number>;
}

// Graph types for dependency visualization

export interface GraphNode {
  id: string;
  title: string;
  task_type: TaskType;
  status: TaskStatus;
  priority: Priority;
  parent_id: string | null;
  pagerank_score: number;
  on_critical_path: boolean;
}

export interface GraphEdge {
  source: string;
  target: string;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
  stats: Record<string, number>;
}

// Bulk operations types

export interface BulkUpdateRequest {
  task_ids: string[];
  status?: TaskStatus | null;
  priority?: Priority | null;
  worker_id?: string | null;
  unassign?: boolean;
}

export interface BulkDeleteRequest {
  task_ids: string[];
}

export interface BulkOperationResponse {
  updated: number;
  failed: number;
  errors: string[];
}

// Undo/Redo types

export const ActionType = {
  TASK_CREATED: "task_created",
  TASK_UPDATED: "task_updated",
  TASK_DELETED: "task_deleted",
  TASK_STATUS_CHANGED: "task_status_changed",
  DEPENDENCY_CREATED: "dependency_created",
  DEPENDENCY_DELETED: "dependency_deleted",
  WORKER_ASSIGNED: "worker_assigned",
  WORKER_UNASSIGNED: "worker_unassigned",
} as const;
export type ActionType = (typeof ActionType)[keyof typeof ActionType];

export const EntityType = {
  TASK: "task",
  EPIC: "epic",
  SUBTASK: "subtask",
  WORKER: "worker",
  PROJECT: "project",
  DEPENDENCY: "dependency",
} as const;
export type EntityType = (typeof EntityType)[keyof typeof EntityType];

export interface ActionResponse {
  id: number;
  action_type: string;
  entity_type: string;
  entity_id: string;
  description: string;
  project_id: string | null;
  undone: boolean;
  created_at: string;
  actor_type: string;
  actor_id: string | null;
}

export interface UndoResponse {
  success: boolean;
  action: ActionResponse | null;
  message: string;
}

export interface HistoryResponse {
  actions: ActionResponse[];
  can_undo: boolean;
  can_redo: boolean;
}

// Worker Output types

export interface OutputLine {
  line: string;
  line_number: number;
  timestamp: string;
}

export interface OutputResponse {
  worker_id: string;
  lines: OutputLine[];
  total_lines: number;
}

export interface OutputBufferStats {
  [workerId: string]: {
    line_count: number;
    max_lines: number;
    total_lines: number;
    subscriber_count: number;
  };
}

// Decision and Question types for human-in-the-loop workflows

export const Urgency = {
  LOW: "low",
  MEDIUM: "medium",
  HIGH: "high",
} as const;
export type Urgency = (typeof Urgency)[keyof typeof Urgency];

export interface Decision {
  id: string;
  blocks_id: string;
  question: string;
  context: string | null;
  options: string[];
  recommendation: string | null;
  resolution: string | null;
  resolved_at: string | null;
  created_at: string;
}

export interface DecisionCreate {
  project_id: string;
  blocks_id: string;
  question: string;
  context?: string | null;
  options?: string[];
  recommendation?: string | null;
}

export interface DecisionResolve {
  resolution: string;
}

export interface DecisionStats {
  total: number;
  pending: number;
  resolved: number;
}

export interface Question {
  id: string;
  related_id: string;
  question: string;
  urgency: Urgency;
  default_answer: string | null;
  answer: string | null;
  answered_at: string | null;
  created_at: string;
}

export interface QuestionCreate {
  project_id: string;
  related_id: string;
  question: string;
  urgency?: Urgency;
  default_answer?: string | null;
}

export interface QuestionAnswer {
  answer: string;
}

export interface QuestionStats {
  total: number;
  pending: number;
  answered: number;
  by_urgency: Record<string, number>;
}

// Git History & Diff types

export interface CommitInfo {
  hash: string;
  short_hash: string;
  message: string;
  author_name: string;
  author_email: string;
  date: string;
  additions: number;
  deletions: number;
}

export interface FileHistoryResponse {
  path: string;
  commits: CommitInfo[];
  is_git_repo: boolean;
}

export interface DiffHunkInfo {
  old_start: number;
  old_count: number;
  new_start: number;
  new_count: number;
  header: string;
  lines: string[];
}

export interface FileDiffResponse {
  path: string;
  old_path: string;
  new_path: string;
  is_new: boolean;
  is_deleted: boolean;
  is_renamed: boolean;
  hunks: DiffHunkInfo[];
  additions: number;
  deletions: number;
  raw: string;
}

export interface FileAtCommitResponse {
  path: string;
  commit: string;
  content: string | null;
  exists: boolean;
}

// Worker Spawner types

export interface SpawnWorkerRequest {
  worker_type?: string; // claude-code, aider, codex, goose, generic
  capabilities?: string[];
  worktree_path?: string | null;
  custom_command?: string | null;
}

export interface SpawnedWorkerResponse {
  worker_id: string;
  worker_type: string;
  tmux_session: string;
  log_path: string | null;
  status: string;
  attach_command: string;
}

export interface TmuxSessionResponse {
  session_name: string;
  worker_id: string;
  attach_command: string;
}

export interface WorkerLogResponse {
  worker_id: string;
  log_path: string | null;
  output: string | null;
  lines_count: number;
}

// Task Validation types

export const ValidationStatus = {
  PASSED: "passed",
  FAILED: "failed",
  SKIPPED: "skipped",
  ERROR: "error",
} as const;
export type ValidationStatus =
  (typeof ValidationStatus)[keyof typeof ValidationStatus];

export interface ValidationCheck {
  name: string;
  status: ValidationStatus;
  message: string;
  duration_seconds: number;
}

export interface ValidationResponse {
  task_id: string;
  overall_passed: boolean;
  needs_human_review: boolean;
  review_reason: string;
  checks: ValidationCheck[];
  summary: string;
  new_status: string;
}

export interface ApproveResponse {
  task_id: string;
  status: string;
  approved: boolean;
}

export interface RejectResponse {
  task_id: string;
  status: string;
  rejected: boolean;
  reason: string | null;
}

// Worker Health types

export const LivenessStatus = {
  ACTIVE: "active",
  THINKING: "thinking",
  SLOW: "slow",
  LIKELY_HUNG: "likely_hung",
  DEGRADED: "degraded",
  UNKNOWN: "unknown",
} as const;
export type LivenessStatus =
  (typeof LivenessStatus)[keyof typeof LivenessStatus];

export const RecoveryUrgency = {
  LOW: "low",
  MEDIUM: "medium",
  HIGH: "high",
  CRITICAL: "critical",
} as const;
export type RecoveryUrgency =
  (typeof RecoveryUrgency)[keyof typeof RecoveryUrgency];

export interface DegradationSignals {
  repetition_score: number;
  apology_count: number;
  retry_count: number;
  contradiction_count: number;
  is_degraded: boolean;
}

export interface RecoveryAction {
  action: string; // "none", "log_warning", "interrupt", "checkpoint_restart", "escalate"
  reason: string;
  urgency: RecoveryUrgency;
}

export interface WorkerHealthResponse {
  worker_id: string;
  task_id: string | null;
  liveness_status: LivenessStatus;
  degradation: DegradationSignals;
  recommended_action: RecoveryAction;
  runtime_seconds: number;
  idle_seconds: number;
  total_output_lines: number;
}

// Model Routing types

export const TaskComplexity = {
  SIMPLE: "simple",
  MODERATE: "moderate",
  COMPLEX: "complex",
} as const;
export type TaskComplexity =
  (typeof TaskComplexity)[keyof typeof TaskComplexity];

export const ModelTier = {
  FAST: "fast",
  BALANCED: "balanced",
  POWERFUL: "powerful",
} as const;
export type ModelTier = (typeof ModelTier)[keyof typeof ModelTier];

export interface RoutingSignals {
  file_count: number;
  dependency_count: number;
  description_length: number;
  simple_keyword_matches: number;
  complex_keyword_matches: number;
  is_epic: boolean;
  is_subtask: boolean;
  is_critical: boolean;
  raw_score: number;
}

export interface RoutingRecommendation {
  task_id: string;
  complexity: TaskComplexity;
  tier: ModelTier;
  reasoning: string;
  suggested_models: string[];
  signals: RoutingSignals;
}

// Git Revert types

export interface RevertResponse {
  success: boolean;
  new_commit_hash: string | null;
  message: string;
  conflicts: string[] | null;
}
