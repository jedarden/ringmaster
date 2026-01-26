"""FastAPI dependencies."""

from fastapi import Request

from ringmaster.db import Database


async def get_db(request: Request) -> Database:
    """Get the database instance from app state."""
    return request.app.state.db
