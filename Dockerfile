# Ringmaster Production Image
# Multi-stage build for optimal image size

FROM python:3.12-slim AS builder

# Set build arguments
ARG PY_VERSION=3.12

# Set working directory
WORKDIR /build

# Install system dependencies for building
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Install build dependencies
COPY pyproject.toml ./
RUN pip install --no-cache-dir poetry && \
    poetry config virtualenvs.create false && \
    poetry install --no-dev --no-root --no-interaction

# Final stage
FROM python:3.12-slim

# Set labels
LABEL org.opencontainers.image.title="Ringmaster"
LABEL org.opencontainers.image.description="Multi-Coding-Agent Orchestration Platform"
LABEL org.opencontainers.image.vendor="Ringmaster"

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    tmux \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r ringmaster && \
    useradd -r -g ringmaster -s /bin/bash -m ringmaster

# Set working directory
WORKDIR /app

# Copy Python dependencies from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY src/ringmaster /usr/local/lib/python3.12/site-packages/ringmaster

# Copy frontend static assets
COPY frontend/dist /app/frontend/dist

# Create data directories
RUN mkdir -p /app/data /app/logs /app/output && \
    chown -R ringmaster:ringmaster /app

# Switch to non-root user
USER ringmaster

# Expose ports
# 8000: FastAPI server
# 8001: WebSocket server
EXPOSE 8000 8001

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# Default command starts the API server
CMD ["python", "-m", "ringmaster.cli", "serve", "--host", "0.0.0.0", "--port", "8000"]
