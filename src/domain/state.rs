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
    fn test_state_from_str_all_states() {
        assert_eq!(CardState::from_str("draft").unwrap(), CardState::Draft);
        assert_eq!(CardState::from_str("planning").unwrap(), CardState::Planning);
        assert_eq!(CardState::from_str("coding").unwrap(), CardState::Coding);
        assert_eq!(CardState::from_str("code_review").unwrap(), CardState::CodeReview);
        assert_eq!(CardState::from_str("testing").unwrap(), CardState::Testing);
        assert_eq!(CardState::from_str("build_queue").unwrap(), CardState::BuildQueue);
        assert_eq!(CardState::from_str("building").unwrap(), CardState::Building);
        assert_eq!(CardState::from_str("build_success").unwrap(), CardState::BuildSuccess);
        assert_eq!(CardState::from_str("build_failed").unwrap(), CardState::BuildFailed);
        assert_eq!(CardState::from_str("deploy_queue").unwrap(), CardState::DeployQueue);
        assert_eq!(CardState::from_str("deploying").unwrap(), CardState::Deploying);
        assert_eq!(CardState::from_str("verifying").unwrap(), CardState::Verifying);
        assert_eq!(CardState::from_str("completed").unwrap(), CardState::Completed);
        assert_eq!(CardState::from_str("error_fixing").unwrap(), CardState::ErrorFixing);
        assert_eq!(CardState::from_str("archived").unwrap(), CardState::Archived);
        assert_eq!(CardState::from_str("failed").unwrap(), CardState::Failed);
    }

    #[test]
    fn test_state_as_str() {
        assert_eq!(CardState::Draft.as_str(), "draft");
        assert_eq!(CardState::Planning.as_str(), "planning");
        assert_eq!(CardState::Coding.as_str(), "coding");
        assert_eq!(CardState::CodeReview.as_str(), "code_review");
        assert_eq!(CardState::Testing.as_str(), "testing");
        assert_eq!(CardState::BuildQueue.as_str(), "build_queue");
        assert_eq!(CardState::Building.as_str(), "building");
        assert_eq!(CardState::BuildSuccess.as_str(), "build_success");
        assert_eq!(CardState::BuildFailed.as_str(), "build_failed");
        assert_eq!(CardState::DeployQueue.as_str(), "deploy_queue");
        assert_eq!(CardState::Deploying.as_str(), "deploying");
        assert_eq!(CardState::Verifying.as_str(), "verifying");
        assert_eq!(CardState::Completed.as_str(), "completed");
        assert_eq!(CardState::ErrorFixing.as_str(), "error_fixing");
        assert_eq!(CardState::Archived.as_str(), "archived");
        assert_eq!(CardState::Failed.as_str(), "failed");
    }

    #[test]
    fn test_state_display() {
        assert_eq!(CardState::Draft.to_string(), "draft");
        assert_eq!(CardState::CodeReview.to_string(), "code_review");
        assert_eq!(CardState::BuildSuccess.to_string(), "build_success");
    }

    #[test]
    fn test_state_phases() {
        assert_eq!(CardState::Draft.phase(), Phase::Development);
        assert_eq!(CardState::Building.phase(), Phase::Build);
        assert_eq!(CardState::Deploying.phase(), Phase::Deploy);
        assert_eq!(CardState::Completed.phase(), Phase::Terminal);
    }

    #[test]
    fn test_state_phases_all_development() {
        assert_eq!(CardState::Draft.phase(), Phase::Development);
        assert_eq!(CardState::Planning.phase(), Phase::Development);
        assert_eq!(CardState::Coding.phase(), Phase::Development);
        assert_eq!(CardState::CodeReview.phase(), Phase::Development);
        assert_eq!(CardState::Testing.phase(), Phase::Development);
    }

    #[test]
    fn test_state_phases_all_build() {
        assert_eq!(CardState::BuildQueue.phase(), Phase::Build);
        assert_eq!(CardState::Building.phase(), Phase::Build);
        assert_eq!(CardState::BuildSuccess.phase(), Phase::Build);
        assert_eq!(CardState::BuildFailed.phase(), Phase::Build);
    }

    #[test]
    fn test_state_phases_all_deploy() {
        assert_eq!(CardState::DeployQueue.phase(), Phase::Deploy);
        assert_eq!(CardState::Deploying.phase(), Phase::Deploy);
        assert_eq!(CardState::Verifying.phase(), Phase::Deploy);
    }

    #[test]
    fn test_state_phases_all_terminal() {
        assert_eq!(CardState::Completed.phase(), Phase::Terminal);
        assert_eq!(CardState::ErrorFixing.phase(), Phase::Terminal);
        assert_eq!(CardState::Archived.phase(), Phase::Terminal);
        assert_eq!(CardState::Failed.phase(), Phase::Terminal);
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

    #[test]
    fn test_states_in_phase() {
        let dev_states = CardState::states_in_phase(Phase::Development);
        assert_eq!(dev_states.len(), 5);
        assert!(dev_states.contains(&CardState::Draft));
        assert!(dev_states.contains(&CardState::Planning));
        assert!(dev_states.contains(&CardState::Coding));
        assert!(dev_states.contains(&CardState::CodeReview));
        assert!(dev_states.contains(&CardState::Testing));

        let build_states = CardState::states_in_phase(Phase::Build);
        assert_eq!(build_states.len(), 4);
        assert!(build_states.contains(&CardState::BuildQueue));
        assert!(build_states.contains(&CardState::Building));
        assert!(build_states.contains(&CardState::BuildSuccess));
        assert!(build_states.contains(&CardState::BuildFailed));

        let deploy_states = CardState::states_in_phase(Phase::Deploy);
        assert_eq!(deploy_states.len(), 3);
        assert!(deploy_states.contains(&CardState::DeployQueue));
        assert!(deploy_states.contains(&CardState::Deploying));
        assert!(deploy_states.contains(&CardState::Verifying));

        let terminal_states = CardState::states_in_phase(Phase::Terminal);
        assert_eq!(terminal_states.len(), 4);
        assert!(terminal_states.contains(&CardState::Completed));
        assert!(terminal_states.contains(&CardState::ErrorFixing));
        assert!(terminal_states.contains(&CardState::Archived));
        assert!(terminal_states.contains(&CardState::Failed));
    }

    #[test]
    fn test_phase_display() {
        assert_eq!(Phase::Development.to_string(), "development");
        assert_eq!(Phase::Build.to_string(), "build");
        assert_eq!(Phase::Deploy.to_string(), "deploy");
        assert_eq!(Phase::Terminal.to_string(), "terminal");
    }

    #[test]
    fn test_trigger_display() {
        assert_eq!(Trigger::StartPlanning.to_string(), "StartPlanning");
        assert_eq!(Trigger::ApprovePlan.to_string(), "ApprovePlan");
        assert_eq!(Trigger::LoopComplete.to_string(), "LoopComplete");
        assert_eq!(Trigger::BuildSucceeded.to_string(), "BuildSucceeded");
        assert_eq!(Trigger::DeploySynced.to_string(), "DeploySynced");
        assert_eq!(Trigger::MaxRetriesExceeded.to_string(), "MaxRetriesExceeded");
    }

    #[test]
    fn test_trigger_from_str() {
        assert_eq!(Trigger::from_str("StartPlanning").unwrap(), Trigger::StartPlanning);
        assert_eq!(Trigger::from_str("ApprovePlan").unwrap(), Trigger::ApprovePlan);
        assert_eq!(Trigger::from_str("RejectPlan").unwrap(), Trigger::RejectPlan);
        assert_eq!(Trigger::from_str("ApproveReview").unwrap(), Trigger::ApproveReview);
        assert_eq!(Trigger::from_str("RejectReview").unwrap(), Trigger::RejectReview);
        assert_eq!(Trigger::from_str("Archive").unwrap(), Trigger::Archive);
        assert_eq!(Trigger::from_str("LoopComplete").unwrap(), Trigger::LoopComplete);
        assert_eq!(Trigger::from_str("LoopFailed").unwrap(), Trigger::LoopFailed);
        assert_eq!(Trigger::from_str("TestsPassed").unwrap(), Trigger::TestsPassed);
        assert_eq!(Trigger::from_str("TestsFailed").unwrap(), Trigger::TestsFailed);
        assert_eq!(Trigger::from_str("BuildStarted").unwrap(), Trigger::BuildStarted);
        assert_eq!(Trigger::from_str("BuildSucceeded").unwrap(), Trigger::BuildSucceeded);
        assert_eq!(Trigger::from_str("BuildFailed").unwrap(), Trigger::BuildFailed);
        assert_eq!(Trigger::from_str("DeployStarted").unwrap(), Trigger::DeployStarted);
        assert_eq!(Trigger::from_str("DeploySynced").unwrap(), Trigger::DeploySynced);
        assert_eq!(Trigger::from_str("DeployFailed").unwrap(), Trigger::DeployFailed);
        assert_eq!(Trigger::from_str("VerifyPassed").unwrap(), Trigger::VerifyPassed);
        assert_eq!(Trigger::from_str("VerifyFailed").unwrap(), Trigger::VerifyFailed);
        assert_eq!(Trigger::from_str("ErrorDetected").unwrap(), Trigger::ErrorDetected);
        assert_eq!(Trigger::from_str("FixApplied").unwrap(), Trigger::FixApplied);
        assert_eq!(Trigger::from_str("MaxRetriesExceeded").unwrap(), Trigger::MaxRetriesExceeded);
    }

    #[test]
    fn test_trigger_from_str_invalid() {
        let result = Trigger::from_str("InvalidTrigger");
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("Unknown trigger"));
    }

    #[test]
    fn test_card_state_serialization() {
        let json = serde_json::to_string(&CardState::CodeReview).unwrap();
        assert_eq!(json, "\"code_review\"");

        let deserialized: CardState = serde_json::from_str("\"build_queue\"").unwrap();
        assert_eq!(deserialized, CardState::BuildQueue);
    }

    #[test]
    fn test_trigger_serialization() {
        let json = serde_json::to_string(&Trigger::StartPlanning).unwrap();
        assert_eq!(json, "\"StartPlanning\"");

        let deserialized: Trigger = serde_json::from_str("\"BuildSucceeded\"").unwrap();
        assert_eq!(deserialized, Trigger::BuildSucceeded);
    }
}
