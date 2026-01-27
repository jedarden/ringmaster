"""Deployment context extraction for task enrichment.

Based on docs/04-context-enrichment.md, Section 5:
- Environment configs (.env, docker-compose, helm values)
- K8s manifests with secret name redaction
- CI/CD pipeline status
- Infrastructure state
"""

import json
import logging
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml

logger = logging.getLogger(__name__)

# File patterns for deployment configs
ENV_FILE_PATTERNS = {
    ".env",
    ".env.example",
    ".env.local",
    ".env.development",
    ".env.production",
    ".env.test",
}

COMPOSE_FILE_PATTERNS = {
    "docker-compose.yml",
    "docker-compose.yaml",
    "docker-compose.override.yml",
    "docker-compose.dev.yml",
    "docker-compose.prod.yml",
    "compose.yml",
    "compose.yaml",
}

HELM_FILE_PATTERNS = {
    "values.yaml",
    "values.yml",
    "values-dev.yaml",
    "values-prod.yaml",
    "values-staging.yaml",
}

K8S_FILE_PATTERNS = {
    "*.yaml",
    "*.yml",
}

K8S_DIRECTORIES = {
    "k8s",
    "kubernetes",
    "manifests",
    "deploy",
    "deployment",
    "deployments",
    "charts",
    "helm",
}

CI_CD_DIRECTORIES = {
    ".github/workflows",
    ".gitlab-ci.yml",
    ".circleci",
    "Jenkinsfile",
    ".azure-pipelines",
}

# Patterns that indicate sensitive values to redact
SECRET_PATTERNS = [
    r"password",
    r"secret",
    r"api[_-]?key",
    r"access[_-]?key",
    r"private[_-]?key",
    r"token",
    r"credential",
    r"auth",
    r"bearer",
    r"jwt",
    r"connection[_-]?string",
    r"database[_-]?url",
]


@dataclass
class DeploymentFile:
    """A deployment-related file."""

    path: Path
    content: str
    file_type: Literal["env", "compose", "k8s", "helm", "cicd", "other"]
    relevance_score: float
    redacted: bool = False


@dataclass
class CICDStatus:
    """Status of a CI/CD pipeline run."""

    workflow_name: str
    status: Literal["success", "failure", "pending", "cancelled", "unknown"]
    branch: str
    run_url: str | None = None
    conclusion: str | None = None
    started_at: str | None = None


@dataclass
class DeploymentContextResult:
    """Result of deployment context extraction."""

    files: list[DeploymentFile] = field(default_factory=list)
    cicd_runs: list[CICDStatus] = field(default_factory=list)
    total_tokens: int = 0
    truncated: bool = False


class DeploymentContextExtractor:
    """Extracts deployment and infrastructure context for a task.

    The extractor finds:
    1. Environment configs - .env files with secret redaction
    2. Docker Compose - service definitions
    3. Kubernetes manifests - deployments, services, configmaps
    4. Helm charts - values files
    5. CI/CD configs - workflow definitions and status
    """

    def __init__(
        self,
        project_dir: Path,
        max_tokens: int = 3000,
        max_files: int = 8,
        redact_secrets: bool = True,
        include_cicd_status: bool = True,
    ):
        self.project_dir = project_dir
        self.max_tokens = max_tokens
        self.max_files = max_files
        self.redact_secrets = redact_secrets
        self.include_cicd_status = include_cicd_status
        self._secret_pattern = re.compile(
            "|".join(SECRET_PATTERNS), re.IGNORECASE
        )

    def extract(self, task_description: str) -> DeploymentContextResult:
        """Extract deployment context relevant to the task.

        Args:
            task_description: Task description to check for deployment keywords.

        Returns:
            DeploymentContextResult with relevant deployment files.
        """
        result = DeploymentContextResult()

        # Check if task is deployment-related
        relevance = self._calculate_task_relevance(task_description)
        if relevance < 0.3:
            logger.debug("Task doesn't appear deployment-related (score: %.2f)", relevance)
            return result

        # Collect deployment files
        self._collect_env_files(result)
        self._collect_compose_files(result)
        self._collect_k8s_manifests(result)
        self._collect_helm_values(result)
        self._collect_cicd_configs(result)

        # Get CI/CD status if available
        if self.include_cicd_status:
            self._get_cicd_status(result)

        # Apply relevance scoring based on task keywords
        keywords = self._extract_deployment_keywords(task_description)
        for df in result.files:
            score = self._score_file_relevance(df, keywords, task_description)
            df.relevance_score = score

        # Sort by relevance and apply budget
        result.files.sort(key=lambda f: f.relevance_score, reverse=True)
        result = self._apply_token_budget(result)

        return result

    def _calculate_task_relevance(self, task_description: str) -> float:
        """Calculate how deployment-related the task is."""
        task_lower = task_description.lower()

        # Strong signals
        strong_keywords = [
            "deploy", "deployment", "kubernetes", "k8s",
            "docker", "container", "environment", "env var",
            "config", "infrastructure", "infra", "ci/cd",
            "pipeline", "helm", "manifest", "yaml",
            "production", "staging", "cluster",
        ]

        # Medium signals
        medium_keywords = [
            "environment", "settings", "configuration",
            "secret", "variable", "service", "port",
            "replica", "scale", "pod", "node",
        ]

        score = 0.0
        for kw in strong_keywords:
            if kw in task_lower:
                score += 0.15

        for kw in medium_keywords:
            if kw in task_lower:
                score += 0.08

        return min(score, 1.0)

    def _extract_deployment_keywords(self, task_description: str) -> list[str]:
        """Extract deployment-specific keywords from task."""
        keywords = []
        task_lower = task_description.lower()

        # Service names
        service_pattern = r"\b([a-z][a-z0-9-]+(?:[-_]service)?)\b"
        for match in re.finditer(service_pattern, task_lower):
            word = match.group(1)
            if len(word) > 3:
                keywords.append(word)

        # Resource names
        resource_pattern = r"\b(deployment|service|configmap|secret|ingress|pod|container)\b"
        for match in re.finditer(resource_pattern, task_lower, re.IGNORECASE):
            keywords.append(match.group(1).lower())

        return list(set(keywords))[:10]

    def _collect_env_files(self, result: DeploymentContextResult) -> None:
        """Collect environment configuration files."""
        for pattern in ENV_FILE_PATTERNS:
            for path in self.project_dir.glob(pattern):
                if path.is_file():
                    content = self._read_and_redact_env_file(path)
                    if content:
                        result.files.append(DeploymentFile(
                            path=path,
                            content=content,
                            file_type="env",
                            relevance_score=0.5,
                            redacted=self.redact_secrets,
                        ))

    def _collect_compose_files(self, result: DeploymentContextResult) -> None:
        """Collect Docker Compose files."""
        for pattern in COMPOSE_FILE_PATTERNS:
            for path in self.project_dir.glob(pattern):
                if path.is_file():
                    content = self._read_and_redact_yaml(path)
                    if content:
                        result.files.append(DeploymentFile(
                            path=path,
                            content=content,
                            file_type="compose",
                            relevance_score=0.6,
                            redacted=self.redact_secrets,
                        ))

    def _collect_k8s_manifests(self, result: DeploymentContextResult) -> None:
        """Collect Kubernetes manifest files."""
        for dir_name in K8S_DIRECTORIES:
            k8s_dir = self.project_dir / dir_name
            if k8s_dir.is_dir():
                for path in k8s_dir.rglob("*.yaml"):
                    if self._is_k8s_manifest(path):
                        content = self._read_and_redact_yaml(path)
                        if content:
                            result.files.append(DeploymentFile(
                                path=path,
                                content=content,
                                file_type="k8s",
                                relevance_score=0.6,
                                redacted=self.redact_secrets,
                            ))
                for path in k8s_dir.rglob("*.yml"):
                    if self._is_k8s_manifest(path):
                        content = self._read_and_redact_yaml(path)
                        if content:
                            result.files.append(DeploymentFile(
                                path=path,
                                content=content,
                                file_type="k8s",
                                relevance_score=0.6,
                                redacted=self.redact_secrets,
                            ))

    def _collect_helm_values(self, result: DeploymentContextResult) -> None:
        """Collect Helm values files."""
        # Look in helm/ and charts/ directories
        for dir_name in ["helm", "charts"]:
            helm_dir = self.project_dir / dir_name
            if helm_dir.is_dir():
                for pattern in HELM_FILE_PATTERNS:
                    for path in helm_dir.rglob(pattern):
                        if path.is_file():
                            content = self._read_and_redact_yaml(path)
                            if content:
                                result.files.append(DeploymentFile(
                                    path=path,
                                    content=content,
                                    file_type="helm",
                                    relevance_score=0.55,
                                    redacted=self.redact_secrets,
                                ))

        # Also check root for values.yaml
        for pattern in HELM_FILE_PATTERNS:
            for path in self.project_dir.glob(pattern):
                if path.is_file():
                    content = self._read_and_redact_yaml(path)
                    if content:
                        result.files.append(DeploymentFile(
                            path=path,
                            content=content,
                            file_type="helm",
                            relevance_score=0.55,
                            redacted=self.redact_secrets,
                        ))

    def _collect_cicd_configs(self, result: DeploymentContextResult) -> None:
        """Collect CI/CD configuration files."""
        # GitHub Actions
        gh_workflows = self.project_dir / ".github" / "workflows"
        if gh_workflows.is_dir():
            for path in gh_workflows.glob("*.yml"):
                content = self._read_file(path)
                if content:
                    result.files.append(DeploymentFile(
                        path=path,
                        content=content,
                        file_type="cicd",
                        relevance_score=0.5,
                        redacted=False,
                    ))
            for path in gh_workflows.glob("*.yaml"):
                content = self._read_file(path)
                if content:
                    result.files.append(DeploymentFile(
                        path=path,
                        content=content,
                        file_type="cicd",
                        relevance_score=0.5,
                        redacted=False,
                    ))

        # GitLab CI
        gitlab_ci = self.project_dir / ".gitlab-ci.yml"
        if gitlab_ci.is_file():
            content = self._read_file(gitlab_ci)
            if content:
                result.files.append(DeploymentFile(
                    path=gitlab_ci,
                    content=content,
                    file_type="cicd",
                    relevance_score=0.5,
                    redacted=False,
                ))

    def _get_cicd_status(self, result: DeploymentContextResult) -> None:
        """Get recent CI/CD run status from GitHub Actions."""
        try:
            # Check if gh CLI is available
            gh_check = subprocess.run(
                ["gh", "--version"],
                capture_output=True,
                timeout=5,
                cwd=self.project_dir,
            )
            if gh_check.returncode != 0:
                return

            # Get recent workflow runs
            proc = subprocess.run(
                [
                    "gh", "run", "list",
                    "--limit", "5",
                    "--json", "name,status,conclusion,headBranch,url,createdAt",
                ],
                capture_output=True,
                text=True,
                timeout=15,
                cwd=self.project_dir,
            )

            if proc.returncode != 0:
                logger.debug("Failed to get CI/CD status: %s", proc.stderr)
                return

            runs = json.loads(proc.stdout)
            for run in runs:
                status = "unknown"
                if run.get("status") == "completed":
                    conclusion = run.get("conclusion", "unknown")
                    status = "success" if conclusion == "success" else "failure"
                elif run.get("status") in ("in_progress", "queued"):
                    status = "pending"

                result.cicd_runs.append(CICDStatus(
                    workflow_name=run.get("name", "Unknown"),
                    status=status,
                    branch=run.get("headBranch", "unknown"),
                    run_url=run.get("url"),
                    conclusion=run.get("conclusion"),
                    started_at=run.get("createdAt"),
                ))

        except subprocess.TimeoutExpired:
            logger.debug("Timeout getting CI/CD status")
        except FileNotFoundError:
            logger.debug("gh CLI not found")
        except (json.JSONDecodeError, KeyError) as e:
            logger.debug("Failed to parse CI/CD status: %s", e)

    def _is_k8s_manifest(self, path: Path) -> bool:
        """Check if a YAML file is a Kubernetes manifest."""
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
            # Check for k8s kind declarations
            return "kind:" in content and "apiVersion:" in content
        except OSError:
            return False

    def _read_file(self, path: Path, max_lines: int = 200) -> str | None:
        """Read a file with line limit."""
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
            if len(lines) > max_lines:
                lines = lines[:max_lines]
                lines.append(f"... (truncated, {len(lines)} more lines)")
            return "\n".join(lines)
        except OSError as e:
            logger.warning("Failed to read %s: %s", path, e)
            return None

    def _read_and_redact_env_file(self, path: Path) -> str | None:
        """Read an env file and redact sensitive values."""
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
            redacted_lines = []

            for line in lines:
                # Skip empty lines and comments
                if not line.strip() or line.strip().startswith("#"):
                    redacted_lines.append(line)
                    continue

                # Parse KEY=value
                if "=" in line:
                    key, _, value = line.partition("=")
                    if self.redact_secrets and self._is_sensitive_key(key):
                        redacted_lines.append(f"{key}=<REDACTED>")
                    else:
                        redacted_lines.append(line)
                else:
                    redacted_lines.append(line)

            return "\n".join(redacted_lines)
        except OSError as e:
            logger.warning("Failed to read env file %s: %s", path, e)
            return None

    def _read_and_redact_yaml(self, path: Path) -> str | None:
        """Read a YAML file and redact sensitive values."""
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")

            if not self.redact_secrets:
                return content

            # Parse and redact YAML
            try:
                # Handle multi-document YAML
                docs = list(yaml.safe_load_all(content))
                redacted_docs = [self._redact_yaml_doc(doc) for doc in docs]
                return yaml.dump_all(redacted_docs, default_flow_style=False)
            except yaml.YAMLError:
                # Fall back to line-by-line redaction
                return self._redact_yaml_lines(content)

        except OSError as e:
            logger.warning("Failed to read YAML %s: %s", path, e)
            return None

    def _redact_yaml_doc(self, doc: dict | list | None) -> dict | list | None:
        """Recursively redact sensitive values in a YAML document."""
        if doc is None:
            return None

        if isinstance(doc, dict):
            result = {}
            for key, value in doc.items():
                if self._is_sensitive_key(str(key)) and isinstance(value, str):
                    result[key] = "<REDACTED>"
                elif isinstance(value, (dict, list)):
                    result[key] = self._redact_yaml_doc(value)
                else:
                    result[key] = value
            return result

        if isinstance(doc, list):
            return [self._redact_yaml_doc(item) for item in doc]

        return doc

    def _redact_yaml_lines(self, content: str) -> str:
        """Simple line-by-line YAML redaction."""
        lines = content.splitlines()
        redacted = []

        for line in lines:
            # Check for key: value patterns
            match = re.match(r'^(\s*)(\S+):\s*(.+)$', line)
            if match:
                indent, key, value = match.groups()
                if self._is_sensitive_key(key) and not value.startswith("|") and not value.startswith(">"):
                    redacted.append(f"{indent}{key}: <REDACTED>")
                    continue
            redacted.append(line)

        return "\n".join(redacted)

    def _is_sensitive_key(self, key: str) -> bool:
        """Check if a key name indicates sensitive data."""
        return bool(self._secret_pattern.search(key))

    def _score_file_relevance(
        self,
        df: DeploymentFile,
        keywords: list[str],
        task_description: str,
    ) -> float:
        """Score file relevance based on task keywords."""
        score = df.relevance_score

        # Boost for keyword matches in path
        path_str = str(df.path).lower()
        for keyword in keywords:
            if keyword in path_str:
                score += 0.15

        # Boost for content matches
        content_lower = df.content.lower()
        for keyword in keywords:
            if keyword in content_lower:
                score += 0.1

        # Boost for file type based on task
        task_lower = task_description.lower()
        if df.file_type == "k8s" and any(kw in task_lower for kw in ["k8s", "kubernetes", "pod", "deployment"]):
            score += 0.2
        if df.file_type == "compose" and any(kw in task_lower for kw in ["docker", "compose", "container"]):
            score += 0.2
        if df.file_type == "env" and any(kw in task_lower for kw in ["env", "environment", "config"]):
            score += 0.2
        if df.file_type == "cicd" and any(kw in task_lower for kw in ["ci", "cd", "pipeline", "workflow", "build"]):
            score += 0.2

        return min(score, 1.0)

    def _apply_token_budget(self, result: DeploymentContextResult) -> DeploymentContextResult:
        """Apply token budget and file limit to deployment context."""
        # First apply max_files limit
        if len(result.files) > self.max_files:
            result.files = result.files[:self.max_files]
            result.truncated = True

        # Calculate total tokens
        total_tokens = 0
        for df in result.files:
            df_tokens = len(df.content) // 4
            total_tokens += df_tokens

        # If within budget, we're done
        if total_tokens <= self.max_tokens:
            result.total_tokens = total_tokens
            return result

        # Truncate to fit token budget
        new_files = []
        tokens_used = 0

        for df in result.files:
            file_tokens = len(df.content) // 4
            if tokens_used + file_tokens <= self.max_tokens:
                new_files.append(df)
                tokens_used += file_tokens
            else:
                result.truncated = True
                break

        result.files = new_files
        result.total_tokens = tokens_used
        return result


def format_deployment_context(result: DeploymentContextResult, project_dir: Path) -> str:
    """Format deployment context for prompt inclusion."""
    if not result.files and not result.cicd_runs:
        return ""

    parts = ["## Deployment Context", ""]

    # Files
    for df in result.files:
        try:
            rel_path = df.path.relative_to(project_dir)
        except ValueError:
            rel_path = df.path

        file_type_label = {
            "env": "Environment",
            "compose": "Docker Compose",
            "k8s": "Kubernetes",
            "helm": "Helm Values",
            "cicd": "CI/CD Config",
            "other": "Config",
        }.get(df.file_type, "Config")

        parts.append(f"### {rel_path} ({file_type_label})")
        if df.redacted:
            parts.append("_Sensitive values redacted_")

        # Determine syntax highlight
        syntax = "yaml"
        if df.file_type == "env":
            syntax = "bash"

        parts.append(f"```{syntax}")
        parts.append(df.content)
        parts.append("```")
        parts.append("")

    # CI/CD Status
    if result.cicd_runs:
        parts.append("### Recent CI/CD Runs")
        parts.append("")
        for run in result.cicd_runs:
            status_emoji = {
                "success": "✓",
                "failure": "✗",
                "pending": "○",
                "cancelled": "⊘",
                "unknown": "?",
            }.get(run.status, "?")
            parts.append(f"- {status_emoji} **{run.workflow_name}** ({run.branch}): {run.status}")
        parts.append("")

    if result.truncated:
        parts.append("_(Some files omitted due to context limits)_")
        parts.append("")

    return "\n".join(parts)
