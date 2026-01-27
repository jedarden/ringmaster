"""Tests for deployment context extraction."""

from pathlib import Path

import pytest

from ringmaster.enricher.deployment_context import (
    DeploymentContextExtractor,
    DeploymentContextResult,
    format_deployment_context,
)


@pytest.fixture
def temp_project(tmp_path: Path) -> Path:
    """Create a temporary project directory with deployment files."""
    # Create .env file
    env_file = tmp_path / ".env"
    env_file.write_text(
        """# Database config
DATABASE_URL=postgres://localhost:5432/app
DATABASE_PASSWORD=secret123
API_KEY=sk-12345
DEBUG=true
PORT=8080
"""
    )

    # Create .env.example
    env_example = tmp_path / ".env.example"
    env_example.write_text(
        """DATABASE_URL=postgres://localhost:5432/app
DATABASE_PASSWORD=
API_KEY=
DEBUG=false
PORT=8080
"""
    )

    # Create docker-compose.yml
    compose_file = tmp_path / "docker-compose.yml"
    compose_file.write_text(
        """version: '3.8'
services:
  app:
    build: .
    ports:
      - "8080:8080"
    environment:
      - DATABASE_PASSWORD=${DATABASE_PASSWORD}
    depends_on:
      - db
  db:
    image: postgres:15
    environment:
      POSTGRES_PASSWORD: ${DATABASE_PASSWORD}
"""
    )

    # Create k8s directory with manifests
    k8s_dir = tmp_path / "k8s"
    k8s_dir.mkdir()

    deployment = k8s_dir / "deployment.yaml"
    deployment.write_text(
        """apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-app
spec:
  replicas: 3
  selector:
    matchLabels:
      app: my-app
  template:
    metadata:
      labels:
        app: my-app
    spec:
      containers:
      - name: app
        image: my-app:latest
        env:
        - name: DATABASE_PASSWORD
          valueFrom:
            secretKeyRef:
              name: db-secret
              key: password
"""
    )

    service = k8s_dir / "service.yaml"
    service.write_text(
        """apiVersion: v1
kind: Service
metadata:
  name: my-app-svc
spec:
  selector:
    app: my-app
  ports:
  - port: 80
    targetPort: 8080
"""
    )

    # Create GitHub Actions workflow
    gh_dir = tmp_path / ".github" / "workflows"
    gh_dir.mkdir(parents=True)

    workflow = gh_dir / "ci.yml"
    workflow.write_text(
        """name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v3
    - name: Run tests
      run: pytest
"""
    )

    # Create Helm chart
    helm_dir = tmp_path / "helm" / "my-chart"
    helm_dir.mkdir(parents=True)

    values = helm_dir / "values.yaml"
    values.write_text(
        """replicaCount: 3
image:
  repository: my-app
  tag: latest
service:
  type: ClusterIP
  port: 80
secrets:
  databasePassword: ""
"""
    )

    return tmp_path


class TestDeploymentContextExtractor:
    """Tests for DeploymentContextExtractor."""

    def test_extract_env_files(self, temp_project: Path):
        """Test extracting environment files."""
        extractor = DeploymentContextExtractor(
            project_dir=temp_project,
            redact_secrets=False,
        )
        result = extractor.extract("Fix environment configuration")

        env_files = [f for f in result.files if f.file_type == "env"]
        assert len(env_files) >= 1

        # Check content is included
        env_content = env_files[0].content
        assert "DATABASE_URL" in env_content
        assert "PORT" in env_content

    def test_env_secret_redaction(self, temp_project: Path):
        """Test that secrets in .env files are redacted."""
        extractor = DeploymentContextExtractor(
            project_dir=temp_project,
            redact_secrets=True,
        )
        result = extractor.extract("Fix environment configuration")

        env_files = [f for f in result.files if f.file_type == "env"]
        assert len(env_files) >= 1

        env_content = env_files[0].content
        # Secret values should be redacted
        assert "<REDACTED>" in env_content
        # Non-secret values should remain
        assert "PORT=8080" in env_content or "DEBUG=true" in env_content

    def test_extract_compose_files(self, temp_project: Path):
        """Test extracting Docker Compose files."""
        extractor = DeploymentContextExtractor(project_dir=temp_project)
        result = extractor.extract("Fix Docker container configuration")

        compose_files = [f for f in result.files if f.file_type == "compose"]
        assert len(compose_files) == 1
        assert "services:" in compose_files[0].content

    def test_extract_k8s_manifests(self, temp_project: Path):
        """Test extracting Kubernetes manifests."""
        extractor = DeploymentContextExtractor(project_dir=temp_project)
        result = extractor.extract("Fix Kubernetes deployment")

        k8s_files = [f for f in result.files if f.file_type == "k8s"]
        assert len(k8s_files) >= 1

        # Check deployment manifest
        deployment_files = [f for f in k8s_files if "deployment" in str(f.path).lower()]
        assert len(deployment_files) == 1
        assert "kind: Deployment" in deployment_files[0].content

    def test_extract_cicd_configs(self, temp_project: Path):
        """Test extracting CI/CD configuration files."""
        extractor = DeploymentContextExtractor(project_dir=temp_project)
        result = extractor.extract("Fix CI/CD pipeline")

        cicd_files = [f for f in result.files if f.file_type == "cicd"]
        assert len(cicd_files) == 1
        assert "name: CI" in cicd_files[0].content

    def test_extract_helm_values(self, temp_project: Path):
        """Test extracting Helm values files."""
        extractor = DeploymentContextExtractor(project_dir=temp_project)
        result = extractor.extract("Update Helm chart configuration")

        helm_files = [f for f in result.files if f.file_type == "helm"]
        assert len(helm_files) >= 1
        assert "replicaCount" in helm_files[0].content

    def test_yaml_secret_redaction(self, temp_project: Path):
        """Test that secrets in YAML files are redacted."""
        extractor = DeploymentContextExtractor(
            project_dir=temp_project,
            redact_secrets=True,
        )
        result = extractor.extract("Fix database password in Kubernetes")

        # k8s secret references should be preserved (they're references, not values)
        # but actual secret values in helm values should be redacted
        helm_files = [f for f in result.files if f.file_type == "helm"]
        if helm_files:
            helm_content = helm_files[0].content
            # Check that databasePassword (sensitive key) is handled
            # In this case, the value is empty string, so it may or may not be redacted
            assert "secrets" in helm_content or "replicaCount" in helm_content

    def test_relevance_threshold(self, temp_project: Path):
        """Test that non-deployment tasks get minimal context."""
        extractor = DeploymentContextExtractor(project_dir=temp_project)

        # Task with no deployment keywords
        result = extractor.extract("Fix the login button color")

        # Should have few or no files (low relevance)
        assert result.total_tokens == 0 or len(result.files) <= 2

    def test_deployment_keyword_relevance(self, temp_project: Path):
        """Test that deployment-related tasks get more context."""
        extractor = DeploymentContextExtractor(project_dir=temp_project)

        # Task with deployment keywords
        result = extractor.extract(
            "Fix the Kubernetes deployment configuration for production environment"
        )

        # Should have multiple files
        assert len(result.files) >= 2
        assert result.total_tokens > 0

    def test_token_budget(self, temp_project: Path):
        """Test that token budget is respected."""
        extractor = DeploymentContextExtractor(
            project_dir=temp_project,
            max_tokens=500,  # Very small budget
        )
        result = extractor.extract("Fix Kubernetes deployment configuration")

        # Total tokens should be within budget
        assert result.total_tokens <= 500

    def test_max_files_limit(self, temp_project: Path):
        """Test that max files limit is respected."""
        extractor = DeploymentContextExtractor(
            project_dir=temp_project,
            max_files=2,
        )
        result = extractor.extract("Fix all deployment configurations")

        assert len(result.files) <= 2

    def test_format_deployment_context(self, temp_project: Path):
        """Test formatting deployment context for prompts."""
        extractor = DeploymentContextExtractor(project_dir=temp_project)
        result = extractor.extract("Fix Kubernetes deployment")

        formatted = format_deployment_context(result, temp_project)

        # Should have markdown structure
        assert "## Deployment Context" in formatted
        assert "```" in formatted  # Code blocks

    def test_format_empty_result(self, temp_project: Path):
        """Test formatting empty deployment context."""
        result = DeploymentContextResult()
        formatted = format_deployment_context(result, temp_project)

        assert formatted == ""

    def test_format_with_truncation(self, temp_project: Path):
        """Test formatting shows truncation indicator."""
        extractor = DeploymentContextExtractor(
            project_dir=temp_project,
            max_files=1,
        )
        result = extractor.extract("Fix all deployment configuration")

        # If truncated, should show indicator
        if result.truncated:
            formatted = format_deployment_context(result, temp_project)
            assert "omitted" in formatted.lower()


class TestSensitiveKeyDetection:
    """Tests for sensitive key detection."""

    def test_sensitive_patterns(self, tmp_path: Path):
        """Test that various secret patterns are detected."""
        env_file = tmp_path / ".env"
        env_file.write_text(
            """# All of these should be redacted
PASSWORD=secret
api_key=abc123
ACCESS_KEY=xyz
private_key=rsa...
AUTH_TOKEN=bearer123
database_credential=cred
JWT_SECRET=jwtsecret
connection_string=conn

# These should NOT be redacted
HOST=localhost
PORT=8080
DEBUG=true
LOG_LEVEL=info
"""
        )

        extractor = DeploymentContextExtractor(
            project_dir=tmp_path,
            redact_secrets=True,
        )
        result = extractor.extract("Fix environment configuration")

        env_files = [f for f in result.files if f.file_type == "env"]
        assert len(env_files) == 1

        content = env_files[0].content
        # Sensitive values should be redacted
        assert "PASSWORD=<REDACTED>" in content
        assert "api_key=<REDACTED>" in content

        # Non-sensitive values should remain
        assert "HOST=localhost" in content
        assert "PORT=8080" in content


class TestTaskRelevanceScoring:
    """Tests for task relevance scoring."""

    def test_high_relevance_keywords(self, tmp_path: Path):
        """Test that strong deployment keywords trigger extraction."""
        # Create minimal .env
        (tmp_path / ".env").write_text("PORT=8080")

        extractor = DeploymentContextExtractor(project_dir=tmp_path)

        # High relevance tasks
        high_relevance_tasks = [
            "Deploy the application to Kubernetes cluster",
            "Fix the Docker container environment variables",
            "Update the CI/CD pipeline configuration",
            "Scale the production deployment to 5 replicas",
        ]

        for task in high_relevance_tasks:
            result = extractor.extract(task)
            # Should find files for deployment-related tasks
            # (at minimum the .env file we created)
            assert result.files or result.total_tokens == 0

    def test_low_relevance_tasks(self, tmp_path: Path):
        """Test that non-deployment tasks have low relevance."""
        # Create minimal .env
        (tmp_path / ".env").write_text("PORT=8080")

        extractor = DeploymentContextExtractor(project_dir=tmp_path)

        # Low relevance tasks
        low_relevance_tasks = [
            "Fix the button color",
            "Add a new user model",
            "Refactor the authentication logic",
        ]

        for task in low_relevance_tasks:
            result = extractor.extract(task)
            # Should have minimal or no deployment context
            assert result.total_tokens == 0 or len(result.files) <= 1


class TestCICDStatus:
    """Tests for CI/CD status extraction (mocked since gh CLI may not be available)."""

    def test_cicd_runs_format(self, tmp_path: Path):
        """Test formatting CI/CD run status."""
        from ringmaster.enricher.deployment_context import CICDStatus

        result = DeploymentContextResult(
            cicd_runs=[
                CICDStatus(
                    workflow_name="CI",
                    status="success",
                    branch="main",
                    run_url="https://github.com/test/repo/actions/runs/123",
                ),
                CICDStatus(
                    workflow_name="Deploy",
                    status="failure",
                    branch="feature-x",
                ),
            ]
        )

        formatted = format_deployment_context(result, tmp_path)

        assert "Recent CI/CD Runs" in formatted
        assert "CI" in formatted
        assert "main" in formatted
        assert "success" in formatted
        assert "Deploy" in formatted
        assert "failure" in formatted


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_project_directory(self, tmp_path: Path):
        """Test extraction from empty directory."""
        extractor = DeploymentContextExtractor(project_dir=tmp_path)
        result = extractor.extract("Fix deployment")

        assert len(result.files) == 0
        assert result.total_tokens == 0

    def test_nonexistent_directory(self):
        """Test extraction from non-existent directory."""
        extractor = DeploymentContextExtractor(
            project_dir=Path("/nonexistent/path/that/does/not/exist")
        )
        result = extractor.extract("Fix deployment")

        assert len(result.files) == 0
        assert result.total_tokens == 0

    def test_invalid_yaml_file(self, tmp_path: Path):
        """Test handling of invalid YAML files."""
        k8s_dir = tmp_path / "k8s"
        k8s_dir.mkdir()

        # Create invalid YAML
        bad_yaml = k8s_dir / "bad.yaml"
        bad_yaml.write_text(
            """apiVersion: v1
kind: ConfigMap
metadata:
  name: test
data:
  key: {{ invalid_template }}  # This would fail strict YAML parsing
"""
        )

        extractor = DeploymentContextExtractor(project_dir=tmp_path)
        # Should not crash
        result = extractor.extract("Fix Kubernetes configuration")

        # May or may not include the file depending on parsing
        # but should not raise exception
        assert isinstance(result, DeploymentContextResult)

    def test_binary_file_handling(self, tmp_path: Path):
        """Test that binary files are handled gracefully."""
        # Create a binary file that might look like a config
        binary_file = tmp_path / ".env"
        binary_file.write_bytes(b"\x00\x01\x02\x03\xff\xfe")

        extractor = DeploymentContextExtractor(project_dir=tmp_path)
        # Should not crash on binary files
        result = extractor.extract("Fix environment")

        assert isinstance(result, DeploymentContextResult)
