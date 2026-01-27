"""FastAPI application factory."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ringmaster.api.routes import (
    chat,
    files,
    graph,
    input,
    logs,
    metrics,
    projects,
    queue,
    tasks,
    workers,
    ws,
)
from ringmaster.db.connection import close_database, get_database

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler."""
    # Startup
    logger.info("Starting Ringmaster API...")
    db = await get_database()
    app.state.db = db
    logger.info("Database connected")

    yield

    # Shutdown
    logger.info("Shutting down Ringmaster API...")
    await close_database()
    logger.info("Database disconnected")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Ringmaster",
        description="Multi-Coding-Agent Orchestration Platform",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure appropriately for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers
    app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
    app.include_router(tasks.router, prefix="/api/tasks", tags=["tasks"])
    app.include_router(workers.router, prefix="/api/workers", tags=["workers"])
    app.include_router(queue.router, prefix="/api/queue", tags=["queue"])
    app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
    app.include_router(files.router, prefix="/api/projects", tags=["files"])
    app.include_router(metrics.router, prefix="/api/metrics", tags=["metrics"])
    app.include_router(input.router, prefix="/api/input", tags=["input"])
    app.include_router(logs.router, prefix="/api/logs", tags=["logs"])
    app.include_router(graph.router, prefix="/api/graph", tags=["graph"])
    app.include_router(ws.router, prefix="/ws", tags=["websocket"])

    @app.get("/health")
    async def health_check() -> dict:
        """Health check endpoint."""
        return {"status": "healthy", "version": "0.1.0"}

    return app


# Create the app instance
app = create_app()
