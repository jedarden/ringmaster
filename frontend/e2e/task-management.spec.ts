import { test, expect } from '@playwright/test';

/**
 * E2E tests for Task Management operations
 * Tests creating, updating status, and managing tasks within a project
 */
test.describe('Task Management', () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to projects page and open first project
    await page.goto('/');
    await page.click('.project-card:first-child');
  });

  test('should display task input component', async ({ page }) => {
    // Should see the task input area
    await expect(page.locator('.task-input')).toBeVisible();
    await expect(page.locator('textarea[placeholder*="Enter a task"]')).toBeVisible();
  });

  test('should create a task via natural language input', async ({ page }) => {
    // Type a task description
    await page.fill('textarea[placeholder*="Enter a task"]', 'Add user authentication feature');

    // Submit the task
    await page.click('button:has-text("Create Task")');

    // Should see the new task in the ready column
    await expect(page.locator('.kanban-column.ready .task-card').filter({ hasText: 'user authentication' })).toBeVisible({ timeout: 5000 });
  });

  test('should change task status via dropdown', async ({ page }) => {
    // Find a task in the ready column
    const taskCard = page.locator('.kanban-column.ready .task-card').first();
    await taskCard.waitFor();

    // Click status dropdown
    await taskCard.locator('.status-dropdown').click();

    // Select "In Progress"
    await page.click('text=In Progress');

    // Task should move to in-progress column
    await expect(page.locator('.kanban-column.in-progress .task-card').first()).toBeVisible({ timeout: 3000 });
  });

  test('should display task details when clicking task card', async ({ page }) => {
    // Click on a task card
    await page.locator('.task-card').first().click();

    // Should see task details (might expand or show modal)
    await expect(page.locator('.task-details, .task-card.expanded')).toBeVisible();
  });

  test('should show task complexity badge', async ({ page }) => {
    // Navigate to a project with tasks
    const taskCard = page.locator('.task-card').first();
    await taskCard.waitFor();

    // Should see complexity badge
    await expect(taskCard.locator('.complexity-badge')).toBeVisible();
  });

  test('should display iteration count for in-progress tasks', async ({ page }) => {
    // Move a task to in-progress first
    const taskCard = page.locator('.kanban-column.ready .task-card').first();
    if (await taskCard.isVisible()) {
      await taskCard.locator('.status-dropdown').click();
      await page.click('text=In Progress');
    }

    // Should see iteration badge showing "1/X"
    const iterationBadge = page.locator('.kanban-column.in-progress .task-card').first().locator('.iteration-badge');
    await expect(iterationBadge).toBeVisible();
  });
});
