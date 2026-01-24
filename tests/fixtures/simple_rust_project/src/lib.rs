//! Simple test project for integration tests

/// This function needs to be implemented by the AI
/// It should return the number 42
pub fn answer() -> i32 {
    // TODO: Implement this function
    0
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_answer() {
        assert_eq!(answer(), 42);
    }
}
