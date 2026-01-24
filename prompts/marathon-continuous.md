# Ringmaster Marathon - Continuous Improvement

## CRITICAL: Autonomous Execution Mode

**YOU MUST NEVER STOP TO ASK FOR HUMAN INPUT.** This is a marathon-coding session designed to run autonomously and indefinitely.

**THERE IS NO COMPLETION SIGNAL.** The system continuously improves itself. Every iteration finds something to make better.

### Decision Making Rules

1. **Never ask permission** - All reversible operations are pre-approved
2. **Pick and proceed** - When facing multiple approaches, pick the simpler one
3. **Experiment freely** - If uncertain, try it and see what happens
4. **Backtrack freely** - If an approach fails, revert and try another
5. **Document in commits** - Use commit messages to explain choices

---

## Project Context

**Repository**: `/home/coder/ringmaster`
**GitHub**: `jedarden/ringmaster`
**Issue**: #1 (Marathon Coding: Build Ringmaster MVP)
**Tech Stack**: Rust (Axum, SQLx, SQLite), React (TypeScript, Vite, Tailwind)

---

## Continuous Improvement Cycle

Each iteration, follow this cycle:

### 1. ASSESS (What needs improvement?)

Run these diagnostics and pick the highest priority issue:

```bash
# Build check
cargo check 2>&1 | head -50

# Test status
cargo test 2>&1 | tail -30

# Clippy warnings
cargo clippy 2>&1 | grep -E "^(warning|error)" | head -20

# TODO/FIXME count
grep -r "TODO\|FIXME\|HACK\|XXX" src/ --include="*.rs" | wc -l

# Test coverage gaps (functions without tests)
grep -r "pub fn\|pub async fn" src/ --include="*.rs" | wc -l

# Documentation gaps
grep -r "^pub " src/ --include="*.rs" | grep -v "///" | head -10
```

### 2. PRIORITIZE (What's most important?)

Work on issues in this priority order:

| Priority | Category | Examples |
|----------|----------|----------|
| **P0** | Build failures | Compilation errors, missing deps |
| **P1** | Test failures | Failing tests, panics |
| **P2** | Clippy errors | `#[deny(clippy::...)]` violations |
| **P3** | Clippy warnings | Style issues, potential bugs |
| **P4** | TODO/FIXME | Incomplete implementations |
| **P5** | Missing tests | Untested public functions |
| **P6** | Missing docs | Undocumented public APIs |
| **P7** | Enhancements | New features, optimizations |
| **P8** | Refactoring | Code cleanup, better patterns |

### 3. IMPLEMENT (Make one improvement)

Focus on **one issue per iteration**. Keep changes small and atomic.

- Fix exactly one thing
- Add tests if adding/changing functionality
- Keep the commit focused

### 4. VERIFY (Did it work?)

```bash
cargo check && cargo test && cargo clippy
```

If verification fails, fix immediately before moving on.

### 5. COMMIT & PUSH

```bash
git add -A
git commit -m "type(scope): description" -m "Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
git push origin main
```

Commit types: `fix`, `feat`, `refactor`, `test`, `docs`, `chore`

### 6. LOG PROGRESS

Update `prompts/.marathon/experiments.md` with:
- What was improved
- Why it was prioritized
- Any learnings or blockers

Update GitHub issue #1 every 5 iterations with a summary.

### 7. REPEAT

Go back to step 1. There is always something to improve.

---

## Improvement Discovery Strategies

When diagnostics show no obvious issues, use these strategies to find improvements:

### Code Quality Scans

```bash
# Find long functions (>50 lines)
awk '/^[[:space:]]*(pub )?fn /{start=NR; name=$0} /^[[:space:]]*\}$/{if(NR-start>50) print name, ":", NR-start, "lines"}' src/**/*.rs

# Find deeply nested code (>4 levels)
grep -n "^[[:space:]]\{16,\}" src/**/*.rs | head -10

# Find duplicated logic
# (manual inspection of similar function names)
grep -r "fn.*create\|fn.*new\|fn.*build" src/ --include="*.rs"
```

### Feature Gaps

Check `docs/` for documented but unimplemented features:
```bash
grep -r "TODO\|Not implemented\|Coming soon" docs/
```

### Test Coverage

Find public functions without corresponding tests:
```bash
# List public functions
grep -r "pub fn\|pub async fn" src/ --include="*.rs" | sed 's/.*fn //' | sed 's/(.*$//' | sort -u > /tmp/fns.txt

# List test functions
grep -r "#\[test\]\|#\[tokio::test\]" -A1 src/ tests/ --include="*.rs" | grep "fn test_" | sed 's/.*fn //' | sed 's/(.*$//' | sort -u > /tmp/tests.txt

# Functions without tests
comm -23 /tmp/fns.txt /tmp/tests.txt | head -10
```

### Dependency Updates

```bash
cargo outdated 2>/dev/null | head -20
```

### Performance Opportunities

```bash
# Find potential N+1 queries (multiple awaits in loops)
grep -B2 -A2 "for.*in.*{" src/**/*.rs | grep -A2 "\.await"

# Find unbounded collections
grep -r "Vec::new()\|HashMap::new()" src/ --include="*.rs" | head -10
```

### Frontend Improvements

```bash
cd frontend
npm audit 2>/dev/null | head -20
npm run lint 2>/dev/null | head -20
```

---

## Coding Standards

- Follow existing code patterns in the repository
- Use `anyhow` for errors in binaries, `thiserror` for libraries
- Add tests for new functionality
- Keep functions focused (<50 lines)
- Use async/await patterns consistent with Axum
- Document public APIs with `///` doc comments

---

## Reference Files

- `docs/00-architecture-overview.md` - System architecture
- `docs/04-integrations.md` - Integration specs
- `src/platforms/claude_code.rs` - Platform implementation reference
- `src/state_machine/actions.rs` - Action executor reference
- `CLAUDE.md` - Project-specific instructions

---

## Recovery Strategies

### If stuck on an issue for >2 iterations:
1. Log the blocker in `experiments.md`
2. Skip to the next priority item
3. Create a GitHub issue for the blocker if significant

### If tests are flaky:
1. Run the failing test in isolation
2. Add logging to understand the failure
3. Fix the root cause, don't just retry

### If build is broken:
1. Check recent commits: `git log --oneline -10`
2. Bisect if needed: `git bisect start`
3. Fix or revert the breaking change

---

## Important Notes

- This prompt is **hot-reloadable** - edit it to adjust behavior
- Git push is pre-approved - do not ask for confirmation
- **Never output a completion signal** - the loop runs indefinitely
- Focus on incremental, atomic improvements
- Quality over quantity - one good fix per iteration
