# API Specification

## Overview

Ringmaster exposes a RESTful API for all operations, plus a WebSocket endpoint for real-time updates. All endpoints are prefixed with `/api`.

## Base URL

```
http://localhost:8080/api
```

## Authentication

Authentication is optional for local use. When enabled:

```http
Authorization: Bearer <token>
```

## Common Response Formats

### Success Response
```json
{
  "data": { ... },
  "meta": {
    "timestamp": "2024-01-15T10:30:00Z"
  }
}
```

### Error Response
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid card state transition",
    "details": {
      "field": "trigger",
      "reason": "Cannot transition from DRAFT to BUILDING"
    }
  }
}
```

### Paginated Response
```json
{
  "data": [...],
  "pagination": {
    "total": 150,
    "limit": 50,
    "offset": 0,
    "hasMore": true
  }
}
```

---

## Cards API

### List Cards

```http
GET /api/cards
```

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `project_id` | uuid | Filter by project |
| `state` | string[] | Filter by states (comma-separated) |
| `labels` | string[] | Filter by labels (comma-separated) |
| `search` | string | Search in title and description |
| `limit` | int | Max results (default: 50, max: 100) |
| `offset` | int | Pagination offset |
| `sort` | string | Sort field: `created_at`, `updated_at`, `priority` |
| `order` | string | Sort order: `asc`, `desc` |

**Response:**
```json
{
  "data": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "projectId": "660e8400-e29b-41d4-a716-446655440000",
      "title": "Implement user authentication",
      "description": "Add JWT-based auth to API",
      "state": "coding",
      "previousState": "planning",
      "stateChangedAt": "2024-01-15T10:00:00Z",
      "loopIteration": 7,
      "totalTimeSpentMs": 3600000,
      "totalCostUsd": 12.47,
      "worktreePath": "/home/coder/.ringmaster/worktrees/card-550e8400",
      "branchName": "feature/card-550e8400",
      "pullRequestUrl": null,
      "labels": ["backend", "security"],
      "priority": 1,
      "createdAt": "2024-01-14T09:00:00Z",
      "updatedAt": "2024-01-15T10:30:00Z"
    }
  ],
  "pagination": {
    "total": 25,
    "limit": 50,
    "offset": 0,
    "hasMore": false
  }
}
```

### Get Card

```http
GET /api/cards/{cardId}
```

**Response:**
```json
{
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "projectId": "660e8400-e29b-41d4-a716-446655440000",
    "title": "Implement user authentication",
    "description": "Add JWT-based auth to API endpoints...",
    "taskPrompt": "Implement JWT authentication with the following requirements...",
    "state": "coding",
    "previousState": "planning",
    "stateChangedAt": "2024-01-15T10:00:00Z",
    "loopIteration": 7,
    "totalTimeSpentMs": 3600000,
    "totalCostUsd": 12.47,
    "worktreePath": "/home/coder/.ringmaster/worktrees/card-550e8400",
    "branchName": "feature/card-550e8400",
    "pullRequestUrl": null,
    "deploymentNamespace": "default",
    "deploymentName": "my-app",
    "argocdAppName": "my-app",
    "labels": ["backend", "security"],
    "priority": 1,
    "deadline": null,
    "errorCount": 0,
    "maxRetries": 5,
    "createdAt": "2024-01-14T09:00:00Z",
    "updatedAt": "2024-01-15T10:30:00Z",
    "acceptanceCriteria": [
      {
        "id": "ac-001",
        "description": "User registration endpoint with email validation",
        "met": false,
        "metAt": null,
        "orderIndex": 0
      },
      {
        "id": "ac-002",
        "description": "Login endpoint returning JWT token",
        "met": false,
        "metAt": null,
        "orderIndex": 1
      }
    ],
    "dependencies": [
      {
        "cardId": "770e8400-e29b-41d4-a716-446655440000",
        "title": "Database schema setup",
        "state": "completed",
        "dependencyType": "blocks"
      }
    ]
  }
}
```

### Create Card

```http
POST /api/cards
```

**Request Body:**
```json
{
  "projectId": "660e8400-e29b-41d4-a716-446655440000",
  "title": "Implement user authentication",
  "description": "Add JWT-based auth to API endpoints",
  "taskPrompt": "Implement JWT authentication with the following requirements:\n1. User registration with email validation\n2. Login endpoint returning JWT\n3. Middleware for protected routes\n4. Token refresh mechanism",
  "acceptanceCriteria": [
    { "description": "User registration endpoint with email validation" },
    { "description": "Login endpoint returning JWT token" },
    { "description": "Middleware for protected routes" },
    { "description": "Token refresh mechanism" },
    { "description": "Unit tests with >80% coverage" }
  ],
  "labels": ["backend", "security"],
  "priority": 1,
  "deadline": "2024-01-20T00:00:00Z",
  "deploymentNamespace": "default",
  "deploymentName": "my-app",
  "argocdAppName": "my-app"
}
```

**Response:** `201 Created`
```json
{
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "state": "draft",
    ...
  }
}
```

### Update Card

```http
PATCH /api/cards/{cardId}
```

**Request Body:** (partial update)
```json
{
  "title": "Updated title",
  "description": "Updated description",
  "labels": ["backend", "security", "priority-high"],
  "priority": 0
}
```

**Response:** `200 OK`
```json
{
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    ...
  }
}
```

### Delete Card

```http
DELETE /api/cards/{cardId}
```

**Response:** `204 No Content`

### State Transition

```http
POST /api/cards/{cardId}/transition
```

**Request Body:**
```json
{
  "trigger": "ApprovePlan",
  "data": {
    "reviewerNotes": "Looks good, proceed with implementation"
  }
}
```

**Available Triggers:**
| Trigger | Valid From States | To State |
|---------|-------------------|----------|
| `StartPlanning` | DRAFT | PLANNING |
| `ApprovePlan` | PLANNING | CODING |
| `RejectPlan` | PLANNING | DRAFT |
| `ApproveReview` | CODE_REVIEW | TESTING |
| `RejectReview` | CODE_REVIEW | CODING |
| `Archive` | COMPLETED, FAILED | ARCHIVED |

**Response:**
```json
{
  "data": {
    "previousState": "planning",
    "newState": "coding",
    "card": { ... }
  }
}
```

**Error Response (Invalid Transition):**
```json
{
  "error": {
    "code": "INVALID_TRANSITION",
    "message": "Cannot transition from DRAFT to CODING",
    "details": {
      "currentState": "draft",
      "trigger": "ApproveReview",
      "validTriggers": ["StartPlanning"]
    }
  }
}
```

---

## Loops API

### Start Loop

```http
POST /api/cards/{cardId}/loop/start
```

**Request Body:** (optional config overrides)
```json
{
  "config": {
    "maxIterations": 50,
    "maxRuntimeSeconds": 7200,
    "maxCostUsd": 100.0,
    "checkpointInterval": 10,
    "cooldownSeconds": 3,
    "completionSignal": "<promise>COMPLETE</promise>"
  }
}
```

**Response:**
```json
{
  "data": {
    "loopId": "loop-550e8400",
    "cardId": "550e8400-e29b-41d4-a716-446655440000",
    "state": {
      "iteration": 0,
      "status": "running",
      "totalCostUsd": 0.0,
      "totalTokens": 0,
      "consecutiveErrors": 0,
      "startTime": "2024-01-15T10:30:00Z"
    }
  }
}
```

### Get Loop State

```http
GET /api/cards/{cardId}/loop
```

**Response:**
```json
{
  "data": {
    "cardId": "550e8400-e29b-41d4-a716-446655440000",
    "iteration": 12,
    "status": "running",
    "totalCostUsd": 8.45,
    "totalTokens": 156000,
    "consecutiveErrors": 0,
    "lastCheckpoint": 10,
    "startTime": "2024-01-15T10:30:00Z",
    "elapsedSeconds": 1847,
    "config": {
      "maxIterations": 100,
      "maxRuntimeSeconds": 14400,
      "maxCostUsd": 300.0
    }
  }
}
```

**Response (No Active Loop):**
```json
{
  "data": null
}
```

### Pause Loop

```http
POST /api/cards/{cardId}/loop/pause
```

**Response:**
```json
{
  "data": {
    "status": "paused",
    "iteration": 12,
    ...
  }
}
```

### Resume Loop

```http
POST /api/cards/{cardId}/loop/resume
```

**Response:**
```json
{
  "data": {
    "status": "running",
    ...
  }
}
```

### Stop Loop

```http
POST /api/cards/{cardId}/loop/stop
```

**Response:**
```json
{
  "data": {
    "status": "stopped",
    "finalIteration": 12,
    "totalCostUsd": 8.45
  }
}
```

### List Active Loops

```http
GET /api/loops
```

**Response:**
```json
{
  "data": [
    {
      "cardId": "550e8400-e29b-41d4-a716-446655440000",
      "cardTitle": "Implement user auth",
      "iteration": 12,
      "status": "running",
      "totalCostUsd": 8.45
    },
    {
      "cardId": "660e8400-e29b-41d4-a716-446655440000",
      "cardTitle": "Add API rate limiting",
      "iteration": 5,
      "status": "paused",
      "totalCostUsd": 3.21
    }
  ],
  "stats": {
    "totalActive": 2,
    "running": 1,
    "paused": 1,
    "totalCostUsd": 11.66,
    "totalIterations": 17
  }
}
```

---

## Attempts API

### List Attempts

```http
GET /api/cards/{cardId}/attempts
```

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `status` | string | Filter by status |
| `limit` | int | Max results (default: 20) |
| `offset` | int | Pagination offset |

**Response:**
```json
{
  "data": [
    {
      "id": "attempt-001",
      "cardId": "550e8400-e29b-41d4-a716-446655440000",
      "attemptNumber": 12,
      "agentType": "claude-opus-4",
      "status": "completed",
      "startedAt": "2024-01-15T10:45:00Z",
      "completedAt": "2024-01-15T10:48:30Z",
      "durationMs": 210000,
      "tokensUsed": 15420,
      "costUsd": 0.89,
      "commitSha": "a1b2c3d4",
      "diffStats": {
        "filesChanged": 3,
        "insertions": 145,
        "deletions": 12
      }
    }
  ],
  "pagination": {
    "total": 12,
    "limit": 20,
    "offset": 0,
    "hasMore": false
  }
}
```

### Get Attempt Details

```http
GET /api/cards/{cardId}/attempts/{attemptId}
```

**Response:**
```json
{
  "data": {
    "id": "attempt-001",
    "cardId": "550e8400-e29b-41d4-a716-446655440000",
    "attemptNumber": 12,
    "agentType": "claude-opus-4",
    "status": "completed",
    "startedAt": "2024-01-15T10:45:00Z",
    "completedAt": "2024-01-15T10:48:30Z",
    "durationMs": 210000,
    "tokensUsed": 15420,
    "costUsd": 0.89,
    "output": "## Analysis\n\nLooking at the current auth implementation...\n\n## Implementation\n\n```rust\n// File: src/middleware/auth.rs\n...\n```\n\n<promise>CODE_COMPLETE</promise>",
    "errorMessage": null,
    "commitSha": "a1b2c3d4",
    "diffStats": {
      "filesChanged": 3,
      "insertions": 145,
      "deletions": 12
    }
  }
}
```

---

## Errors API

### List Errors

```http
GET /api/cards/{cardId}/errors
```

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `resolved` | bool | Filter by resolution status |
| `category` | string | Filter by category: `build`, `test`, `deploy`, `runtime` |
| `limit` | int | Max results |
| `offset` | int | Pagination offset |

**Response:**
```json
{
  "data": [
    {
      "id": "error-001",
      "cardId": "550e8400-e29b-41d4-a716-446655440000",
      "attemptId": "attempt-010",
      "errorType": "CompilationError",
      "message": "the trait bound `Claims: Deserialize<'_>` is not satisfied",
      "category": "build",
      "severity": "error",
      "resolved": true,
      "resolvedAt": "2024-01-15T11:00:00Z",
      "resolutionAttemptId": "attempt-012",
      "createdAt": "2024-01-15T10:30:00Z"
    }
  ]
}
```

### Get Error Details

```http
GET /api/cards/{cardId}/errors/{errorId}
```

**Response:**
```json
{
  "data": {
    "id": "error-001",
    "cardId": "550e8400-e29b-41d4-a716-446655440000",
    "errorType": "CompilationError",
    "message": "the trait bound `Claims: Deserialize<'_>` is not satisfied",
    "stackTrace": "error[E0277]: the trait bound...\n  --> src/middleware/auth.rs:14:5\n...",
    "context": {
      "file": "src/middleware/auth.rs",
      "line": 14,
      "sourceState": "building",
      "buildRunId": 12345678,
      "logs": "Run cargo build --release\n..."
    },
    "category": "build",
    "severity": "error",
    "resolved": true,
    "resolvedAt": "2024-01-15T11:00:00Z",
    "resolutionAttemptId": "attempt-012",
    "createdAt": "2024-01-15T10:30:00Z"
  }
}
```

### Mark Error Resolved

```http
POST /api/cards/{cardId}/errors/{errorId}/resolve
```

**Request Body:**
```json
{
  "resolutionAttemptId": "attempt-012"
}
```

**Response:**
```json
{
  "data": {
    "id": "error-001",
    "resolved": true,
    "resolvedAt": "2024-01-15T11:00:00Z",
    ...
  }
}
```

---

## Projects API

### List Projects

```http
GET /api/projects
```

**Response:**
```json
{
  "data": [
    {
      "id": "660e8400-e29b-41d4-a716-446655440000",
      "name": "My API",
      "description": "Backend API service",
      "repositoryUrl": "https://github.com/org/my-api",
      "repositoryPath": "/home/coder/projects/my-api",
      "techStack": ["rust", "axum", "postgresql"],
      "cardCount": 15,
      "activeLoops": 2,
      "createdAt": "2024-01-01T00:00:00Z"
    }
  ]
}
```

### Create Project

```http
POST /api/projects
```

**Request Body:**
```json
{
  "name": "My API",
  "description": "Backend API service",
  "repositoryUrl": "https://github.com/org/my-api",
  "repositoryPath": "/home/coder/projects/my-api",
  "techStack": ["rust", "axum", "postgresql"],
  "codingConventions": "Use thiserror for error types. All handlers return Result<Json<T>, AppError>..."
}
```

---

## Integrations API

### GitHub Actions Status

```http
GET /api/integrations/github/workflows/{runId}
```

**Response:**
```json
{
  "data": {
    "id": 12345678,
    "name": "Build and Deploy",
    "status": "completed",
    "conclusion": "success",
    "branch": "feature/card-550e8400",
    "htmlUrl": "https://github.com/org/repo/actions/runs/12345678",
    "createdAt": "2024-01-15T10:00:00Z",
    "updatedAt": "2024-01-15T10:15:00Z",
    "jobs": [
      {
        "name": "build",
        "status": "completed",
        "conclusion": "success"
      },
      {
        "name": "test",
        "status": "completed",
        "conclusion": "success"
      }
    ]
  }
}
```

### ArgoCD Application Status

```http
GET /api/integrations/argocd/apps/{appName}
```

**Response:**
```json
{
  "data": {
    "name": "my-app",
    "namespace": "argocd",
    "syncStatus": "Synced",
    "healthStatus": "Healthy",
    "operationState": {
      "phase": "Succeeded",
      "message": "successfully synced"
    },
    "resources": [
      {
        "kind": "Deployment",
        "name": "my-app",
        "namespace": "default",
        "status": "Synced",
        "health": "Healthy"
      },
      {
        "kind": "Service",
        "name": "my-app",
        "namespace": "default",
        "status": "Synced",
        "health": "Healthy"
      }
    ]
  }
}
```

### Trigger ArgoCD Sync

```http
POST /api/integrations/argocd/apps/{appName}/sync
```

**Response:**
```json
{
  "data": {
    "syncing": true,
    "message": "Sync initiated"
  }
}
```

### ArgoCD Rollback

```http
POST /api/integrations/argocd/apps/{appName}/rollback
```

**Request Body:**
```json
{
  "revision": 5
}
```

---

## WebSocket API

### Connection

```
WS /api/ws
```

### Client Messages

**Subscribe to Cards:**
```json
{
  "type": "subscribe",
  "cardIds": ["550e8400-e29b-41d4-a716-446655440000"],
  "projectIds": ["660e8400-e29b-41d4-a716-446655440000"]
}
```

**Unsubscribe:**
```json
{
  "type": "unsubscribe",
  "cardIds": ["550e8400-e29b-41d4-a716-446655440000"]
}
```

**Ping:**
```json
{
  "type": "ping"
}
```

### Server Messages

**Card Updated:**
```json
{
  "type": "card_updated",
  "cardId": "550e8400-e29b-41d4-a716-446655440000",
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "state": "coding",
    ...
  },
  "timestamp": "2024-01-15T10:30:00Z"
}
```

**State Changed:**
```json
{
  "type": "state_changed",
  "cardId": "550e8400-e29b-41d4-a716-446655440000",
  "data": {
    "from": "planning",
    "to": "coding",
    "trigger": "ApprovePlan"
  },
  "timestamp": "2024-01-15T10:30:00Z"
}
```

**Loop Iteration:**
```json
{
  "type": "loop_iteration",
  "cardId": "550e8400-e29b-41d4-a716-446655440000",
  "data": {
    "iteration": 12,
    "status": "running",
    "tokensUsed": 15420,
    "costUsd": 0.89
  },
  "timestamp": "2024-01-15T10:30:00Z"
}
```

**Loop Completed:**
```json
{
  "type": "loop_completed",
  "cardId": "550e8400-e29b-41d4-a716-446655440000",
  "data": {
    "result": "CompletionSignal",
    "totalIterations": 12,
    "totalCostUsd": 8.45,
    "totalTokens": 156000
  },
  "timestamp": "2024-01-15T10:30:00Z"
}
```

**Build Status:**
```json
{
  "type": "build_status",
  "cardId": "550e8400-e29b-41d4-a716-446655440000",
  "data": {
    "runId": 12345678,
    "status": "completed",
    "conclusion": "success"
  },
  "timestamp": "2024-01-15T10:30:00Z"
}
```

**Deploy Status:**
```json
{
  "type": "deploy_status",
  "cardId": "550e8400-e29b-41d4-a716-446655440000",
  "data": {
    "appName": "my-app",
    "syncStatus": "Synced",
    "healthStatus": "Healthy"
  },
  "timestamp": "2024-01-15T10:30:00Z"
}
```

**Error Detected:**
```json
{
  "type": "error_detected",
  "cardId": "550e8400-e29b-41d4-a716-446655440000",
  "data": {
    "errorId": "error-001",
    "errorType": "CompilationError",
    "message": "the trait bound...",
    "category": "build"
  },
  "timestamp": "2024-01-15T10:30:00Z"
}
```

**Pong:**
```json
{
  "type": "pong"
}
```

---

## Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `VALIDATION_ERROR` | 400 | Request body validation failed |
| `NOT_FOUND` | 404 | Resource not found |
| `INVALID_TRANSITION` | 400 | Invalid state transition |
| `GUARD_FAILED` | 400 | Transition guard condition not met |
| `LOOP_ALREADY_EXISTS` | 409 | Loop already running for card |
| `LOOP_NOT_FOUND` | 404 | No active loop for card |
| `CONCURRENCY_LIMIT` | 429 | Max concurrent loops reached |
| `INTEGRATION_ERROR` | 502 | External service error |
| `INTERNAL_ERROR` | 500 | Internal server error |

---

## Rate Limits

| Endpoint | Limit |
|----------|-------|
| All endpoints | 100 req/min |
| `/api/cards/*/loop/start` | 10 req/min |
| WebSocket messages | 50 msg/sec |

---

## OpenAPI Specification

Full OpenAPI 3.0 specification available at:

```
GET /api/openapi.json
GET /api/openapi.yaml
```

Swagger UI available at:

```
GET /api/docs
```
