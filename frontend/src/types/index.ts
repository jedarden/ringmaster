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
  errorCount: number;
  totalCostUsd: number;
  totalTokens: number;
  labels: string[];
  priority: number;
  pullRequestUrl?: string;
  branchName?: string;
  worktreePath?: string;
  deploymentName?: string;
  deploymentNamespace?: string;
  argocdAppName?: string;
  deadline?: string;
  acceptanceCriteria?: AcceptanceCriterion[];
  createdAt: string;
  updatedAt: string;
  stateChangedAt?: string;
}

export interface AcceptanceCriterion {
  id: string;
  description: string;
  met: boolean;
}

export interface Project {
  id: string;
  name: string;
  description?: string;
  repositoryUrl: string;
  repositoryPath?: string;
  defaultBranch: string;
  techStack?: string[];
  codingConventions?: string;
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

// Response type for GET /api/loops (list all active loops)
export interface ActiveLoopInfo {
  cardId: string;
  cardTitle: string;
  iteration: number;
  status: LoopStatus;
  totalCostUsd: number;
}

export interface ActiveLoopsStats {
  totalActive: number;
  running: number;
  paused: number;
  totalCostUsd: number;
  totalIterations: number;
}

export interface ActiveLoopsResponse {
  loops: ActiveLoopInfo[];
  stats: ActiveLoopsStats;
}

export interface Attempt {
  id: string;
  cardId: string;
  attemptNumber: number;
  iteration: number;
  promptHash: string;
  inputTokens: number;
  outputTokens: number;
  tokensUsed?: number;
  costUsd: number;
  durationMs: number;
  output?: string;
  outputSummary?: string;
  completionSignalFound: boolean;
  commitSha?: string;
  diffStats?: {
    insertions: number;
    deletions: number;
    filesChanged: number;
  };
  status: 'pending' | 'running' | 'completed' | 'failed';
  errorMessage?: string;
  startedAt: string;
  createdAt: string;
}

export interface CardError {
  id: string;
  cardId: string;
  errorType: string;
  category: 'build' | 'test' | 'deploy' | 'runtime' | 'other';
  message: string;
  stackTrace?: string;
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
