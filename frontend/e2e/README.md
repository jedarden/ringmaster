# Ringmaster E2E Tests

Playwright-based end-to-end tests for the Ringmaster frontend.

## Quick Start

### Option 1: Run with auto-started servers (recommended for local dev)
```bash
cd frontend
npm run test:e2e
```

This will:
1. Start the Ringmaster backend API (via `start-backend-for-e2e.sh`)
2. Start the Vite dev server for the frontend
3. Run all E2E tests headless

### Option 2: Run with manually started servers
```bash
# Terminal 1: Start backend
cd /path/to/ringmaster
ringmaster init  # First time only
ringmaster serve

# Terminal 2: Run tests
cd frontend
npm run test:e2e
```

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

## Test Configuration

Tests run **serially** (not in parallel) to avoid:
- React Router race conditions
- Database conflicts from concurrent mutations
- WebSocket connection issues

See `playwright.config.ts` for full configuration.

## Test Data Management

Tests use helper functions in `e2e/helpers/test-api.ts` to:
- Create test projects, tasks, and workers via API
- Clean up test data before/after test runs
- Wait for backend to be ready

All test data is prefixed with "E2E" or "e2e" for easy identification.

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
2. Import test helpers from `./helpers/test-api`
3. Use `test.describe()` to group related tests
4. Use `test.beforeAll()` to set up test data
5. Use `test.afterAll()` to clean up test data
6. Use `test.beforeEach()` for per-test navigation
7. Use Playwright's locators for element selection
8. Run `npm run test:e2e` to execute

Example:
```typescript
import { test, expect } from '@playwright/test';
import { createTestProject, deleteTestProject, waitForBackend } from './helpers/test-api';

test.describe('My Feature', () => {
  test.beforeAll(async () => {
    await waitForBackend();
  });

  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
  });

  test('should do something', async ({ page }) => {
    // Your test code here
  });
});
```

## Debugging

```bash
# Run with debug mode (opens inspector)
npx playwright test --debug

# Run specific test file
npx playwright test e2e/project-crud.spec.ts

# Run specific test
npx playwright test -g "should create a new project"

# Show trace (after failed test)
npx playwright show-trace test-results/[test-name]/trace.zip
```

## Troubleshooting

### Backend not starting
- Check that Python 3.11+ is installed
- Run `ringmaster init` manually first
- Check port 8000 is not already in use

### Tests timing out
- Check backend health: `curl http://localhost:8000/health`
- Check frontend is running: `curl http://localhost:5173`
- Increase timeout in `playwright.config.ts` if needed

### "API: disconnected" in tests
- Backend is not running or not reachable
- Check browser console for WebSocket errors
- Verify CORS settings on backend
