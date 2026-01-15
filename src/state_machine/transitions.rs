//! Transition definitions for the card state machine

use crate::domain::{Action, CardState, Guard, Trigger};

/// Definition of a state transition
#[derive(Debug, Clone)]
pub struct TransitionDef {
    pub from: CardState,
    pub to: CardState,
    pub trigger: Trigger,
    pub guard: Option<Guard>,
    pub actions: Vec<Action>,
}

impl TransitionDef {
    pub fn new(from: CardState, trigger: Trigger, to: CardState) -> Self {
        Self {
            from,
            to,
            trigger,
            guard: None,
            actions: Vec::new(),
        }
    }

    pub fn with_guard(mut self, guard: Guard) -> Self {
        self.guard = Some(guard);
        self
    }

    pub fn with_action(mut self, action: Action) -> Self {
        self.actions.push(action);
        self
    }

    pub fn with_actions(mut self, actions: Vec<Action>) -> Self {
        self.actions = actions;
        self
    }
}

/// Build all the transition definitions according to the state machine spec
pub fn build_transitions() -> Vec<TransitionDef> {
    use Action::*;
    use CardState::*;
    use Guard::*;
    use Trigger::*;

    vec![
        // Development Phase
        TransitionDef::new(Draft, StartPlanning, Planning),
        TransitionDef::new(Planning, ApprovePlan, Coding)
            .with_guard(HasAcceptanceCriteria)
            .with_actions(vec![CreateGitWorktree, StartRalphLoop]),
        TransitionDef::new(Planning, RejectPlan, Draft),
        TransitionDef::new(Coding, LoopComplete, CodeReview)
            .with_guard(HasGeneratedCode)
            .with_actions(vec![PauseRalphLoop, CreatePullRequest]),
        TransitionDef::new(Coding, ErrorDetected, ErrorFixing)
            .with_guard(UnderRetryLimit)
            .with_action(CollectErrorContext),
        TransitionDef::new(CodeReview, ApproveReview, Testing)
            .with_guard(HasPullRequest),
        TransitionDef::new(CodeReview, RejectReview, Coding)
            .with_action(StartRalphLoop),
        TransitionDef::new(Testing, TestsPassed, BuildQueue),
        TransitionDef::new(Testing, TestsFailed, ErrorFixing)
            .with_guard(UnderRetryLimit)
            .with_action(CollectErrorContext),
        // Build Phase
        TransitionDef::new(BuildQueue, BuildStarted, Building)
            .with_action(MonitorBuild),
        TransitionDef::new(Building, Trigger::BuildSucceeded, BuildSuccess)
            .with_action(RecordMetrics),
        TransitionDef::new(Building, Trigger::BuildFailed, CardState::BuildFailed)
            .with_action(CollectErrorContext),
        TransitionDef::new(BuildSuccess, DeployStarted, DeployQueue),
        TransitionDef::new(CardState::BuildFailed, ErrorDetected, ErrorFixing)
            .with_guard(UnderRetryLimit)
            .with_action(RestartLoopWithError),
        TransitionDef::new(CardState::BuildFailed, MaxRetriesExceeded, Failed)
            .with_action(NotifyUser),
        // Deploy Phase
        TransitionDef::new(DeployQueue, DeployStarted, Deploying)
            .with_action(MonitorArgoCD),
        TransitionDef::new(Deploying, DeploySynced, Verifying)
            .with_guard(SyncCompleted)
            .with_action(RunHealthChecks),
        TransitionDef::new(Deploying, DeployFailed, ErrorFixing)
            .with_guard(UnderRetryLimit)
            .with_action(CollectErrorContext),
        TransitionDef::new(Verifying, VerifyPassed, Completed)
            .with_guard(HealthCheckPassed)
            .with_actions(vec![NotifyUser, RecordMetrics]),
        TransitionDef::new(Verifying, VerifyFailed, ErrorFixing)
            .with_guard(UnderRetryLimit)
            .with_action(CollectErrorContext),
        // Error Fixing transitions
        TransitionDef::new(ErrorFixing, FixApplied, Coding)
            .with_action(RestartLoopWithError),
        TransitionDef::new(ErrorFixing, MaxRetriesExceeded, Failed)
            .with_action(NotifyUser),
        // Archive transitions
        TransitionDef::new(Completed, Archive, Archived),
        TransitionDef::new(Failed, Archive, Archived),
    ]
}

/// Get valid triggers from a given state
pub fn valid_triggers_for_state(state: CardState) -> Vec<Trigger> {
    build_transitions()
        .into_iter()
        .filter(|t| t.from == state)
        .map(|t| t.trigger)
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_transitions_are_defined() {
        let transitions = build_transitions();
        assert!(!transitions.is_empty());
    }

    #[test]
    fn test_draft_can_start_planning() {
        let triggers = valid_triggers_for_state(CardState::Draft);
        assert!(triggers.contains(&Trigger::StartPlanning));
    }

    #[test]
    fn test_coding_can_complete_or_fail() {
        let triggers = valid_triggers_for_state(CardState::Coding);
        assert!(triggers.contains(&Trigger::LoopComplete));
        assert!(triggers.contains(&Trigger::ErrorDetected));
    }
}
