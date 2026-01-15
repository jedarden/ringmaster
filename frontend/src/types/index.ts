// Card states based on the state machine
export type CardState =
  | 'draft'
  | 'planning'
  | 'coding'
  | 'code_review'
  | 'testing'
  | 'build_queue'
  | 'building'
  | 'build_success'
  | 'build_failed'
  | 'deploy_queue'
  | 'deploying'
  | 'verifying'
  | 'completed'
  | 'error_fixing'
  | 'archived'
  | 'failed';

export interface Card {
  id: string;
  projectId: string;
  title: string;
  description?: string;
  taskPrompt: string;
  state: CardState;
  previousState?: CardState;
  loopIteration: number;
  totalCostUsd: number;
  totalTokens: number;
  labels: string[];
  priority: number;
  pullRequestUrl?: string;
  branchName?: string;
  worktreePath?: string;
  createdAt: string;
  updatedAt: string;
  stateChangedAt?: string;
}

export interface Project {
  id: string;
  name: string;
  description?: string;
  repoUrl: string;
  repoPath: string;
  defaultBranch: string;
  cardCount: number;
  activeLoops: number;
  totalCostUsd: number;
  createdAt: string;
  updatedAt: string;
}

export interface LoopConfig {
  maxIterations: number;
  maxRuntimeSeconds: number;
  maxCostUsd: number;
  checkpointInterval: number;
  cooldownSeconds: number;
  maxConsecutiveErrors: number;
  completionSignal: string;
}

export type LoopStatus = 'running' | 'paused' | 'completed' | 'stopped' | 'failed';

export type StopReason =
  | 'CompletionSignal'
  | 'MaxIterations'
  | 'CostLimit'
  | 'TimeLimit'
  | 'UserStopped'
  | 'CircuitBreaker'
  | { Error: string };

export interface LoopState {
  cardId: string;
  iteration: number;
  status: LoopStatus;
  totalCostUsd: number;
  totalTokens: number;
  consecutiveErrors: number;
  lastCheckpoint?: number;
  startTime: string;
  elapsedSeconds: number;
  config: LoopConfig;
  stopReason?: StopReason;
}

export interface Attempt {
  id: string;
  cardId: string;
  iteration: number;
  promptHash: string;
  inputTokens: number;
  outputTokens: number;
  costUsd: number;
  durationMs: number;
  outputSummary?: string;
  completionSignalFound: boolean;
  createdAt: string;
}

export interface CardError {
  id: string;
  cardId: string;
  errorType: string;
  message: string;
  context?: Record<string, unknown>;
  resolved: boolean;
  resolvedAt?: string;
  createdAt: string;
}

// API response types
export interface ApiResponse<T> {
  data: T;
  meta: {
    timestamp: string;
  };
}

export interface PaginatedResponse<T> {
  data: T[];
  pagination: {
    total: number;
    limit: number;
    offset: number;
    hasMore: boolean;
  };
}

export interface ApiError {
  error: {
    code: string;
    message: string;
    details?: unknown;
  };
}

// Trigger types for state transitions
export type Trigger =
  | 'StartPlanning'
  | 'PlanApproved'
  | 'StartCoding'
  | 'LoopComplete'
  | 'RequestReview'
  | 'ReviewApproved'
  | 'ReviewRejected'
  | 'StartTesting'
  | 'TestsPassed'
  | 'TestsFailed'
  | 'QueueBuild'
  | 'BuildStarted'
  | 'BuildSucceeded'
  | 'BuildFailed'
  | 'QueueDeploy'
  | 'DeployStarted'
  | 'DeployCompleted'
  | 'VerificationPassed'
  | 'VerificationFailed'
  | 'ErrorDetected'
  | 'ErrorFixed'
  | 'Retry'
  | 'Archive'
  | 'Unarchive'
  | 'MarkFailed';
