//! Prompt Pipeline - 5-layer recursive prompt enrichment
//!
//! This module provides:
//! - `PromptPipeline`: Assembles prompts with 5 context layers
//! - `RlmSummarizer`: Compresses chat history using RLM summarization

pub mod rlm;

pub use rlm::{RlmConfig, RlmSummarizer, SummarizationResult};

use serde::{Deserialize, Serialize};

use crate::domain::{Card, CardState, Project};

/// Assembled prompt ready for LLM execution
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AssembledPrompt {
    pub system_prompt: String,
    pub user_prompt: String,
    pub context: PromptContext,
    pub metrics: PromptMetrics,
}

/// Context included in the prompt
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PromptContext {
    pub card_context: Option<String>,
    pub project_context: Option<String>,
    pub sdlc_context: Option<String>,
    pub supplemental_context: Option<String>,
    pub refinement_context: Option<String>,
}

/// Metrics for prompt assembly
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PromptMetrics {
    pub total_tokens_estimate: i32,
    pub layer_tokens: Vec<(String, i32)>,
}

/// Prompt pipeline for assembling prompts
pub struct PromptPipeline {
    /// System prompt template
    system_prompt: String,
    /// Max tokens for context
    max_context_tokens: i32,
}

impl Default for PromptPipeline {
    fn default() -> Self {
        Self::new()
    }
}

impl PromptPipeline {
    pub fn new() -> Self {
        Self {
            system_prompt: default_system_prompt(),
            max_context_tokens: 100_000,
        }
    }

    /// Assemble a prompt for a card
    pub fn assemble(&self, card: &Card, project: &Project) -> AssembledPrompt {
        let mut context = PromptContext {
            card_context: None,
            project_context: None,
            sdlc_context: None,
            supplemental_context: None,
            refinement_context: None,
        };

        let mut layer_tokens = Vec::new();

        // Layer 1: Card Context
        let card_ctx = self.build_card_context(card);
        let card_tokens = estimate_tokens(&card_ctx);
        layer_tokens.push(("card".to_string(), card_tokens));
        context.card_context = Some(card_ctx);

        // Layer 2: Project Context
        let project_ctx = self.build_project_context(project);
        let project_tokens = estimate_tokens(&project_ctx);
        layer_tokens.push(("project".to_string(), project_tokens));
        context.project_context = Some(project_ctx);

        // Layer 3: SDLC State Context
        let sdlc_ctx = self.build_sdlc_context(card);
        let sdlc_tokens = estimate_tokens(&sdlc_ctx);
        layer_tokens.push(("sdlc".to_string(), sdlc_tokens));
        context.sdlc_context = Some(sdlc_ctx);

        // Layer 4: Supplemental Context (error logs, etc.)
        // This would be populated from error context, build logs, etc.
        context.supplemental_context = None;

        // Layer 5: Refinement (safety guardrails)
        let refinement_ctx = self.build_refinement_context(card);
        let refinement_tokens = estimate_tokens(&refinement_ctx);
        layer_tokens.push(("refinement".to_string(), refinement_tokens));
        context.refinement_context = Some(refinement_ctx);

        // Build user prompt
        let user_prompt = self.build_user_prompt(card, &context);

        let total_tokens: i32 = layer_tokens.iter().map(|(_, t)| t).sum();

        AssembledPrompt {
            system_prompt: self.system_prompt.clone(),
            user_prompt,
            context,
            metrics: PromptMetrics {
                total_tokens_estimate: total_tokens,
                layer_tokens,
            },
        }
    }

    fn build_card_context(&self, card: &Card) -> String {
        format!(
            r#"## Task Card

**Title:** {}
**Description:** {}
**Task Prompt:**
{}

**Current State:** {}
**Loop Iteration:** {}
"#,
            card.title,
            card.description.as_deref().unwrap_or("No description"),
            card.task_prompt,
            card.state,
            card.loop_iteration
        )
    }

    fn build_project_context(&self, project: &Project) -> String {
        format!(
            r#"## Project Context

**Project:** {}
**Repository:** {}
**Tech Stack:** {}
**Coding Conventions:**
{}
"#,
            project.name,
            project.repository_url,
            project.tech_stack.join(", "),
            project.coding_conventions.as_deref().unwrap_or("Follow standard best practices")
        )
    }

    fn build_sdlc_context(&self, card: &Card) -> String {
        let phase_guidance = match card.state {
            CardState::Planning => {
                "You are in the PLANNING phase. Create a detailed implementation plan."
            }
            CardState::Coding => {
                "You are in the CODING phase. Implement the planned features. When complete, output <promise>COMPLETE</promise>."
            }
            CardState::ErrorFixing => {
                "You are in the ERROR_FIXING phase. Analyze the error context and fix the issues."
            }
            _ => "Follow the task requirements.",
        };

        format!(
            r#"## SDLC Phase

**Phase:** {}
**Guidance:** {}
"#,
            card.state.phase(),
            phase_guidance
        )
    }

    fn build_refinement_context(&self, card: &Card) -> String {
        let worktree_path = card.worktree_path.as_deref().unwrap_or(".");

        format!(
            r#"## Safety & Constraints

- Only modify files within the worktree: {}
- Do not delete or modify critical configuration files
- Follow the project's coding conventions
- Write tests for new functionality
- Signal completion with: <promise>COMPLETE</promise>
"#,
            worktree_path
        )
    }

    fn build_user_prompt(&self, card: &Card, context: &PromptContext) -> String {
        let mut prompt = String::new();

        if let Some(ctx) = &context.card_context {
            prompt.push_str(ctx);
            prompt.push_str("\n\n");
        }

        if let Some(ctx) = &context.project_context {
            prompt.push_str(ctx);
            prompt.push_str("\n\n");
        }

        if let Some(ctx) = &context.sdlc_context {
            prompt.push_str(ctx);
            prompt.push_str("\n\n");
        }

        if let Some(ctx) = &context.supplemental_context {
            prompt.push_str("## Additional Context\n\n");
            prompt.push_str(ctx);
            prompt.push_str("\n\n");
        }

        if let Some(ctx) = &context.refinement_context {
            prompt.push_str(ctx);
        }

        prompt
    }
}

/// Estimate token count (rough approximation: 4 chars per token)
fn estimate_tokens(text: &str) -> i32 {
    (text.len() / 4) as i32
}

/// Default system prompt
fn default_system_prompt() -> String {
    r#"You are an expert software engineer working on implementing features and fixing bugs.
You have access to the full codebase and can make any necessary changes.

## Instructions

1. Analyze the task requirements carefully
2. Plan your implementation approach
3. Make changes incrementally, testing as you go
4. Follow the project's coding conventions
5. When the task is complete, output: <promise>COMPLETE</promise>

## Output Format

Structure your response as:
- **Analysis**: Brief analysis of the task
- **Implementation**: Code changes with file paths
- **Testing**: How to verify the changes work
- **Status**: Either continue working or signal completion

Remember to signal completion only when the task is fully done.
"#
    .to_string()
}

#[cfg(test)]
mod tests {
    use super::*;
    use uuid::Uuid;

    #[test]
    fn test_prompt_assembly() {
        let pipeline = PromptPipeline::new();

        let project = Project::new(
            "Test Project".to_string(),
            "https://github.com/test/repo".to_string(),
        );

        let card = Card::new(
            project.id,
            "Implement feature X".to_string(),
            "Add a new feature that does X, Y, and Z".to_string(),
        );

        let prompt = pipeline.assemble(&card, &project);

        assert!(!prompt.system_prompt.is_empty());
        assert!(!prompt.user_prompt.is_empty());
        assert!(prompt.context.card_context.is_some());
        assert!(prompt.context.project_context.is_some());
    }
}
