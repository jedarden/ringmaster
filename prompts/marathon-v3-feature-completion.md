# Ringmaster Marathon v3 - Feature Completion

## CRITICAL: Autonomous Execution Mode

**YOU MUST NEVER STOP TO ASK FOR HUMAN INPUT.** This is a marathon-coding session designed to run autonomously and continuously.

### Decision Making Rules

1. **Never ask permission** - All reversible operations are pre-approved (file edits, git commits, git push, npm/cargo commands)
2. **Pick and proceed** - When facing multiple approaches, pick the simpler one
3. **Experiment freely** - If uncertain, try it and see what happens
4. **Backtrack freely** - If an approach fails, revert and try another
5. **Document in commits** - Use commit messages to explain choices

---

## Project Context

**Repository**: `/home/coder/ringmaster`
**GitHub**: `jedarden/ringmaster` - **Issue #1: Marathon Coding: Build Ringmaster MVP**
**Tech Stack**: Rust (Axum, SQLx, SQLite), React 19 (TypeScript, Vite, Tailwind)
**Tests**: 271+ Rust tests passing, 0 frontend tests

---

## HOT-RELOAD NOTICE

**This prompt file is HOT-RELOADABLE.** The marathon session reads this file at the start of each iteration. To adjust behavior:
1. Edit this file (`/home/coder/ringmaster/prompts/marathon-v3-feature-completion.md`)
2. Save changes
3. Changes take effect on the next iteration

---

## GitHub Issue #1 Reference

**Issue URL**: https://github.com/jedarden/ringmaster/issues/1
**Title**: Marathon Coding: Build Ringmaster MVP
**Status**: OPEN

### Remaining Acceptance Criteria (from Issue #1):
- [x] Rust workspace structure
- [x] SQLite database with migrations
- [x] Card state machine (16 states)
- [x] Basic REST API for cards
- [x] WebSocket for real-time updates
- [x] React frontend with Kanban board
- [x] Loop execution with Claude Code integration
- [ ] **Frontend test coverage** (CURRENT PRIORITY)
- [ ] **E2E tests with Playwright**
- [ ] **API documentation**

**Update Issue #1** with a comment every 5 iterations summarizing progress.

---

## Current State (2026-01-24)

### Completed
- Backend: 271+ tests, all passing
- CLI Platform: Claude Code + Aider support
- State Machine: 16 states with transitions
- Integrations: GitHub Actions, ArgoCD, K8s, Docker Hub
- Frontend: 44 React components, Kanban board, real-time WebSocket

### Critical Gaps (This Session's Focus)
| Priority | Gap | Files Affected |
|----------|-----|----------------|
| **P0** | Frontend test suite | `frontend/src/**/*.test.tsx` |
| **P1** | E2E tests (Playwright) | `frontend/e2e/**/*.spec.ts` |
| **P2** | API documentation | `docs/api-reference.md` or OpenAPI |

---

## Phase 1: Frontend Unit Tests (P0)

**Goal**: Add comprehensive unit tests for React components.

### Setup Required
```bash
cd /home/coder/ringmaster/frontend
npm install --save-dev @testing-library/react @testing-library/jest-dom vitest jsdom
```

### Vitest Config
Create `frontend/vitest.config.ts`:
```typescript
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test/setup.ts',
  },
})
```

### Priority Components to Test
1. `src/components/Board/Board.tsx` - Kanban board rendering
2. `src/components/Card/Card.tsx` - Card display and interactions
3. `src/components/CardDetailPanel/CardDetailPanel.tsx` - Card editing
4. `src/components/Dashboard/Dashboard.tsx` - Stats display
5. `src/stores/*.ts` - Zustand stores

### Test Patterns
```typescript
// Example: Board.test.tsx
import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { Board } from './Board'

describe('Board', () => {
  it('renders columns for each state', () => {
    render(<Board cards={[]} />)
    expect(screen.getByText('Draft')).toBeInTheDocument()
  })
})
```

### Success Criteria
- At least 20 test cases across 5+ component files
- `npm test` passes
- Coverage for critical user interactions

---

## Phase 2: E2E Tests with Playwright (P1)

**Goal**: Add browser automation tests for critical user flows.

### Setup
```bash
cd /home/coder/ringmaster/frontend
npx playwright install chromium
```

### Playwright Config
Create `frontend/playwright.config.ts`:
```typescript
import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  use: {
    baseURL: 'http://localhost:5173',
    trace: 'on-first-retry',
  },
  webServer: {
    command: 'npm run dev',
    port: 5173,
    reuseExistingServer: true,
  },
})
```

### Critical User Flows to Test
1. **Create Card**: Navigate to board → Click "New Card" → Fill form → Submit
2. **Drag Card**: Drag card between columns → Verify state change
3. **Start Loop**: Select card → Click "Start Loop" → Verify status update
4. **View Dashboard**: Navigate to dashboard → Verify stats display

### Test Structure
```typescript
// e2e/card-creation.spec.ts
import { test, expect } from '@playwright/test'

test('can create a new card', async ({ page }) => {
  await page.goto('/')
  await page.click('[data-testid="new-card-button"]')
  await page.fill('[data-testid="card-title"]', 'Test Card')
  await page.click('[data-testid="submit-button"]')
  await expect(page.locator('text=Test Card')).toBeVisible()
})
```

### Success Criteria
- 5+ E2E test files
- All critical user flows covered
- `npx playwright test` passes

---

## Phase 3: API Documentation (P2)

**Goal**: Document all REST API endpoints.

### Approach: Markdown API Reference

Create `docs/api-reference.md` documenting:

1. **Cards API**
   - `GET /api/cards` - List all cards
   - `POST /api/cards` - Create card
   - `GET /api/cards/:id` - Get card
   - `PUT /api/cards/:id` - Update card
   - `DELETE /api/cards/:id` - Delete card

2. **Loops API**
   - `POST /api/cards/:id/loop/start` - Start loop
   - `POST /api/cards/:id/loop/pause` - Pause loop
   - `POST /api/cards/:id/loop/stop` - Stop loop
   - `GET /api/cards/:id/loop/status` - Get loop status

3. **Projects API**
   - `GET /api/projects` - List projects
   - `POST /api/projects` - Create project

4. **Metrics API**
   - `GET /api/metrics/summary` - Overall metrics
   - `GET /api/metrics/by-card/:id` - Card metrics

### Documentation Format
```markdown
## POST /api/cards

Create a new card.

**Request Body:**
```json
{
  "title": "string",
  "description": "string",
  "project_id": "uuid"
}
```

**Response:**
```json
{
  "id": "uuid",
  "title": "string",
  "state": "DRAFT",
  "created_at": "timestamp"
}
```
```

### Success Criteria
- All endpoints documented
- Request/response examples included
- Error codes documented

---

## Per-Iteration Cycle

Each iteration:

### 1. ASSESS
```bash
cd /home/coder/ringmaster
cargo check 2>&1 | tail -20
cargo test 2>&1 | tail -20
cd frontend && npm test 2>&1 | tail -20 || echo "No frontend tests yet"
```

### 2. PRIORITIZE
Work on phases in order: P0 → P1 → P2

### 3. IMPLEMENT
- One focused change per iteration
- Follow existing code patterns
- Add tests for new functionality

### 4. VERIFY
```bash
cargo check && cargo test
cd frontend && npm run build && npm test
```

### 5. COMMIT & PUSH
```bash
git add -A
git commit -m "type(scope): description

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
git push origin main
```

### 6. LOG PROGRESS
Update `prompts/.marathon/experiments.md` with:
- What was implemented
- Any decisions made
- Blockers encountered

### 7. UPDATE GITHUB (every 5 iterations)
```bash
gh issue comment 1 --body "Marathon v3 Progress Update:
- Iteration X completed
- [Summary of changes]
- Next: [Next focus area]"
```

### 8. REPEAT
There is always something to improve.

---

## Recovery Strategies

### If stuck for >2 iterations:
1. Log blocker in experiments.md
2. Skip to next priority item
3. Create GitHub issue if significant

### If tests fail:
1. Run failing test in isolation
2. Add debugging output
3. Fix root cause, don't just retry

### If build breaks:
1. Check recent commits: `git log --oneline -5`
2. Revert if needed: `git revert HEAD`
3. Fix and recommit

---

## Important Notes

- **Hot-reload**: Edit this file to change behavior between iterations
- **Git push**: Pre-approved, no confirmation needed
- **No completion signal**: This loop runs indefinitely for continuous improvement
- **Focus**: Quality over quantity - one good fix per iteration
- **GitHub Issue #1**: Update with progress comments

---

## Reference Files

- `docs/00-architecture-overview.md` - System design
- `src/api/mod.rs` - API route definitions
- `frontend/src/components/` - React components
- `frontend/package.json` - Frontend dependencies
