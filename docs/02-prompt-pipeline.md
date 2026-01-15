# Prompt Assembly Pipeline

## Overview

The Prompt Assembly Pipeline constructs the final prompt sent to the code generation LLM. It combines multiple context sources in a specific order, using RLM (Recursive Language Model) summarization when content exceeds token limits.

## Key Term: RLM (Recursive Language Model)

**RLM** is a context management technique that uses an LLM to summarize long content while preserving essential information. Its purpose is to ensure the code generation LLM has relevant context to either:
1. **Act on the information** - generate code, fix bugs, implement features
2. **Spawn child agents** - conduct supplemental research if more context is needed

```
Long Content (50k tokens) → [RLM Summarization] → Condensed Context (5k tokens)
                                                          │
                                                          ▼
                                                    Code Gen LLM
                                                          │
                                        ┌─────────────────┴─────────────────┐
                                        ▼                                   ▼
                                  Act directly                    Spawn child research
                                  (has enough context)            (needs more info)
```

## Prompt Structure

The final prompt is assembled in this order:

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                              PROMPT STRUCTURE                                         │
└──────────────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────────────────┐
│  1. SYSTEM PROMPT                                                                     │
│                                                                                       │
│  Base instructions for the LLM:                                                       │
│  • Role definition ("You are a senior software engineer...")                          │
│  • General capabilities and constraints                                               │
│  • Output format expectations                                                         │
│  • Safety guardrails                                                                  │
│                                                                                       │
│  Token Budget: ~500-1000 tokens (static)                                              │
└──────────────────────────────────────────────────────────────────────────────────────┘
                                         │
                                         ▼
┌──────────────────────────────────────────────────────────────────────────────────────┐
│  2. CODING AGENT SYSTEM PROMPT                                                        │
│                                                                                       │
│  Agent-specific instructions for the current task type:                               │
│  • Stage-specific behavior (planning vs coding vs error-fixing)                       │
│  • Tool usage instructions                                                            │
│  • Completion signal format (<promise>COMPLETE</promise>)                             │
│  • Code style and conventions                                                         │
│                                                                                       │
│  Token Budget: ~500-1500 tokens (varies by stage)                                     │
└──────────────────────────────────────────────────────────────────────────────────────┘
                                         │
                                         ▼
┌──────────────────────────────────────────────────────────────────────────────────────┐
│  3. CARD CHAT HISTORY                                                                 │
│                                                                                       │
│  Previous conversation and attempts on this card:                                     │
│  • User requests and clarifications                                                   │
│  • Previous LLM responses and code generated                                          │
│  • Error messages and fixes attempted                                                 │
│  • Progress notes                                                                     │
│                                                                                       │
│  ⚠️  RLM APPLIED: If history exceeds budget, use LLM to summarize                     │
│                                                                                       │
│  Token Budget: ~5000-15000 tokens (RLM summarized if needed)                          │
└──────────────────────────────────────────────────────────────────────────────────────┘
                                         │
                                         ▼
┌──────────────────────────────────────────────────────────────────────────────────────┐
│  4. OTHER CONTEXT                                                                     │
│                                                                                       │
│  Supporting information for the task:                                                 │
│  • Notes (user-provided context, requirements)                                        │
│  • ADRs (Architecture Decision Records)                                               │
│  • Libraries/dependencies documentation                                               │
│  • Relevant source files                                                              │
│  • Build logs (if fixing build errors)                                                │
│  • Pod logs (if fixing runtime errors)                                                │
│  • Test results                                                                       │
│                                                                                       │
│  Token Budget: ~5000-20000 tokens (prioritized by relevance)                          │
└──────────────────────────────────────────────────────────────────────────────────────┘
                                         │
                                         ▼
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                              FINAL ASSEMBLED PROMPT                                   │
│                              (~15000-40000 tokens)                                    │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

## Section Details

### 1. System Prompt

The base system prompt defines the LLM's role and general behavior:

```markdown
You are a senior software engineer working on a development task. You have
access to tools for reading files, writing code, and executing commands.

## Guidelines
- Write clean, maintainable code following project conventions
- Include appropriate error handling
- Write tests for new functionality
- Do not modify files outside the designated workspace
- Do not expose secrets or credentials

## Output Format
- Explain your reasoning before writing code
- Use markdown code blocks with language identifiers
- Signal completion with: <promise>COMPLETE</promise>
```

### 2. Coding Agent System Prompt

Stage-specific instructions that change based on the card's current state:

| Stage | Agent Focus |
|-------|-------------|
| **Planning** | Architecture decisions, implementation steps, risk assessment |
| **Coding** | Feature implementation, TDD approach, code quality |
| **Code Review** | Address feedback, fix issues, explain changes |
| **Testing** | Write/fix tests, improve coverage, handle edge cases |
| **Error Fixing** | Analyze error, identify root cause, implement fix |

```rust
fn get_agent_prompt(state: CardState) -> &'static str {
    match state {
        CardState::Planning => PLANNING_AGENT_PROMPT,
        CardState::Coding => CODING_AGENT_PROMPT,
        CardState::CodeReview => REVIEW_AGENT_PROMPT,
        CardState::Testing => TESTING_AGENT_PROMPT,
        CardState::ErrorFixing => ERROR_FIXING_AGENT_PROMPT,
        _ => DEFAULT_AGENT_PROMPT,
    }
}
```

### 3. Card Chat History

The conversation history for this specific card. When history is too long, RLM summarization is applied:

```rust
struct CardChatHistory {
    messages: Vec<ChatMessage>,
    total_tokens: usize,
}

impl CardChatHistory {
    async fn to_context(&self, budget: usize, llm: &LLMService) -> String {
        if self.total_tokens <= budget {
            // Fits within budget - include full history
            self.format_full_history()
        } else {
            // Too long - apply RLM summarization
            self.summarize_with_rlm(budget, llm).await
        }
    }

    async fn summarize_with_rlm(&self, budget: usize, llm: &LLMService) -> String {
        let prompt = format!(
            "Summarize this conversation history for a coding task. \
             Preserve: key decisions, error messages, code that worked/failed, \
             current state of implementation. Be concise.\n\n{}",
            self.format_full_history()
        );

        llm.complete(&prompt).await
    }
}
```

**What to preserve in RLM summary:**
- Key user requirements and clarifications
- Errors encountered and their causes
- Code snippets that worked or failed
- Decisions made and rationale
- Current implementation state

### 4. Other Context

Supporting context assembled based on task needs:

```rust
struct OtherContext {
    notes: Vec<Note>,              // User-provided notes and requirements
    adrs: Vec<ADR>,                // Architecture Decision Records
    libraries: Vec<LibraryDoc>,    // Dependency documentation
    source_files: Vec<SourceFile>, // Relevant code files
    build_logs: Option<String>,    // GitHub Actions output
    pod_logs: Option<String>,      // Kubernetes pod logs
    test_results: Option<String>,  // Test output
}

impl OtherContext {
    fn assemble(&self, card: &Card, budget: usize) -> String {
        let mut context = String::new();
        let mut remaining = budget;

        // Priority 1: Notes (always include)
        if !self.notes.is_empty() {
            context.push_str(&self.format_notes());
            remaining -= self.notes_tokens();
        }

        // Priority 2: Error-related context (if in error-fixing state)
        if card.state == CardState::ErrorFixing {
            if let Some(logs) = &self.build_logs {
                context.push_str(&format!("## Build Logs\n```\n{}\n```\n", logs));
            }
            if let Some(logs) = &self.pod_logs {
                context.push_str(&format!("## Pod Logs\n```\n{}\n```\n", logs));
            }
        }

        // Priority 3: Relevant source files
        for file in self.source_files.iter().take_while(|_| remaining > 1000) {
            context.push_str(&file.format());
            remaining -= file.tokens();
        }

        // Priority 4: ADRs (if space permits)
        for adr in self.adrs.iter().take_while(|_| remaining > 500) {
            context.push_str(&adr.format());
            remaining -= adr.tokens();
        }

        context
    }
}
```

## Token Budget Management

Total token budget allocation:

| Section | Budget | Notes |
|---------|--------|-------|
| System Prompt | ~1,000 | Static |
| Agent Prompt | ~1,500 | Varies by stage |
| Chat History | ~10,000 | RLM summarized if exceeded |
| Other Context | ~15,000 | Prioritized by relevance |
| **Total** | **~27,500** | Leaves room for LLM response |

```rust
pub struct TokenBudget {
    pub system_prompt: usize,      // 1,000
    pub agent_prompt: usize,       // 1,500
    pub chat_history: usize,       // 10,000
    pub other_context: usize,      // 15,000
    pub total: usize,              // 27,500
}

impl Default for TokenBudget {
    fn default() -> Self {
        Self {
            system_prompt: 1_000,
            agent_prompt: 1_500,
            chat_history: 10_000,
            other_context: 15_000,
            total: 27_500,
        }
    }
}
```

## RLM Summarization Details

When chat history exceeds its token budget, RLM summarization condenses it:

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                           RLM SUMMARIZATION PROCESS                                   │
└──────────────────────────────────────────────────────────────────────────────────────┘

Original Chat History (50,000 tokens)
│
├── Message 1: User describes feature requirement
├── Message 2: LLM proposes implementation approach
├── Message 3: User clarifies edge case
├── Message 4: LLM writes initial code
├── Message 5: Error encountered - compilation failed
├── Message 6: LLM fixes compilation error
├── Message 7: User requests additional validation
├── ... (many more messages)
├── Message 47: Current state of implementation
│
▼
┌──────────────────────────────────────────────────────────────────────────────────────┐
│  RLM SUMMARIZATION PROMPT                                                             │
│                                                                                       │
│  "Summarize this conversation history for a coding task continuation.                 │
│   The developer needs to understand:                                                  │
│   - What was requested                                                                │
│   - Key decisions made                                                                │
│   - Errors encountered and how they were resolved                                     │
│   - Current state of the implementation                                               │
│   - What still needs to be done                                                       │
│                                                                                       │
│   Be concise but preserve technical details like error messages and code snippets     │
│   that are relevant to continuing the work."                                          │
└──────────────────────────────────────────────────────────────────────────────────────┘
│
▼
Summarized History (8,000 tokens)
│
├── ## Task Summary
│   User requested JWT authentication with token refresh...
│
├── ## Key Decisions
│   - Using jsonwebtoken crate for JWT handling
│   - Storing refresh tokens in Redis
│   - 15-minute access token expiry
│
├── ## Errors Resolved
│   - Fixed missing Deserialize derive on Claims struct
│   - Resolved Redis connection timeout issue
│
├── ## Current State
│   - Access token generation: ✓ Complete
│   - Token validation middleware: ✓ Complete
│   - Refresh token endpoint: In Progress
│   - Tests: Not started
│
└── ## Remaining Work
    - Complete refresh token endpoint
    - Add rate limiting
    - Write unit tests
```

## Implementation

```rust
// File: crates/pipeline/src/assembler.rs

pub struct PromptAssembler {
    system_prompt: String,
    agent_prompts: HashMap<CardState, String>,
    budget: TokenBudget,
    llm_service: Arc<LLMService>,  // For RLM summarization
}

impl PromptAssembler {
    pub async fn assemble(&self, card: &Card, context: &TaskContext) -> AssembledPrompt {
        let mut sections = Vec::new();

        // 1. System Prompt (static)
        sections.push(PromptSection {
            name: "system".to_string(),
            content: self.system_prompt.clone(),
            tokens: self.estimate_tokens(&self.system_prompt),
        });

        // 2. Coding Agent System Prompt (based on state)
        let agent_prompt = self.agent_prompts
            .get(&card.state)
            .unwrap_or(&self.agent_prompts[&CardState::Coding]);
        sections.push(PromptSection {
            name: "agent".to_string(),
            content: agent_prompt.clone(),
            tokens: self.estimate_tokens(agent_prompt),
        });

        // 3. Card Chat History (RLM if too long)
        let history_content = if context.chat_history.total_tokens > self.budget.chat_history {
            // Apply RLM summarization
            self.summarize_history(&context.chat_history).await
        } else {
            context.chat_history.format()
        };
        sections.push(PromptSection {
            name: "history".to_string(),
            content: history_content.clone(),
            tokens: self.estimate_tokens(&history_content),
        });

        // 4. Other Context (prioritized)
        let other_content = context.other.assemble(card, self.budget.other_context);
        sections.push(PromptSection {
            name: "context".to_string(),
            content: other_content.clone(),
            tokens: self.estimate_tokens(&other_content),
        });

        AssembledPrompt { sections }
    }

    async fn summarize_history(&self, history: &ChatHistory) -> String {
        let prompt = format!(
            "{}\n\n---\n\n{}",
            RLM_SUMMARIZATION_PROMPT,
            history.format()
        );

        self.llm_service.complete(&prompt).await.unwrap_or_else(|_| {
            // Fallback: truncate to recent messages
            history.truncate_to_recent(self.budget.chat_history)
        })
    }
}

const RLM_SUMMARIZATION_PROMPT: &str = r#"
Summarize this conversation history for a coding task continuation.
The developer needs to understand:
- What was requested
- Key decisions made
- Errors encountered and how they were resolved
- Current state of the implementation
- What still needs to be done

Be concise but preserve technical details like error messages and code snippets
that are relevant to continuing the work.
"#;
```

## Configuration

```toml
# config.toml

[prompt]
# Token budgets
system_prompt_budget = 1000
agent_prompt_budget = 1500
chat_history_budget = 10000
other_context_budget = 15000

# RLM settings
[prompt.rlm]
# Model to use for summarization (smaller = cheaper)
model = "claude-3-haiku"
# Trigger RLM when history exceeds this percentage of budget
threshold_percentage = 80

# Context priorities (higher = included first)
[prompt.context_priority]
notes = 100
build_logs = 90      # When in error-fixing state
pod_logs = 85        # When in error-fixing state
source_files = 80
test_results = 75
adrs = 50
libraries = 40
```

## Related Documentation

- [00-architecture-overview.md](./00-architecture-overview.md) - Overall system architecture
- [03-loop-manager.md](./03-loop-manager.md) - How prompts are used in the Ralph loop
- [09-heuristic-orchestration.md](./09-heuristic-orchestration.md) - Heuristic vs LLM responsibilities
