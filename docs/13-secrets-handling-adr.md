# Secrets Handling Architecture Decision Record

## ADR-019: Comprehensive Secrets Management

**Status:** Proposed
**Context:** Workers need some secrets to operate (LLM API keys) but must not access or leak project secrets (database passwords, API tokens, cloud credentials).

---

## Problem Statement

```
┌─────────────────────────────────────────────────────────────────────┐
│  SECRETS RISK MATRIX                                                 │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  What could go wrong:                                                │
│                                                                      │
│  1. Worker embeds secret in generated code                          │
│     → Secret committed to git                                        │
│                                                                      │
│  2. Worker includes secret in prompt to LLM                          │
│     → Secret sent to external API                                    │
│                                                                      │
│  3. Worker logs secret to output                                     │
│     → Secret visible in UI, audit logs                               │
│                                                                      │
│  4. Worker exfiltrates secret via network                            │
│     → Secret sent to attacker-controlled endpoint                    │
│                                                                      │
│  5. Worker reads secret it shouldn't have access to                  │
│     → Privilege escalation                                           │
│                                                                      │
│  6. Self-improvement modifies secrets handling code                  │
│     → Security bypass                                                │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Decision

Implement a **multi-layer secrets architecture**:

1. **Secret Classification** - Categorize secrets by sensitivity and usage
2. **Runtime Injection** - Secrets injected at execution time, never in prompts
3. **Sandbox Isolation** - Workers run without access to secret storage
4. **Proxy Pattern** - Integration tests use secret-holding proxies
5. **Detection & Redaction** - Active scanning for secret leakage
6. **Audit Trail** - Log all secret access

---

## Layer 1: Secret Classification

### Secret Categories

```python
class SecretCategory(str, Enum):
    """Categories of secrets with different handling rules."""

    # Category 1: Ringmaster Operations
    RINGMASTER_RUNTIME = "ringmaster_runtime"
    # - LLM API keys (Claude, OpenAI)
    # - Ringmaster database credentials
    # - Internal service tokens
    # Handling: Injected into Ringmaster process, never exposed to workers

    # Category 2: Worker Runtime
    WORKER_RUNTIME = "worker_runtime"
    # - Worker's own LLM API key (if different from Ringmaster)
    # - Git credentials for pushing
    # - Package registry tokens (npm, PyPI)
    # Handling: Injected into worker environment, redacted from output

    # Category 3: Project Secrets
    PROJECT_SECRET = "project_secret"
    # - Database credentials
    # - External API keys (Stripe, AWS, etc.)
    # - OAuth client secrets
    # Handling: NEVER exposed to workers directly

    # Category 4: Test Secrets
    TEST_SECRET = "test_secret"
    # - Staging database credentials
    # - Sandbox API keys
    # - Test user credentials
    # Handling: Available only in integration test containers


@dataclass
class Secret:
    """A secret with metadata."""

    name: str                      # e.g., "DATABASE_URL"
    category: SecretCategory
    project_id: str | None         # None = global
    value_hash: str                # SHA-256 hash for detection
    patterns: list[str]            # Regex patterns to detect in output
    created_at: datetime
    last_accessed: datetime | None
    access_count: int = 0
```

### Secret Registry

```python
class SecretRegistry:
    """Central registry of secrets and their metadata (not values)."""

    def __init__(self, db: Database):
        self.db = db
        self._patterns: dict[str, list[re.Pattern]] = {}

    async def register(
        self,
        name: str,
        category: SecretCategory,
        value: str,
        project_id: str | None = None,
    ) -> Secret:
        """Register a secret (stores hash and patterns, not value)."""

        # Generate detection patterns
        patterns = self._generate_patterns(name, value)

        secret = Secret(
            name=name,
            category=category,
            project_id=project_id,
            value_hash=hashlib.sha256(value.encode()).hexdigest(),
            patterns=patterns,
            created_at=datetime.now(UTC),
            last_accessed=None,
        )

        await self.db.insert_secret_metadata(secret)

        # Cache patterns for fast detection
        self._patterns[secret.name] = [re.compile(p) for p in patterns]

        return secret

    def _generate_patterns(self, name: str, value: str) -> list[str]:
        """Generate regex patterns to detect this secret in output."""

        patterns = []

        # Exact value match (escaped)
        patterns.append(re.escape(value))

        # Common obfuscation attempts
        # Base64 encoded
        b64 = base64.b64encode(value.encode()).decode()
        patterns.append(re.escape(b64))

        # URL encoded
        url_encoded = urllib.parse.quote(value)
        if url_encoded != value:
            patterns.append(re.escape(url_encoded))

        # Partial exposure (first/last N chars)
        if len(value) > 10:
            patterns.append(re.escape(value[:8]) + r".{2,}" + re.escape(value[-4:]))

        return patterns
```

---

## Layer 2: Runtime Injection

### Worker Environment Setup

```python
class WorkerEnvironment:
    """Manages environment variables for worker execution."""

    # Secrets that workers NEVER receive
    BLOCKED_VARS = [
        "DATABASE_URL",
        "DATABASE_PASSWORD",
        "AWS_SECRET_ACCESS_KEY",
        "STRIPE_SECRET_KEY",
        "OAUTH_CLIENT_SECRET",
        # ... comprehensive list
    ]

    # Secrets workers CAN receive (for their operation)
    ALLOWED_WORKER_SECRETS = [
        "ANTHROPIC_API_KEY",      # For Claude Code
        "OPENAI_API_KEY",         # For other workers
        "GIT_CREDENTIALS",        # For git push
        "NPM_TOKEN",              # For package install
    ]

    async def prepare_environment(
        self,
        worker: Worker,
        project: Project,
    ) -> dict[str, str]:
        """Prepare sanitized environment for worker."""

        env = {}

        # Start with minimal base environment
        env["PATH"] = "/usr/local/bin:/usr/bin:/bin"
        env["HOME"] = str(Path.home())
        env["TERM"] = "xterm-256color"

        # Add allowed worker secrets from secure storage
        for secret_name in self.ALLOWED_WORKER_SECRETS:
            value = await self._get_secret(secret_name, worker.id)
            if value:
                env[secret_name] = value

        # Add worker-specific config
        env["RINGMASTER_WORKER_ID"] = worker.id
        env["RINGMASTER_PROJECT_ID"] = project.id

        # Explicitly remove any blocked secrets that might leak from parent
        for blocked in self.BLOCKED_VARS:
            env.pop(blocked, None)

        return env

    async def _get_secret(self, name: str, worker_id: str) -> str | None:
        """Get secret value from secure storage with audit logging."""

        # Fetch from secrets manager (Vault, K8s secrets, etc.)
        value = await secrets_manager.get(name)

        if value:
            await audit_logger.log(
                AuditEventType.SECRET_ACCESSED,
                actor=f"worker:{worker_id}",
                resource_type="secret",
                resource_id=name,
                details={"category": "worker_runtime"},
            )

        return value
```

### Prompt Sanitization

```python
class PromptSanitizer:
    """Ensures secrets never appear in prompts sent to LLMs."""

    def __init__(self, secret_registry: SecretRegistry):
        self.registry = secret_registry

    async def sanitize(self, prompt: str, project_id: str) -> SanitizedPrompt:
        """Remove any secrets from prompt before sending to LLM."""

        redactions = []
        sanitized = prompt

        # Check all registered secrets
        secrets = await self.registry.get_secrets_for_project(project_id)

        for secret in secrets:
            for pattern in self.registry.get_patterns(secret.name):
                matches = pattern.finditer(sanitized)
                for match in matches:
                    redactions.append(Redaction(
                        secret_name=secret.name,
                        start=match.start(),
                        end=match.end(),
                        original_length=len(match.group()),
                    ))

                    # Replace with placeholder
                    sanitized = pattern.sub(
                        f"[REDACTED:{secret.name}]",
                        sanitized
                    )

        if redactions:
            logger.warning(
                f"Redacted {len(redactions)} secret(s) from prompt: "
                f"{[r.secret_name for r in redactions]}"
            )

            # This is a security event - log it
            await audit_logger.log(
                AuditEventType.SECRET_REDACTED,
                actor="system",
                resource_type="prompt",
                resource_id=project_id,
                details={"redactions": [r.secret_name for r in redactions]},
            )

        return SanitizedPrompt(
            content=sanitized,
            redactions=redactions,
            was_modified=len(redactions) > 0,
        )
```

---

## Layer 3: Sandbox Isolation

### Container-Based Isolation

```yaml
# worker-container.yaml
apiVersion: v1
kind: Pod
metadata:
  name: ringmaster-worker
spec:
  securityContext:
    runAsNonRoot: true
    runAsUser: 1000
    fsGroup: 1000

  containers:
  - name: worker
    image: ringmaster-worker:latest

    securityContext:
      allowPrivilegeEscalation: false
      readOnlyRootFilesystem: true
      capabilities:
        drop: ["ALL"]

    env:
      # Only allowed secrets injected
      - name: ANTHROPIC_API_KEY
        valueFrom:
          secretKeyRef:
            name: worker-secrets
            key: anthropic-api-key

    volumeMounts:
      # Worktree mounted read-write
      - name: worktree
        mountPath: /workspace

      # Tmp for worker operations
      - name: tmp
        mountPath: /tmp

    # No access to host network, secrets volume, etc.
    # Network policy restricts egress to:
    # - LLM APIs (api.anthropic.com, api.openai.com)
    # - Package registries (registry.npmjs.org, pypi.org)
    # - Git hosts (github.com, gitlab.com)
```

### Network Policy

```yaml
# worker-network-policy.yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: worker-egress
spec:
  podSelector:
    matchLabels:
      app: ringmaster-worker
  policyTypes:
  - Egress
  egress:
  # Allow LLM APIs
  - to:
    - ipBlock:
        cidr: 0.0.0.0/0
    ports:
    - port: 443
      protocol: TCP
    # Restrict to known hosts via DNS policy
  # Allow DNS
  - to:
    - namespaceSelector: {}
      podSelector:
        matchLabels:
          k8s-app: kube-dns
    ports:
    - port: 53
      protocol: UDP
```

### Local (Non-K8s) Isolation

```python
class LocalSandbox:
    """Sandbox for local development without K8s."""

    def __init__(self):
        self.allowed_hosts = [
            "api.anthropic.com",
            "api.openai.com",
            "registry.npmjs.org",
            "pypi.org",
            "github.com",
            "gitlab.com",
        ]

    async def run_worker(
        self,
        command: list[str],
        env: dict[str, str],
        cwd: Path,
    ) -> subprocess.CompletedProcess:
        """Run worker with sandboxing."""

        # Use firejail or similar if available
        if shutil.which("firejail"):
            # Firejail provides network filtering, filesystem sandboxing
            wrapped_command = [
                "firejail",
                "--quiet",
                "--private-tmp",
                "--noroot",
                f"--whitelist={cwd}",
                "--net=none",  # No network (we'll proxy LLM calls)
                "--",
                *command,
            ]
        else:
            # Fallback: at least clean environment
            wrapped_command = command
            logger.warning("firejail not available, running without full sandbox")

        return await asyncio.create_subprocess_exec(
            *wrapped_command,
            env=env,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
```

---

## Layer 4: Proxy Pattern for Integration Tests

### Secret-Holding Proxy

When tests need real secrets (database, external APIs), workers don't get the secrets directly. Instead, they interact with a proxy that holds the secrets.

```
┌─────────────────────────────────────────────────────────────────────┐
│  INTEGRATION TEST ARCHITECTURE                                       │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  Worker (no secrets)                                                 │
│       │                                                              │
│       │ HTTP request to localhost:9300                              │
│       ▼                                                              │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │  SECRET PROXY (runs in trusted context)                         ││
│  │                                                                  ││
│  │  • Holds actual secrets                                         ││
│  │  • Validates request is from authorized worker                  ││
│  │  • Injects secrets into outgoing requests                       ││
│  │  • Strips secrets from responses                                ││
│  │                                                                  ││
│  │  Example:                                                        ││
│  │  Worker: POST /proxy/database {"query": "SELECT * FROM users"}  ││
│  │  Proxy:  Connects to real DB with secret credentials            ││
│  │  Proxy:  Returns results (no credentials exposed)               ││
│  │                                                                  ││
│  └─────────────────────────────────────────────────────────────────┘│
│       │                                                              │
│       │ Actual request with secrets                                 │
│       ▼                                                              │
│  External Service (Database, API, etc.)                              │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Proxy Implementation

```python
class SecretProxy:
    """Proxy that holds secrets and makes authenticated requests on behalf of workers."""

    def __init__(self, secrets: dict[str, str]):
        self.secrets = secrets
        self.app = FastAPI()
        self._setup_routes()

    def _setup_routes(self):
        @self.app.post("/proxy/database")
        async def proxy_database(request: DatabaseRequest, worker_id: str = Header(...)):
            """Execute database query using secret credentials."""

            # Validate worker is authorized
            if not await self._is_authorized(worker_id, "database"):
                raise HTTPException(403, "Worker not authorized for database access")

            # Get connection string with secrets
            conn_string = self.secrets.get("DATABASE_URL")
            if not conn_string:
                raise HTTPException(500, "Database secret not configured")

            # Execute query
            async with asyncpg.connect(conn_string) as conn:
                result = await conn.fetch(request.query)

            # Return results (no credentials in response)
            return {"rows": [dict(r) for r in result]}

        @self.app.post("/proxy/http/{service}")
        async def proxy_http(
            service: str,
            request: HttpProxyRequest,
            worker_id: str = Header(...),
        ):
            """Make HTTP request with injected authentication."""

            if not await self._is_authorized(worker_id, service):
                raise HTTPException(403, f"Worker not authorized for {service}")

            # Get service config
            config = self._get_service_config(service)

            # Inject authentication
            headers = dict(request.headers)
            if config.auth_type == "bearer":
                headers["Authorization"] = f"Bearer {self.secrets[config.secret_name]}"
            elif config.auth_type == "api_key":
                headers[config.header_name] = self.secrets[config.secret_name]

            # Make request
            async with httpx.AsyncClient() as client:
                response = await client.request(
                    method=request.method,
                    url=config.base_url + request.path,
                    headers=headers,
                    json=request.body,
                )

            # Return response (strip any secrets that might be echoed)
            return {
                "status": response.status_code,
                "body": self._sanitize_response(response.json()),
            }

    async def _is_authorized(self, worker_id: str, resource: str) -> bool:
        """Check if worker is authorized to access resource."""
        # Check against authorization policy
        policy = await policy_store.get_worker_policy(worker_id)
        return resource in policy.allowed_resources

    def _sanitize_response(self, data: dict) -> dict:
        """Remove any secrets from response data."""
        # Recursively check for secret patterns
        return sanitize_dict(data, self.secrets.values())
```

### Worker Prompt for Proxy Usage

```markdown
## Integration Testing

For integration tests requiring external services, use the secret proxy:

```python
# Instead of:
# conn = psycopg2.connect(os.environ["DATABASE_URL"])  # Won't work - no secrets

# Use:
import httpx

async def query_database(sql: str) -> list[dict]:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:9300/proxy/database",
            json={"query": sql},
            headers={"Worker-ID": os.environ["RINGMASTER_WORKER_ID"]},
        )
        return response.json()["rows"]
```

Available proxy endpoints:
- `POST /proxy/database` - Execute SQL queries
- `POST /proxy/http/{service}` - Make authenticated HTTP requests

The proxy handles authentication. You never see or need the actual secrets.
```

---

## Layer 5: Detection & Redaction

### Output Scanner

```python
class OutputSecretScanner:
    """Scans worker output for secret leakage."""

    def __init__(self, secret_registry: SecretRegistry):
        self.registry = secret_registry

        # Generic patterns for common secret formats
        self.generic_patterns = [
            # AWS keys
            (r"AKIA[0-9A-Z]{16}", "AWS Access Key"),
            (r"[0-9a-zA-Z/+]{40}", "Possible AWS Secret Key"),

            # API keys
            (r"sk-[a-zA-Z0-9]{48}", "OpenAI API Key"),
            (r"sk-ant-[a-zA-Z0-9-]{95}", "Anthropic API Key"),

            # Tokens
            (r"ghp_[a-zA-Z0-9]{36}", "GitHub Personal Access Token"),
            (r"gho_[a-zA-Z0-9]{36}", "GitHub OAuth Token"),
            (r"glpat-[a-zA-Z0-9-]{20}", "GitLab Personal Access Token"),

            # Private keys
            (r"-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----", "Private Key"),
            (r"-----BEGIN PGP PRIVATE KEY BLOCK-----", "PGP Private Key"),

            # Connection strings
            (r"postgres://[^:]+:[^@]+@", "PostgreSQL Connection String"),
            (r"mongodb(\+srv)?://[^:]+:[^@]+@", "MongoDB Connection String"),
            (r"mysql://[^:]+:[^@]+@", "MySQL Connection String"),
            (r"redis://:[^@]+@", "Redis Connection String"),

            # Generic
            (r"['\"]?password['\"]?\s*[:=]\s*['\"][^'\"]+['\"]", "Hardcoded Password"),
            (r"['\"]?api[_-]?key['\"]?\s*[:=]\s*['\"][^'\"]+['\"]", "Hardcoded API Key"),
        ]

    async def scan(
        self,
        content: str,
        project_id: str,
        context: str = "output",
    ) -> ScanResult:
        """Scan content for secrets."""

        findings = []

        # Check registered secrets (exact matches)
        secrets = await self.registry.get_secrets_for_project(project_id)
        for secret in secrets:
            for pattern in self.registry.get_patterns(secret.name):
                if pattern.search(content):
                    findings.append(SecretFinding(
                        type="registered_secret",
                        secret_name=secret.name,
                        category=secret.category,
                        severity="critical",
                        context=context,
                    ))

        # Check generic patterns
        for pattern, description in self.generic_patterns:
            matches = re.findall(pattern, content)
            if matches:
                findings.append(SecretFinding(
                    type="pattern_match",
                    description=description,
                    severity="high",
                    match_count=len(matches),
                    context=context,
                ))

        # Check for high-entropy strings (possible secrets)
        high_entropy = self._find_high_entropy_strings(content)
        for s in high_entropy:
            findings.append(SecretFinding(
                type="high_entropy",
                description=f"High-entropy string detected: {s[:10]}...",
                severity="medium",
                context=context,
            ))

        return ScanResult(
            clean=len(findings) == 0,
            findings=findings,
        )

    def _find_high_entropy_strings(self, content: str, min_length: int = 20) -> list[str]:
        """Find strings with high entropy (likely secrets)."""

        # Extract quoted strings and assignments
        candidates = re.findall(r'["\']([^"\']{20,})["\']', content)

        high_entropy = []
        for candidate in candidates:
            entropy = self._calculate_entropy(candidate)
            if entropy > 4.5:  # Threshold for "random-looking"
                high_entropy.append(candidate)

        return high_entropy

    def _calculate_entropy(self, s: str) -> float:
        """Calculate Shannon entropy of a string."""
        from collections import Counter
        from math import log2

        if not s:
            return 0

        counts = Counter(s)
        length = len(s)
        return -sum(
            (count / length) * log2(count / length)
            for count in counts.values()
        )
```

### Real-Time Redaction

```python
class OutputRedactor:
    """Redacts secrets from worker output in real-time."""

    def __init__(self, scanner: OutputSecretScanner):
        self.scanner = scanner

    async def process_line(
        self,
        line: str,
        project_id: str,
        worker_id: str,
    ) -> tuple[str, bool]:
        """Process a line of output, redacting secrets.

        Returns:
            Tuple of (redacted_line, was_redacted)
        """

        scan_result = await self.scanner.scan(line, project_id)

        if scan_result.clean:
            return line, False

        # Redact findings
        redacted = line
        for finding in scan_result.findings:
            if finding.type == "registered_secret":
                # Replace with placeholder
                patterns = self.scanner.registry.get_patterns(finding.secret_name)
                for pattern in patterns:
                    redacted = pattern.sub(f"[REDACTED:{finding.secret_name}]", redacted)

            elif finding.type == "pattern_match":
                # Replace with generic placeholder
                redacted = re.sub(
                    self.scanner.generic_patterns[0][0],  # The matched pattern
                    f"[REDACTED:possible_{finding.description.lower().replace(' ', '_')}]",
                    redacted
                )

        # Log security event
        await audit_logger.log(
            AuditEventType.SECRET_REDACTED,
            actor=f"worker:{worker_id}",
            resource_type="output",
            resource_id=project_id,
            details={
                "findings": [f.dict() for f in scan_result.findings],
                "line_preview": line[:50] + "..." if len(line) > 50 else line,
            },
        )

        return redacted, True
```

### Git Pre-Commit Hook

```python
class SecretPreCommitHook:
    """Prevents committing secrets to git."""

    async def check(self, staged_files: list[Path], project_id: str) -> HookResult:
        """Check staged files for secrets before commit."""

        violations = []

        for file_path in staged_files:
            content = file_path.read_text()
            scan_result = await scanner.scan(content, project_id, context="git_commit")

            if not scan_result.clean:
                violations.append(FileViolation(
                    file=str(file_path),
                    findings=scan_result.findings,
                ))

        if violations:
            return HookResult(
                allowed=False,
                message=self._format_violation_message(violations),
                violations=violations,
            )

        return HookResult(allowed=True)

    def _format_violation_message(self, violations: list[FileViolation]) -> str:
        lines = ["🚫 Commit blocked: secrets detected in staged files\n"]

        for v in violations:
            lines.append(f"  {v.file}:")
            for f in v.findings:
                lines.append(f"    - {f.description or f.secret_name} ({f.severity})")

        lines.append("\nRemove secrets before committing.")
        return "\n".join(lines)
```

---

## Layer 6: Audit Trail

### Secret Access Logging

```python
class SecretAuditLogger:
    """Specialized audit logging for secret operations."""

    async def log_access(
        self,
        secret_name: str,
        accessor: str,
        access_type: str,
        granted: bool,
        reason: str | None = None,
    ) -> None:
        """Log a secret access attempt."""

        await self.db.execute(
            """
            INSERT INTO secret_audit_log
            (id, timestamp, secret_name, accessor, access_type, granted, reason, ip_address, user_agent)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                generate_id(),
                datetime.now(UTC),
                secret_name,
                accessor,
                access_type,
                granted,
                reason,
                get_client_ip(),
                get_user_agent(),
            )
        )

        # Alert on suspicious patterns
        if not granted:
            await self._check_for_attack_pattern(secret_name, accessor)

    async def log_redaction(
        self,
        secret_name: str,
        context: str,
        worker_id: str,
    ) -> None:
        """Log when a secret was redacted from output."""

        await self.db.execute(
            """
            INSERT INTO secret_redaction_log
            (id, timestamp, secret_name, context, worker_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            (generate_id(), datetime.now(UTC), secret_name, context, worker_id)
        )

        # Frequent redactions may indicate a problem
        recent_count = await self._count_recent_redactions(worker_id)
        if recent_count > 5:
            await self._alert_frequent_redactions(worker_id, recent_count)

    async def _check_for_attack_pattern(self, secret_name: str, accessor: str) -> None:
        """Check if access pattern suggests an attack."""

        # Count recent denied accesses from this accessor
        denied_count = await self.db.fetch_one(
            """
            SELECT COUNT(*) as count FROM secret_audit_log
            WHERE accessor = ? AND granted = FALSE
              AND timestamp > datetime('now', '-1 hour')
            """,
            (accessor,)
        )

        if denied_count["count"] >= 10:
            logger.error(f"Possible secret enumeration attack from {accessor}")

            await notifier.send_alert(
                title="Security Alert: Possible Secret Enumeration",
                message=f"Accessor '{accessor}' has {denied_count['count']} denied secret access attempts in the last hour.",
                severity="critical",
            )

            # Consider blocking the accessor
            await self._block_accessor(accessor)
```

---

## Configuration

```toml
[secrets]
# Storage backend
backend = "kubernetes"  # "kubernetes", "vault", "env", "file"

[secrets.kubernetes]
namespace = "ringmaster"
secret_name = "ringmaster-secrets"

[secrets.vault]
address = "https://vault.example.com"
auth_method = "kubernetes"
role = "ringmaster"

[secrets.scanning]
enabled = true
scan_output = true
scan_prompts = true
scan_git_commits = true
high_entropy_threshold = 4.5

[secrets.redaction]
enabled = true
placeholder_format = "[REDACTED:{name}]"
log_redactions = true

[secrets.proxy]
enabled = true
port = 9300
allowed_services = ["database", "stripe", "aws"]

[secrets.audit]
enabled = true
retention_days = 365
alert_on_denied_access = true
alert_threshold = 10
```

---

## Summary

| Layer | Purpose | Key Mechanism |
|-------|---------|---------------|
| **Classification** | Categorize secrets by sensitivity | 4-tier category system |
| **Runtime Injection** | Secrets never in prompts | Environment sanitization |
| **Sandbox Isolation** | Workers can't access secret storage | Container + network policy |
| **Proxy Pattern** | Integration tests without exposing secrets | Secret-holding proxy |
| **Detection & Redaction** | Catch leakage in output | Pattern matching + entropy analysis |
| **Audit Trail** | Track all secret access | Comprehensive logging |

### Security Invariants

1. **Workers NEVER receive project secrets** - Only worker runtime secrets (LLM API keys, git creds)
2. **Secrets NEVER appear in prompts** - Sanitized before LLM call
3. **Secrets NEVER appear in logs/output** - Real-time redaction
4. **Secrets NEVER committed to git** - Pre-commit hook
5. **Integration tests use proxy** - Secrets stay in trusted context
6. **All access is audited** - Full trail for investigation
7. **Self-improvement can't modify secrets code** - Protected files
