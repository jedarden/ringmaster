//! Database connection pool

use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};
use sqlx::SqlitePool;
use std::path::Path;
use std::str::FromStr;

/// Create a new SQLite connection pool
pub async fn create_pool(database_path: &str) -> Result<SqlitePool, sqlx::Error> {
    // Ensure parent directory exists
    if let Some(parent) = Path::new(database_path).parent() {
        std::fs::create_dir_all(parent).ok();
    }

    let options = SqliteConnectOptions::from_str(database_path)?
        .create_if_missing(true)
        .journal_mode(sqlx::sqlite::SqliteJournalMode::Wal)
        .foreign_keys(true);

    let pool = SqlitePoolOptions::new()
        .max_connections(10)
        .connect_with(options)
        .await?;

    Ok(pool)
}

/// Run database migrations
pub async fn run_migrations(pool: &SqlitePool) -> Result<(), sqlx::Error> {
    // All migration files in order
    let migrations = [
        include_str!("../../migrations/001_initial_schema.sql"),
        include_str!("../../migrations/002_chat_history.sql"),
        include_str!("../../migrations/003_loop_checkpoints.sql"),
        include_str!("../../migrations/004_session_metrics.sql"),
    ];

    for migration_sql in migrations {
        // Parse statements properly - handling parentheses for CREATE TABLE
        let statements = parse_sql_statements(migration_sql);

        for stmt in statements {
            let stmt = stmt.trim();
            if stmt.is_empty() || stmt.starts_with("--") || stmt.starts_with("PRAGMA") {
                continue;
            }

            if let Err(e) = sqlx::query(stmt).execute(pool).await {
                let err_str = e.to_string();
                if !err_str.contains("already exists") {
                    tracing::warn!("Migration statement failed: {} - {}", &stmt[..stmt.len().min(50)], e);
                }
            }
        }
    }

    Ok(())
}

/// Parse SQL statements, properly handling parentheses in CREATE TABLE
fn parse_sql_statements(sql: &str) -> Vec<String> {
    let mut statements = Vec::new();
    let mut current = String::new();
    let mut paren_depth: i32 = 0;
    let mut in_string = false;
    let mut in_line_comment = false;
    let mut chars = sql.chars().peekable();

    while let Some(c) = chars.next() {
        // Handle line comments
        if c == '-' && chars.peek() == Some(&'-') && !in_string {
            in_line_comment = true;
            continue;
        }
        if in_line_comment {
            if c == '\n' {
                in_line_comment = false;
                current.push(c);
            }
            continue;
        }

        match c {
            '\'' => {
                in_string = !in_string;
                current.push(c);
            }
            '(' if !in_string => {
                paren_depth += 1;
                current.push(c);
            }
            ')' if !in_string => {
                paren_depth = paren_depth.saturating_sub(1);
                current.push(c);
            }
            ';' if !in_string && paren_depth == 0 => {
                let stmt = current.trim().to_string();
                if !stmt.is_empty() && !stmt.starts_with("PRAGMA") {
                    statements.push(stmt);
                }
                current.clear();
            }
            _ => {
                current.push(c);
            }
        }
    }

    // Don't forget the last statement if no trailing semicolon
    let stmt = current.trim().to_string();
    if !stmt.is_empty() && !stmt.starts_with("PRAGMA") {
        statements.push(stmt);
    }

    statements
}

/// Initialize database - create pool and run migrations
pub async fn init_database(database_path: &str) -> Result<SqlitePool, sqlx::Error> {
    let pool = create_pool(database_path).await?;
    run_migrations(&pool).await?;
    Ok(pool)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn test_create_pool() {
        let pool = create_pool("sqlite::memory:").await;
        assert!(pool.is_ok());
    }
}
