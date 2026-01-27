# Ringmaster E2E Tests

Playwright-based end-to-end tests for the Ringmaster frontend.

## Prerequisites

1. Backend API server running on `http://localhost:8000`
2. Database initialized with test data

## Running Tests

### Run all E2E tests (headless)
```bash
npm run test:e2e
```

### Run tests with UI (interactive mode)
```bash
npm run test:e2e:ui
```

### Run tests in headed mode (see browser)
```bash
npm run test:e2e:headed
```

## Test Suites

### `project-crud.spec.ts`
- Tests project creation, viewing, and navigation
- Validates project mailbox display
- Tests project detail page loading

### `task-management.spec.ts`
- Tests natural language task creation
- Validates task status changes
- Tests task details display
- Validates complexity badges and iteration counts

### `worker-management.spec.ts`
- Tests workers dashboard display
- Validates worker status badges
- Tests worker capabilities display
- Validates spawn worker modal

### `queue-priority.spec.ts`
- Tests priority queue view
- Validates ready tasks list
- Tests task priority badges
- Validates navigation from queue to project

### `keyboard-shortcuts.spec.ts`
- Tests command palette (Cmd+K)
- Validates shortcuts help (?)
- Tests j/k navigation
- Validates g-letter shortcuts for navigation

### `realtime-updates.spec.ts`
- Tests WebSocket connection status
- Validates metrics dashboard
- Tests logs viewer live mode
- Validates events timeline

## Adding New Tests

1. Create a new spec file in `frontend/e2e/`
2. Use `test.describe()` to group related tests
3. Use `test.beforeEach()` for common setup
4. Use Playwright's locators for element selection
5. Run `npm run test:e2e` to execute

## Debugging

```bash
# Run with debug mode
npx playwright test --debug

# Run specific test file
npx playwright test e2e/project-crud.spec.ts

# Run specific test
npx playwright test -g "should create a new project"
```
