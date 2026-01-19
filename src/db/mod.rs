//! Database module - SQLite with sqlx

mod pool;
mod cards;
mod projects;
mod attempts;
mod models;
mod queries;

pub use pool::*;
pub use cards::*;
pub use projects::*;
pub use attempts::*;
pub use queries::create_error;

use crate::domain::CardError;
use sqlx::SqlitePool;

/// Record an error in the database (alias for create_error)
pub async fn record_error(pool: &SqlitePool, error: &CardError) -> Result<(), sqlx::Error> {
    create_error(pool, error).await
}
