"""Database connection and migration management."""

import logging
from pathlib import Path
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)

# Global database instance
_database: "Database | None" = None


class Database:
    """SQLite database wrapper with async support."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self._connection: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        """Open database connection and run migrations."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = await aiosqlite.connect(self.db_path)
        self._connection.row_factory = aiosqlite.Row

        # Enable WAL mode and other pragmas
        await self._connection.execute("PRAGMA journal_mode = WAL")
        await self._connection.execute("PRAGMA synchronous = NORMAL")
        await self._connection.execute("PRAGMA foreign_keys = ON")
        await self._connection.execute("PRAGMA busy_timeout = 5000")

        await self._run_migrations()
        logger.info(f"Connected to database: {self.db_path}")

    async def disconnect(self) -> None:
        """Close database connection."""
        if self._connection:
            await self._connection.close()
            self._connection = None
            logger.info("Database connection closed")

    @property
    def connection(self) -> aiosqlite.Connection:
        """Get the database connection."""
        if not self._connection:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._connection

    async def execute(
        self, query: str, params: tuple[Any, ...] | dict[str, Any] | None = None
    ) -> aiosqlite.Cursor:
        """Execute a query and return cursor."""
        if params is None:
            return await self.connection.execute(query)
        return await self.connection.execute(query, params)

    async def executemany(
        self, query: str, params_seq: list[tuple[Any, ...]]
    ) -> aiosqlite.Cursor:
        """Execute a query with multiple parameter sets."""
        return await self.connection.executemany(query, params_seq)

    async def fetchone(
        self, query: str, params: tuple[Any, ...] | dict[str, Any] | None = None
    ) -> aiosqlite.Row | None:
        """Execute query and fetch one row."""
        cursor = await self.execute(query, params)
        return await cursor.fetchone()

    async def fetchall(
        self, query: str, params: tuple[Any, ...] | dict[str, Any] | None = None
    ) -> list[aiosqlite.Row]:
        """Execute query and fetch all rows."""
        cursor = await self.execute(query, params)
        return await cursor.fetchall()

    async def commit(self) -> None:
        """Commit the current transaction."""
        await self.connection.commit()

    async def _run_migrations(self) -> None:
        """Run pending SQL migrations."""
        migrations_dir = Path(__file__).parent.parent.parent.parent / "migrations"

        if not migrations_dir.exists():
            logger.warning(f"Migrations directory not found: {migrations_dir}")
            return

        # Get list of migration files
        migration_files = sorted(migrations_dir.glob("*.sql"))

        for migration_file in migration_files:
            # Extract version number from filename (e.g., "001_initial.sql" -> 1)
            version_str = migration_file.stem.split("_")[0]
            try:
                version = int(version_str)
            except ValueError:
                logger.warning(f"Skipping invalid migration filename: {migration_file}")
                continue

            # Check if already applied
            try:
                row = await self.fetchone(
                    "SELECT version FROM _migrations WHERE version = ?", (version,)
                )
                if row:
                    continue
            except aiosqlite.OperationalError:
                # _migrations table doesn't exist yet, first migration will create it
                pass

            # Run migration
            logger.info(f"Applying migration: {migration_file.name}")
            sql = migration_file.read_text()

            try:
                # Use executescript for the entire migration file
                # This properly handles multi-statement SQL with embedded semicolons
                await self.connection.executescript(sql)
                await self.commit()
                logger.info(f"Migration applied: {migration_file.name}")
            except Exception as e:
                logger.error(
                    f"Failed to apply migration {migration_file.name}: {type(e).__name__}: {e}"
                )
                raise


async def get_database(db_path: str | Path | None = None) -> Database:
    """Get or create the global database instance."""
    global _database

    if _database is None:
        if db_path is None:
            db_path = Path.home() / ".ringmaster" / "ringmaster.db"
        _database = Database(db_path)
        await _database.connect()

    return _database


async def close_database() -> None:
    """Close the global database instance."""
    global _database

    if _database:
        await _database.disconnect()
        _database = None
