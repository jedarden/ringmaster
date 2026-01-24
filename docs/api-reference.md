# Ringmaster API Reference

This document describes the REST API endpoints for the Ringmaster platform.

## Base URL

All API endpoints are prefixed with `/api/`.

## Response Format

### Success Responses

All successful responses follow this wrapper format:

```json
{
  "data": { /* response data */ },
  "meta": {
    "timestamp": "2025-01-24T12:34:56.789Z"
  }
}
```

### Paginated Responses

Paginated endpoints include pagination metadata:

```json
{
  "data": [ /* items */ ],
  "pagination": {
    "total": 100,
    "limit": 50,
    "offset": 0,
    "hasMore": true
  }
}
```

### Error Responses

Errors follow this format:

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human readable message",
    "details": null
  }
}
```

### HTTP Status Codes

| Code | Description |
|------|-------------|
| `200 OK` | Successful GET/PATCH operations |
| `201 Created` | Successful POST (creates resource) |
| `204 No Content` | Successful DELETE |
| `400 Bad Request` | Invalid input or invalid state transition |
| `401 Unauthorized` | Authentication required |
| `404 Not Found` | Resource not found |
| `429 Too Many Requests` | Rate limited |
| `500 Internal Server Error` | Internal error |

---

## Cards API

### List Cards

`GET /api/cards`

List all cards with optional filtering and pagination.

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `project_id` | UUID | Filter by project |
| `state` | string | Filter by card state |
| `labels` | string | Comma-separated labels |
| `search` | string | Search in title/description |
| `limit` | integer | Results per page (default: 50, max: 100) |
| `offset` | integer | Pagination offset |
| `sort` | string | Sort field |
| `order` | string | Sort order (`asc` or `desc`) |

**Response:**

```json
{
  "data": [
    {
      "id": "uuid",
      "projectId": "uuid",
      "title": "Implement feature X",
      "taskPrompt": "Create a new component...",
      "state": "coding",
      "loopIteration": 3,
      "errorCount": 0,
      "totalCostUsd": 1.25,
      "totalTokens": 50000,
      "labels": ["frontend", "feature"],
      "priority": 1,
      "createdAt": "2025-01-24T10:00:00Z",
      "updatedAt": "2025-01-24T12:30:00Z"
    }
  ],
  "pagination": {
    "total": 42,
    "limit": 50,
    "offset": 0,
    "hasMore": false
  }
}
```

### Create Card

`POST /api/cards`

Create a new card.

**Request Body:**

```json
{
  "projectId": "uuid",
  "title": "Implement feature X",
  "taskPrompt": "Create a new React component that...",
  "labels": ["frontend", "feature"],
  "priority": 1,
  "deadline": "2025-02-01T00:00:00Z",
  "acceptanceCriteria": [
    { "description": "Component renders correctly" },
    { "description": "Tests pass" }
  ]
}
```

**Response:** `201 Created`

```json
{
  "data": {
    "id": "uuid",
    "projectId": "uuid",
    "title": "Implement feature X",
    "state": "draft",
    "createdAt": "2025-01-24T10:00:00Z",
    "updatedAt": "2025-01-24T10:00:00Z"
  }
}
```

### Get Card

`GET /api/cards/:card_id`

Get a single card with acceptance criteria and dependencies.

**Response:**

```json
{
  "data": {
    "card": { /* Card object */ },
    "acceptanceCriteria": [
      {
        "id": "uuid",
        "description": "Component renders correctly",
        "met": false
      }
    ],
    "dependencies": []
  }
}
```

### Update Card

`PATCH /api/cards/:card_id`

Update card details.

**Request Body:**

```json
{
  "title": "Updated title",
  "taskPrompt": "Updated task description",
  "labels": ["backend"],
  "priority": 2
}
```

**Response:** Updated card object.

### Delete Card

`DELETE /api/cards/:card_id`

Delete a card.

**Response:** `204 No Content`

### Transition Card State

`POST /api/cards/:card_id/transition`

Trigger a state machine transition.

**Request Body:**

```json
{
  "trigger": "StartCoding"
}
```

**Available Triggers:**

| Trigger | Description |
|---------|-------------|
| `StartPlanning` | Move to planning state |
| `PlanApproved` | Approve the plan |
| `StartCoding` | Begin coding loop |
| `LoopComplete` | Mark coding complete |
| `RequestReview` | Request code review |
| `ReviewApproved` | Approve review |
| `ReviewRejected` | Reject review |
| `StartTesting` | Begin testing |
| `TestsPassed` | Tests passed |
| `TestsFailed` | Tests failed |
| `QueueBuild` | Queue for build |
| `BuildStarted` | Build started |
| `BuildSucceeded` | Build succeeded |
| `BuildFailed` | Build failed |
| `QueueDeploy` | Queue for deployment |
| `DeployStarted` | Deployment started |
| `DeployCompleted` | Deployment completed |
| `VerificationPassed` | Verification passed |
| `VerificationFailed` | Verification failed |
| `ErrorDetected` | Error detected |
| `ErrorFixed` | Error fixed |
| `Retry` | Retry operation |
| `Archive` | Archive card |
| `Unarchive` | Unarchive card |
| `MarkFailed` | Mark as failed |

**Response:**

```json
{
  "data": {
    "previousState": "draft",
    "newState": "planning",
    "card": { /* Updated card object */ }
  }
}
```

---

## Projects API

### List Projects

`GET /api/projects`

List all projects with statistics.

**Response:**

```json
{
  "data": [
    {
      "id": "uuid",
      "name": "Ringmaster",
      "repositoryUrl": "https://github.com/org/repo",
      "description": "SDLC orchestration platform",
      "defaultBranch": "main",
      "cardCount": 15,
      "activeLoops": 2,
      "totalCostUsd": 45.00,
      "createdAt": "2025-01-01T00:00:00Z",
      "updatedAt": "2025-01-24T12:00:00Z"
    }
  ]
}
```

### Create Project

`POST /api/projects`

Create a new project.

**Request Body:**

```json
{
  "name": "Project Name",
  "repositoryUrl": "https://github.com/org/repo",
  "description": "Project description",
  "defaultBranch": "main",
  "techStack": ["rust", "react"],
  "codingConventions": "Follow existing patterns..."
}
```

**Response:** `201 Created`

### Get Project

`GET /api/projects/:project_id`

Get a single project.

### Update Project

`PATCH /api/projects/:project_id`

Update project details.

### Delete Project

`DELETE /api/projects/:project_id`

Delete a project.

**Response:** `204 No Content`

---

## Loops API

### Get Loop State

`GET /api/cards/:card_id/loop`

Get the current loop state for a card.

**Response:**

```json
{
  "data": {
    "cardId": "uuid",
    "status": "running",
    "iteration": 5,
    "totalCostUsd": 2.50,
    "totalTokens": 100000,
    "consecutiveErrors": 0,
    "startTime": "2025-01-24T10:00:00Z",
    "elapsedSeconds": 1800,
    "config": {
      "maxIterations": 100,
      "maxRuntimeSeconds": 3600,
      "maxCostUsd": 10.00,
      "checkpointInterval": 10,
      "cooldownSeconds": 5,
      "maxConsecutiveErrors": 3,
      "completionSignal": "TASK_COMPLETE"
    }
  }
}
```

### Start Loop

`POST /api/cards/:card_id/loop/start`

Start an autonomous coding loop.

**Request Body:**

```json
{
  "config": {
    "maxIterations": 50,
    "maxCostUsd": 5.00,
    "maxRuntimeSeconds": 1800
  },
  "subscription": "sub_123"
}
```

**Response:**

```json
{
  "data": {
    "loopId": "uuid",
    "cardId": "uuid",
    "state": { /* LoopState object */ }
  }
}
```

### Pause Loop

`POST /api/cards/:card_id/loop/pause`

Pause an active loop.

### Resume Loop

`POST /api/cards/:card_id/loop/resume`

Resume a paused loop.

### Stop Loop

`POST /api/cards/:card_id/loop/stop`

Stop a running loop.

**Response:**

```json
{
  "data": {
    "status": "stopped",
    "finalIteration": 15,
    "totalCostUsd": 3.75
  }
}
```

### List Active Loops

`GET /api/loops`

List all currently active loops across all cards.

**Response:**

```json
{
  "data": {
    "loops": [
      {
        "cardId": "uuid",
        "cardTitle": "Implement feature",
        "iteration": 5,
        "status": "running",
        "totalCostUsd": 2.50
      }
    ],
    "stats": {
      "totalActive": 3,
      "running": 2,
      "paused": 1,
      "totalCostUsd": 12.50,
      "totalIterations": 45
    }
  }
}
```

---

## Attempts API

### List Attempts

`GET /api/cards/:card_id/attempts`

List all loop attempts for a card.

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `status` | string | Filter by status |
| `limit` | integer | Results per page |
| `offset` | integer | Pagination offset |

**Response:**

```json
{
  "data": [
    {
      "id": "uuid",
      "cardId": "uuid",
      "attemptNumber": 1,
      "iteration": 5,
      "inputTokens": 5000,
      "outputTokens": 2000,
      "costUsd": 0.25,
      "durationMs": 45000,
      "completionSignalFound": false,
      "commitSha": "abc123",
      "diffStats": {
        "insertions": 150,
        "deletions": 30,
        "filesChanged": 5
      },
      "status": "completed",
      "startedAt": "2025-01-24T10:00:00Z",
      "createdAt": "2025-01-24T10:00:00Z"
    }
  ],
  "pagination": { /* ... */ }
}
```

### Get Attempt

`GET /api/cards/:card_id/attempts/:attempt_id`

Get details of a specific attempt.

---

## Errors API

### List Errors

`GET /api/cards/:card_id/errors`

List errors for a card.

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `resolved` | boolean | Filter by resolved status |
| `category` | string | Filter by category (`build`, `test`, `deploy`, `runtime`, `other`) |
| `limit` | integer | Results per page |
| `offset` | integer | Pagination offset |

### Get Error

`GET /api/cards/:card_id/errors/:error_id`

Get a specific error.

### Resolve Error

`POST /api/cards/:card_id/errors/:error_id/resolve`

Mark an error as resolved.

**Request Body:**

```json
{
  "resolutionAttemptId": "uuid"
}
```

---

## Metrics API

### Get Summary

`GET /api/metrics/summary`

Get overall metrics summary.

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `period` | string | Time period: `day`, `week`, `month`, `all` |

**Response:**

```json
{
  "data": {
    "totalCards": 150,
    "completedCards": 100,
    "activeLoops": 5,
    "totalCostUsd": 500.00,
    "totalTokens": 10000000,
    "averageCostPerCard": 3.33
  }
}
```

### Get Card Metrics

`GET /api/metrics/by-card/:card_id`

Get metrics for a specific card.

### Get Subscription Metrics

`GET /api/metrics/by-subscription`

Get metrics grouped by subscription.

---

## Integrations API

### GitHub Actions

#### List Workflows

`GET /api/integrations/github/workflows/:owner/:repo`

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `branch` | string | Filter by branch |
| `status` | string | Filter by status |
| `per_page` | integer | Results per page |

#### Get Workflow Run

`GET /api/integrations/github/workflows/:owner/:repo/:run_id`

#### Get Workflow Jobs

`GET /api/integrations/github/workflows/:owner/:repo/:run_id/jobs`

#### Dispatch Workflow

`POST /api/integrations/github/workflows/:owner/:repo/:workflow_id/dispatch`

**Request Body:**

```json
{
  "ref": "main",
  "inputs": {
    "environment": "production"
  }
}
```

#### Cancel Workflow

`POST /api/integrations/github/workflows/:owner/:repo/:run_id/cancel`

### ArgoCD

#### List Applications

`GET /api/integrations/argocd/apps`

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `project` | string | Filter by project |
| `server_url` | string | ArgoCD server URL |

#### Get Application

`GET /api/integrations/argocd/apps/:app_name`

#### Sync Application

`POST /api/integrations/argocd/apps/:app_name/sync`

**Request Body:**

```json
{
  "revision": "main",
  "prune": true,
  "server_url": "https://argocd.example.com"
}
```

#### Rollback Application

`POST /api/integrations/argocd/apps/:app_name/rollback`

#### Refresh Application

`POST /api/integrations/argocd/apps/:app_name/refresh`

### Docker Hub

#### List Tags

`GET /api/integrations/dockerhub/tags/:namespace/:repo`

#### Get Tag

`GET /api/integrations/dockerhub/tags/:namespace/:repo/:tag`

#### Get Repository

`GET /api/integrations/dockerhub/repos/:namespace/:repo`

#### Get Latest Tag

`GET /api/integrations/dockerhub/latest/:namespace/:repo`

### Kubernetes

#### Get Deployment Status

`GET /api/integrations/k8s/:namespace/deployments/:name`

#### List Pods

`GET /api/integrations/k8s/:namespace/pods`

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `label_selector` | string | Label selector |

#### Get Pod Logs

`GET /api/integrations/k8s/:namespace/pods/:pod_name/logs`

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `container` | string | Container name |
| `tail_lines` | integer | Number of lines to tail |
| `previous` | boolean | Get previous container logs |

#### Get Deployment Errors

`GET /api/integrations/k8s/:namespace/deployments/:name/errors`

---

## WebSocket API

### Connect

`GET /api/ws` (WebSocket upgrade)

Connect to the real-time event stream.

### Client Messages

#### Subscribe

```json
{
  "type": "subscribe",
  "card_ids": ["uuid1", "uuid2"],
  "project_ids": ["uuid3"]
}
```

#### Unsubscribe

```json
{
  "type": "unsubscribe",
  "card_ids": ["uuid1"]
}
```

#### Ping

```json
{
  "type": "ping"
}
```

### Server Messages

#### Pong

```json
{
  "type": "pong"
}
```

#### Event

```json
{
  "type": "event",
  "eventType": "CardStateChanged",
  "cardId": "uuid",
  "data": { /* event-specific data */ }
}
```

#### Error

```json
{
  "type": "error",
  "message": "Error description"
}
```

---

## Health Check

`GET /health`

Returns `OK` if the service is healthy.

**Response:** `200 OK` with body `OK`
