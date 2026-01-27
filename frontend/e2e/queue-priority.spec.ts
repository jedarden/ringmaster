import { test, expect } from '@playwright/test';

/**
 * E2E tests for Queue and Priority Management
 * Tests the priority queue view and task prioritization
 */
test.describe('Queue & Priority', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/queue');
  });

  test('should display queue page', async ({ page }) => {
    // Should see queue page header
    await expect(page.getByRole('heading', { name: /queue/i })).toBeVisible();
  });

  test('should display ready tasks list', async ({ page }) => {
    // Should see ready tasks
    await expect(page.locator('.ready-tasks-list')).toBeVisible();
  });

  test('should show task priority badges', async ({ page }) => {
    // Ready tasks should have priority badges
    const readyTasks = page.locator('.ready-task-item');

    if (await readyTasks.count() > 0) {
      const firstTask = readyTasks.first();
      await expect(firstTask.locator('.priority-badge')).toBeVisible();
    }
  });

  test('should navigate from queue to project', async ({ page }) => {
    // Click on a ready task
    const readyTask = page.locator('.ready-task-item').first();

    if (await readyTask.isVisible()) {
      await readyTask.click();
      // Should navigate to project detail
      await expect(page).toHaveURL(/\/projects\/[a-z0-9]+/i);
    }
  });

  test('should display queue statistics', async ({ page }) => {
    // Should show queue stats
    await expect(page.locator('.queue-stats')).toBeVisible();
  });
});
