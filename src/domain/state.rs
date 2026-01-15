//! Card state definitions for the SDLC lifecycle

use serde::{Deserialize, Serialize};
use std::fmt;
use std::str::FromStr;

/// The 16 SDLC states a card can be in
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum CardState {
    // Development Phase
    Draft,
    Planning,
    Coding,
    CodeReview,
    Testing,
    // Build Phase
    BuildQueue,
    Building,
    BuildSuccess,
    BuildFailed,
    // Deploy Phase
    DeployQueue,
    Deploying,
    Verifying,
    // Terminal States
    Completed,
    ErrorFixing,
    Archived,
    Failed,
}

impl CardState {
    /// Returns the phase this state belongs to
    pub fn phase(&self) -> Phase {
        match self {
            CardState::Draft
            | CardState::Planning
            | CardState::Coding
            | CardState::CodeReview
            | CardState::Testing => Phase::Development,

            CardState::BuildQueue
            | CardState::Building
            | CardState::BuildSuccess
            | CardState::BuildFailed => Phase::Build,

            CardState::DeployQueue | CardState::Deploying | CardState::Verifying => Phase::Deploy,

            CardState::Completed
            | CardState::ErrorFixing
            | CardState::Archived
            | CardState::Failed => Phase::Terminal,
        }
    }

    /// Returns whether this state allows Ralph loop execution
    pub fn allows_loop(&self) -> bool {
        matches!(self, CardState::Coding | CardState::ErrorFixing)
    }

    /// Returns whether this state is terminal
    pub fn is_terminal(&self) -> bool {
        matches!(
            self,
            CardState::Completed | CardState::Archived | CardState::Failed
        )
    }

    /// Get all states in a specific phase
    pub fn states_in_phase(phase: Phase) -> Vec<CardState> {
        use CardState::*;
        match phase {
            Phase::Development => vec![Draft, Planning, Coding, CodeReview, Testing],
            Phase::Build => vec![BuildQueue, Building, BuildSuccess, BuildFailed],
            Phase::Deploy => vec![DeployQueue, Deploying, Verifying],
            Phase::Terminal => vec![Completed, ErrorFixing, Archived, Failed],
        }
    }

    /// Returns the database string representation
    pub fn as_str(&self) -> &'static str {
        match self {
            CardState::Draft => "draft",
            CardState::Planning => "planning",
            CardState::Coding => "coding",
            CardState::CodeReview => "code_review",
            CardState::Testing => "testing",
            CardState::BuildQueue => "build_queue",
            CardState::Building => "building",
            CardState::BuildSuccess => "build_success",
            CardState::BuildFailed => "build_failed",
            CardState::DeployQueue => "deploy_queue",
            CardState::Deploying => "deploying",
            CardState::Verifying => "verifying",
            CardState::Completed => "completed",
            CardState::ErrorFixing => "error_fixing",
            CardState::Archived => "archived",
            CardState::Failed => "failed",
        }
    }
}

impl fmt::Display for CardState {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.as_str())
    }
}

impl FromStr for CardState {
    type Err = String;

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        match s {
            "draft" => Ok(CardState::Draft),
            "planning" => Ok(CardState::Planning),
            "coding" => Ok(CardState::Coding),
            "code_review" => Ok(CardState::CodeReview),
            "testing" => Ok(CardState::Testing),
            "build_queue" => Ok(CardState::BuildQueue),
            "building" => Ok(CardState::Building),
            "build_success" => Ok(CardState::BuildSuccess),
            "build_failed" => Ok(CardState::BuildFailed),
            "deploy_queue" => Ok(CardState::DeployQueue),
            "deploying" => Ok(CardState::Deploying),
            "verifying" => Ok(CardState::Verifying),
            "completed" => Ok(CardState::Completed),
            "error_fixing" => Ok(CardState::ErrorFixing),
            "archived" => Ok(CardState::Archived),
            "failed" => Ok(CardState::Failed),
            _ => Err(format!("Unknown card state: {}", s)),
        }
    }
}

/// The phases in the SDLC lifecycle
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Phase {
    Development,
    Build,
    Deploy,
    Terminal,
}

impl fmt::Display for Phase {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Phase::Development => write!(f, "development"),
            Phase::Build => write!(f, "build"),
            Phase::Deploy => write!(f, "deploy"),
            Phase::Terminal => write!(f, "terminal"),
        }
    }
}

/// Triggers that cause state transitions
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "PascalCase")]
pub enum Trigger {
    // User triggers
    StartPlanning,
    ApprovePlan,
    RejectPlan,
    ApproveReview,
    RejectReview,
    Archive,

    // System triggers
    LoopComplete,
    LoopFailed,
    TestsPassed,
    TestsFailed,
    BuildStarted,
    BuildSucceeded,
    BuildFailed,
    DeployStarted,
    DeploySynced,
    DeployFailed,
    VerifyPassed,
    VerifyFailed,
    ErrorDetected,
    FixApplied,
    MaxRetriesExceeded,
}

impl fmt::Display for Trigger {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Trigger::StartPlanning => write!(f, "StartPlanning"),
            Trigger::ApprovePlan => write!(f, "ApprovePlan"),
            Trigger::RejectPlan => write!(f, "RejectPlan"),
            Trigger::ApproveReview => write!(f, "ApproveReview"),
            Trigger::RejectReview => write!(f, "RejectReview"),
            Trigger::Archive => write!(f, "Archive"),
            Trigger::LoopComplete => write!(f, "LoopComplete"),
            Trigger::LoopFailed => write!(f, "LoopFailed"),
            Trigger::TestsPassed => write!(f, "TestsPassed"),
            Trigger::TestsFailed => write!(f, "TestsFailed"),
            Trigger::BuildStarted => write!(f, "BuildStarted"),
            Trigger::BuildSucceeded => write!(f, "BuildSucceeded"),
            Trigger::BuildFailed => write!(f, "BuildFailed"),
            Trigger::DeployStarted => write!(f, "DeployStarted"),
            Trigger::DeploySynced => write!(f, "DeploySynced"),
            Trigger::DeployFailed => write!(f, "DeployFailed"),
            Trigger::VerifyPassed => write!(f, "VerifyPassed"),
            Trigger::VerifyFailed => write!(f, "VerifyFailed"),
            Trigger::ErrorDetected => write!(f, "ErrorDetected"),
            Trigger::FixApplied => write!(f, "FixApplied"),
            Trigger::MaxRetriesExceeded => write!(f, "MaxRetriesExceeded"),
        }
    }
}

impl FromStr for Trigger {
    type Err = String;

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        match s {
            "StartPlanning" => Ok(Trigger::StartPlanning),
            "ApprovePlan" => Ok(Trigger::ApprovePlan),
            "RejectPlan" => Ok(Trigger::RejectPlan),
            "ApproveReview" => Ok(Trigger::ApproveReview),
            "RejectReview" => Ok(Trigger::RejectReview),
            "Archive" => Ok(Trigger::Archive),
            "LoopComplete" => Ok(Trigger::LoopComplete),
            "LoopFailed" => Ok(Trigger::LoopFailed),
            "TestsPassed" => Ok(Trigger::TestsPassed),
            "TestsFailed" => Ok(Trigger::TestsFailed),
            "BuildStarted" => Ok(Trigger::BuildStarted),
            "BuildSucceeded" => Ok(Trigger::BuildSucceeded),
            "BuildFailed" => Ok(Trigger::BuildFailed),
            "DeployStarted" => Ok(Trigger::DeployStarted),
            "DeploySynced" => Ok(Trigger::DeploySynced),
            "DeployFailed" => Ok(Trigger::DeployFailed),
            "VerifyPassed" => Ok(Trigger::VerifyPassed),
            "VerifyFailed" => Ok(Trigger::VerifyFailed),
            "ErrorDetected" => Ok(Trigger::ErrorDetected),
            "FixApplied" => Ok(Trigger::FixApplied),
            "MaxRetriesExceeded" => Ok(Trigger::MaxRetriesExceeded),
            _ => Err(format!("Unknown trigger: {}", s)),
        }
    }
}

/// Guard conditions that must be met for a transition
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Guard {
    HasAcceptanceCriteria,
    HasPlan,
    HasGeneratedCode,
    HasPullRequest,
    TestsExist,
    BuildSucceeded,
    SyncCompleted,
    HealthCheckPassed,
    UnderRetryLimit,
}

/// Actions to execute during a transition
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Action {
    CreateGitWorktree,
    StartRalphLoop,
    PauseRalphLoop,
    StopRalphLoop,
    CreatePullRequest,
    TriggerBuild,
    MonitorBuild,
    TriggerDeploy,
    MonitorArgoCD,
    RunHealthChecks,
    CollectErrorContext,
    RestartLoopWithError,
    NotifyUser,
    RecordMetrics,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_state_from_str() {
        assert_eq!(CardState::from_str("draft").unwrap(), CardState::Draft);
        assert_eq!(
            CardState::from_str("code_review").unwrap(),
            CardState::CodeReview
        );
        assert!(CardState::from_str("invalid").is_err());
    }

    #[test]
    fn test_state_phases() {
        assert_eq!(CardState::Draft.phase(), Phase::Development);
        assert_eq!(CardState::Building.phase(), Phase::Build);
        assert_eq!(CardState::Deploying.phase(), Phase::Deploy);
        assert_eq!(CardState::Completed.phase(), Phase::Terminal);
    }

    #[test]
    fn test_allows_loop() {
        assert!(CardState::Coding.allows_loop());
        assert!(CardState::ErrorFixing.allows_loop());
        assert!(!CardState::Draft.allows_loop());
        assert!(!CardState::Building.allows_loop());
    }

    #[test]
    fn test_is_terminal() {
        assert!(CardState::Completed.is_terminal());
        assert!(CardState::Failed.is_terminal());
        assert!(CardState::Archived.is_terminal());
        assert!(!CardState::Coding.is_terminal());
    }
}
