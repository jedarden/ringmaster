//! Card State Machine implementation

use std::collections::HashMap;

use crate::domain::{Action, Card, CardState, Guard, Trigger};
use crate::state_machine::transitions::{build_transitions, TransitionDef};
use thiserror::Error;

#[derive(Error, Debug)]
pub enum TransitionError {
    #[error("Invalid transition from {from} with trigger {trigger}")]
    InvalidTransition { from: CardState, trigger: Trigger },

    #[error("Guard condition failed: {guard:?}")]
    GuardFailed { guard: Guard },

    #[error("Action execution failed: {action:?} - {message}")]
    ActionFailed { action: Action, message: String },
}

/// The card state machine handles all state transitions
pub struct CardStateMachine {
    transitions: HashMap<(CardState, Trigger), TransitionDef>,
}

impl Default for CardStateMachine {
    fn default() -> Self {
        Self::new()
    }
}

impl CardStateMachine {
    pub fn new() -> Self {
        let mut transitions = HashMap::new();

        for def in build_transitions() {
            transitions.insert((def.from, def.trigger), def);
        }

        Self { transitions }
    }

    /// Check if a transition is valid (without executing it)
    pub fn can_transition(&self, card: &Card, trigger: Trigger) -> Result<(), TransitionError> {
        let key = (card.state, trigger);
        let def = self
            .transitions
            .get(&key)
            .ok_or(TransitionError::InvalidTransition {
                from: card.state,
                trigger,
            })?;

        // Check guard condition
        if let Some(guard) = &def.guard {
            if !self.evaluate_guard(card, guard) {
                return Err(TransitionError::GuardFailed {
                    guard: guard.clone(),
                });
            }
        }

        Ok(())
    }

    /// Get the target state for a transition (without executing it)
    pub fn get_target_state(
        &self,
        current: CardState,
        trigger: Trigger,
    ) -> Option<CardState> {
        self.transitions
            .get(&(current, trigger))
            .map(|def| def.to)
    }

    /// Get the transition definition for a given state and trigger
    pub fn get_transition(&self, state: CardState, trigger: Trigger) -> Option<&TransitionDef> {
        self.transitions.get(&(state, trigger))
    }

    /// Execute a transition on a card
    /// Returns the new state and the actions that need to be executed
    pub fn transition(
        &self,
        card: &mut Card,
        trigger: Trigger,
    ) -> Result<(CardState, Vec<Action>), TransitionError> {
        let key = (card.state, trigger);
        let def = self
            .transitions
            .get(&key)
            .ok_or(TransitionError::InvalidTransition {
                from: card.state,
                trigger,
            })?;

        // Check guard condition
        if let Some(guard) = &def.guard {
            if !self.evaluate_guard(card, guard) {
                return Err(TransitionError::GuardFailed {
                    guard: guard.clone(),
                });
            }
        }

        // Record previous state
        card.previous_state = Some(card.state);
        card.state = def.to;
        card.state_changed_at = Some(chrono::Utc::now());

        Ok((def.to, def.actions.clone()))
    }

    /// Evaluate a guard condition against a card
    fn evaluate_guard(&self, card: &Card, guard: &Guard) -> bool {
        match guard {
            Guard::HasAcceptanceCriteria => {
                // This would need to check the DB - for now we assume true if prompt exists
                !card.task_prompt.is_empty()
            }
            Guard::HasPlan => card.state != CardState::Draft,
            Guard::HasGeneratedCode => card.has_code_changes(),
            Guard::HasPullRequest => card.pull_request_url.is_some(),
            Guard::TestsExist => true, // Would need to verify tests exist in worktree
            Guard::BuildSucceeded => card.state == CardState::BuildSuccess,
            Guard::SyncCompleted => true, // Would check ArgoCD status
            Guard::HealthCheckPassed => true, // Would check k8s health
            Guard::UnderRetryLimit => card.under_retry_limit(),
        }
    }

    /// Get all valid triggers for a card in its current state
    pub fn valid_triggers(&self, card: &Card) -> Vec<Trigger> {
        self.transitions
            .iter()
            .filter(|((from, _), def)| {
                *from == card.state
                    && def
                        .guard
                        .as_ref()
                        .map(|g| self.evaluate_guard(card, g))
                        .unwrap_or(true)
            })
            .map(|((_, trigger), _)| *trigger)
            .collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use uuid::Uuid;

    fn test_card() -> Card {
        Card::new(
            Uuid::new_v4(),
            "Test Card".to_string(),
            "Test task prompt".to_string(),
        )
    }

    #[test]
    fn test_draft_to_planning() {
        let machine = CardStateMachine::new();
        let mut card = test_card();
        assert_eq!(card.state, CardState::Draft);

        let result = machine.transition(&mut card, Trigger::StartPlanning);
        assert!(result.is_ok());
        assert_eq!(card.state, CardState::Planning);
        assert_eq!(card.previous_state, Some(CardState::Draft));
    }

    #[test]
    fn test_invalid_transition() {
        let machine = CardStateMachine::new();
        let mut card = test_card();

        // Can't go directly from Draft to Coding
        let result = machine.transition(&mut card, Trigger::LoopComplete);
        assert!(result.is_err());
    }

    #[test]
    fn test_can_transition() {
        let machine = CardStateMachine::new();
        let card = test_card();

        assert!(machine.can_transition(&card, Trigger::StartPlanning).is_ok());
        assert!(machine.can_transition(&card, Trigger::BuildStarted).is_err());
    }

    #[test]
    fn test_valid_triggers() {
        let machine = CardStateMachine::new();
        let card = test_card();

        let triggers = machine.valid_triggers(&card);
        assert!(triggers.contains(&Trigger::StartPlanning));
        assert!(!triggers.contains(&Trigger::BuildStarted));
    }
}
