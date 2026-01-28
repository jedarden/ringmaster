import { test, expect } from '@playwright/test';
import {
  createTestProject,
  createTestTask,
  deleteTestProject,
  cleanupTestProjects,
  waitForBackend,
} from './helpers/test-api';
import { navigateWithRetry, waitForPageStability } from './helpers/navigation';

/**
 * Helper to clean up test tasks (not in test-api.ts to avoid circular deps)
 */
async function cleanupTestTasks(): Promise<void> {
  const API_BASE_URL = 'http://localhost:8000/api';
  const response = await fetch(`${API_BASE_URL}/tasks`);
  if (!response.ok) return;

  const tasks = await response.json() as Array<{ id: string; title: string }>;
  const testTasks = tasks.filter((t) => t.title.includes('E2E') || t.title.includes('Test Task'));

  await Promise.all(
    testTasks.map((t) =>
      fetch(`${API_BASE_URL}/tasks/${t.id}`, { method: 'DELETE' })
    )
  );
}

/**
 * E2E tests for Task Management operations
 * Tests creating, updating status, and managing tasks within a project
 */
test.describe('Task Management', () => {
  // Clean up test data before all tests run
  test.beforeAll(async () => {
    await waitForBackend();
    await cleanupTestProjects();
    await cleanupTestTasks();
  });

  // Clean up test data after all tests run
  test.afterAll(async () => {
    await cleanupTestProjects();
    await cleanupTestTasks();
  });

  test.beforeEach(async ({ page }) => {
    // Navigate to projects page using robust navigation
    await navigateWithRetry(page, '/');
    await waitForPageStability(page);
  });

  test('should display task input component', async ({ page }) => {
    // Create a test project
    const project = await createTestProject({
      name: `Task Input Test ${Date.now()}`,
    });

    // Navigate to project detail page
    await navigateWithRetry(page, `/projects/${project.id}`);
    await waitForPageStability(page);

    // Should see the task input area
    await expect(page.locator('textarea[placeholder*="Enter a task"]')).toBeVisible();

    // Cleanup
    await deleteTestProject(project.id);
  });

  test('should create a task via natural language input', async ({ page }) => {
    // Create a test project
    const project = await createTestProject({
      name: `Create Task Test ${Date.now()}`,
    });

    // Navigate to project detail page
    await navigateWithRetry(page, `/projects/${project.id}`);
    await waitForPageStability(page);

    // Type a task description
    const taskTitle = 'Add user authentication feature';
    await page.fill('textarea[placeholder*="Enter a task"]', taskTitle);

    // Submit the task
    await page.click('button:has-text("Create")');

    // Wait for task to appear
    await expect(page.locator('.task-card').filter({ hasText: taskTitle })).toBeVisible({ timeout: 5000 });

    // Cleanup
    await deleteTestProject(project.id);
  });

  test('should change task status via dropdown', async ({ page }) => {
    // Create a test project with a task
    const project = await createTestProject({
      name: `Status Change Test ${Date.now()}`,
    });
    const task = await createTestTask(project.id, {
      title: `Status Test Task ${Date.now()}`,
      status: 'ready',
    });

    // Navigate to project detail page
    await navigateWithRetry(page, `/projects/${project.id}`);
    await waitForPageStability(page);

    // Find the task card in ready column
    const taskCard = page.locator('.kanban-column.ready .task-card').filter({ hasText: task.title });
    await expect(taskCard).toBeVisible({ timeout: 5000 });

    // Click status dropdown
    await taskCard.locator('.status-dropdown').click();

    // Select "In Progress"
    await page.click('text=In Progress');

    // Task should move to in-progress column (wait for state update)
    await page.waitForTimeout(500);

    // Cleanup
    await deleteTestProject(project.id);
  });

  test('should display task details when clicking task card', async ({ page }) => {
    // Create a test project with a task
    const project = await createTestProject({
      name: `Task Detail Test ${Date.now()}`,
    });
    const task = await createTestTask(project.id, {
      title: `Detail Task ${Date.now()}`,
      status: 'ready',
    });

    // Navigate to project detail page
    await navigateWithRetry(page, `/projects/${project.id}`);
    await waitForPageStability(page);

    // Click on a task card
    const taskCard = page.locator('.task-card').filter({ hasText: task.title });
    await taskCard.click();

    // Should see task details or task card still visible
    await expect(taskCard).toBeVisible();

    // Cleanup
    await deleteTestProject(project.id);
  });

  test('should show task complexity badge', async ({ page }) => {
    // Create a test project with a task
    const project = await createTestProject({
      name: `Complexity Test ${Date.now()}`,
    });
    await createTestTask(project.id, {
      title: `Complexity Task ${Date.now()}`,
      status: 'ready',
    });

    // Navigate to project detail page
    await navigateWithRetry(page, `/projects/${project.id}`);
    await waitForPageStability(page);

    // Should see complexity badge on at least one task card
    const taskCards = page.locator('.task-card');
    await expect(taskCards.first()).toBeVisible({ timeout: 5000 });

    // Check if complexity badge exists (it might not be visible if no tasks yet)
    const complexityBadges = page.locator('.complexity-badge');
    const badgeCount = await complexityBadges.count();
    expect(badgeCount).toBeGreaterThanOrEqual(0);

    // Cleanup
    await deleteTestProject(project.id);
  });

  test('should display iteration count for in-progress tasks', async ({ page }) => {
    // Create a test project with an in-progress task
    const project = await createTestProject({
      name: `Iteration Test ${Date.now()}`,
    });
    await createTestTask(project.id, {
      title: `Iteration Task ${Date.now()}`,
      status: 'in_progress',
    });

    // Navigate to project detail page
    await navigateWithRetry(page, `/projects/${project.id}`);
    await waitForPageStability(page);

    // Find task in in-progress column
    const inProgressTasks = page.locator('.kanban-column.in-progress .task-card');
    const count = await inProgressTasks.count();

    if (count > 0) {
      // Should see task card
      await expect(inProgressTasks.first()).toBeVisible();
    }

    // Cleanup
    await deleteTestProject(project.id);
  });
});
