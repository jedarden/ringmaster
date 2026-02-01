# ADR-018: Project Deployment Models

## Status

Proposed

## Context

Ringmaster manages multiple projects with different deployment pipelines:

- **Ringmaster itself**: Hot-reload, no external CI
- **Web apps**: GitHub Actions → Vercel/Netlify
- **Backend services**: GitHub → Docker → Kubernetes
- **Libraries**: GitHub → PyPI/npm publish
- **Local projects**: No deployment, just file changes

The self-improvement loop (ADR-017) assumes ringmaster controls the full cycle. For external projects, ringmaster must integrate with existing pipelines rather than replace them.

## Decision

### 1. Project Deployment Configuration

Each project specifies its deployment model:

```python
class DeploymentModel(str, Enum):
    """How a project gets deployed after changes."""

    NONE = "none"              # Local dev, no deployment
    HOT_RELOAD = "hot_reload"  # Ringmaster self-improvement
    CI_CD = "ci_cd"            # Push triggers external CI/CD
    GITOPS = "gitops"          # ArgoCD/Flux watches repo
    MANUAL = "manual"          # Human deploys manually
    WEBHOOK = "webhook"        # Ringmaster calls deployment webhook


@dataclass
class ProjectDeployment:
    """Deployment configuration for a project."""

    model: DeploymentModel

    # CI/CD settings
    ci_provider: str | None = None  # github, gitlab, circleci
    ci_required_checks: list[str] = field(default_factory=list)
    auto_merge: bool = False  # Merge PR when checks pass

    # GitOps settings
    gitops_app: str | None = None  # ArgoCD app name
    gitops_namespace: str | None = None

    # Webhook settings
    deploy_webhook: str | None = None
    rollback_webhook: str | None = None

    # Branch strategy
    default_branch: str = "main"
    use_prs: bool = True  # Create PRs vs direct push
    require_approval: bool = True  # Human must approve PR
```

### 2. Task Completion Flow by Model

#### Model: NONE (Local Development)

```
Worker completes → Commit → Task DONE

No push, no deployment. Developer sees changes in their working directory.
Useful for: Local experiments, drafts, exploration tasks.
```

#### Model: HOT_RELOAD (Ringmaster Self-Improvement)

```
Worker completes → Commit → Merge → Hot-reload → Health check → Task DONE
                                          ↓
                                   Rollback on failure

Full loop as defined in ADR-017.
Only used for: ringmaster improving itself.
```

#### Model: CI_CD (GitHub Actions, GitLab CI, etc.)

```
Worker completes
    → Commit
    → Push branch
    → Create PR (if use_prs=True)
    → Wait for CI checks
    → If checks pass AND auto_merge=True:
        → Merge PR → Task DONE
    → If checks pass AND auto_merge=False:
        → Task REVIEW (wait for human)
    → If checks fail:
        → Task FAILED (with CI output)
```

**Implementation:**

```python
async def handle_ci_cd_completion(
    task: Task,
    project: Project,
    worktree: Path,
):
    """Handle task completion for CI/CD projects."""
    config = project.deployment

    # Push branch
    branch = f"ringmaster/{task.id[:8]}"
    await push_branch(worktree, branch)

    # Create PR if configured
    if config.use_prs:
        pr = await create_pull_request(
            repo=project.repo_url,
            branch=branch,
            title=task.title,
            body=format_pr_body(task),
        )
        task.metadata["pr_url"] = pr.url
        task.metadata["pr_number"] = pr.number

    # Watch CI status
    task.status = TaskStatus.REVIEW
    await save_task(task)

    # Start background watcher
    await start_ci_watcher(task, project, pr.number if config.use_prs else branch)


async def ci_status_callback(task: Task, project: Project, status: CIStatus):
    """Called when CI status changes."""
    config = project.deployment

    if status.state == "success":
        if config.auto_merge and all_checks_passed(status, config.ci_required_checks):
            await merge_pr(project.repo_url, task.metadata["pr_number"])
            task.status = TaskStatus.DONE
        else:
            # Keep in REVIEW for human approval
            await notify_human(task, "CI passed, awaiting approval")

    elif status.state == "failure":
        task.status = TaskStatus.FAILED
        task.failure_reason = format_ci_failures(status)

    await save_task(task)
```

#### Model: GITOPS (ArgoCD, Flux)

```
Worker completes
    → Commit
    → Push to default branch (or merge PR)
    → ArgoCD detects change
    → ArgoCD syncs application
    → Ringmaster monitors ArgoCD status
    → Healthy → Task DONE
    → Degraded → Task FAILED (trigger rollback?)
```

**Implementation:**

```python
async def handle_gitops_completion(
    task: Task,
    project: Project,
    worktree: Path,
):
    """Handle task completion for GitOps projects."""
    config = project.deployment

    # Push changes (direct or via PR)
    if config.use_prs:
        # Same PR flow as CI/CD, but deployment happens via GitOps
        await handle_ci_cd_completion(task, project, worktree)
    else:
        # Direct push triggers GitOps sync
        await push_to_default_branch(worktree, config.default_branch)

    # Monitor ArgoCD application status
    task.status = TaskStatus.REVIEW
    await save_task(task)

    await start_gitops_watcher(
        task,
        app_name=config.gitops_app,
        namespace=config.gitops_namespace,
    )


async def gitops_status_callback(task: Task, status: ArgoStatus):
    """Called when ArgoCD application status changes."""
    if status.health == "Healthy" and status.sync == "Synced":
        task.status = TaskStatus.DONE
    elif status.health == "Degraded":
        task.status = TaskStatus.FAILED
        task.failure_reason = f"Deployment degraded: {status.message}"
        # Optionally trigger rollback
    # else: still syncing, keep watching

    await save_task(task)
```

#### Model: MANUAL

```
Worker completes
    → Commit
    → Push branch
    → Create PR
    → Task REVIEW
    → Human merges and deploys manually
    → Human marks task DONE in UI
```

#### Model: WEBHOOK

```
Worker completes
    → Commit
    → Push
    → POST to deploy_webhook with payload
    → Monitor response / callback
    → Success → Task DONE
    → Failure → POST to rollback_webhook
```

### 3. Rollback Strategies by Model

| Model | Rollback Trigger | Rollback Action |
|-------|------------------|-----------------|
| NONE | N/A | `git checkout` locally |
| HOT_RELOAD | Health check fails | `git revert` + reload |
| CI_CD | CI fails | Close PR, no merge happens |
| GITOPS | App degraded | Push revert commit, ArgoCD syncs |
| MANUAL | Human decides | Human reverts manually |
| WEBHOOK | Deploy fails | Call rollback_webhook |

### 4. Status Observation

Ringmaster needs to observe external systems:

```python
class DeploymentObserver:
    """Watches external deployment systems for status changes."""

    async def watch_github_checks(self, repo: str, ref: str, callback):
        """Poll GitHub API for check status."""
        while True:
            status = await github_api.get_combined_status(repo, ref)
            await callback(status)
            if status.state in ("success", "failure", "error"):
                break
            await asyncio.sleep(30)

    async def watch_argocd_app(self, app_name: str, callback):
        """Poll ArgoCD API for application health."""
        while True:
            status = await argocd_api.get_application(app_name)
            await callback(status)
            if status.health in ("Healthy", "Degraded"):
                break
            await asyncio.sleep(15)

    async def watch_webhook_status(self, task_id: str, callback):
        """Wait for webhook callback from deployment system."""
        # Register callback endpoint
        # Deployment system POSTs status back
        pass
```

### 5. Project Configuration Schema

Add to project settings:

```yaml
# Project: my-web-app
deployment:
  model: ci_cd
  ci_provider: github
  ci_required_checks:
    - build
    - test
    - lint
  auto_merge: false
  use_prs: true
  require_approval: true
  default_branch: main

# Project: my-k8s-service
deployment:
  model: gitops
  gitops_app: my-k8s-service
  gitops_namespace: production
  use_prs: true
  require_approval: true

# Project: ringmaster (self)
deployment:
  model: hot_reload
  use_prs: false
  require_approval: false  # Tests are the approval
```

### 6. Database Schema

```sql
-- Add to projects table
ALTER TABLE projects ADD COLUMN deployment_model TEXT DEFAULT 'none';
ALTER TABLE projects ADD COLUMN deployment_config TEXT;  -- JSON

-- Track deployment status per task
CREATE TABLE deployments (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(id),
    project_id TEXT NOT NULL REFERENCES projects(id),
    model TEXT NOT NULL,
    status TEXT NOT NULL,  -- pending, in_progress, success, failed, rolled_back
    pr_url TEXT,
    pr_number INTEGER,
    ci_status TEXT,  -- JSON
    gitops_status TEXT,  -- JSON
    started_at TEXT NOT NULL,
    completed_at TEXT,
    error_message TEXT
);
```

## Consequences

### Positive

- Works with existing project pipelines (no forcing new workflows)
- Flexible: from no deployment to full GitOps
- Rollback strategy per model
- Observability into external systems

### Negative

- Complexity of supporting multiple models
- Need API integrations (GitHub, ArgoCD, etc.)
- Polling external systems adds latency
- Different failure modes per model

### Trade-offs

| Approach | Pros | Cons |
|----------|------|------|
| Ringmaster controls deployment | Consistent behavior | Ignores existing pipelines |
| **Integrate with existing pipelines** | Works with what teams have | More integration work |
| Only handle code changes | Simple | No visibility into deployment |

We chose integration because teams already have deployment pipelines they trust.

## Implementation Priority

1. **NONE model** - Already works (just commit)
2. **CI_CD model** - Most common, GitHub API integration
3. **GITOPS model** - For K8s projects, ArgoCD integration
4. **HOT_RELOAD model** - Ringmaster self-improvement (ADR-017)
5. **WEBHOOK model** - Generic integration point
6. **MANUAL model** - Fallback, minimal implementation

## References

- ADR-017: Self-Improvement Loop Integration
- ADR-016: Resource Cleanup
- GitHub Status API: https://docs.github.com/en/rest/commits/statuses
- ArgoCD API: https://argo-cd.readthedocs.io/en/stable/developer-guide/api-docs/
