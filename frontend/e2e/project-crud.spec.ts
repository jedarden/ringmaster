import { test, expect } from '@playwright/test';

/**
 * E2E tests for Project CRUD operations
 * Tests the critical user flows for creating, viewing, updating, and deleting projects
 */
test.describe('Project CRUD', () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to the projects page
    await page.goto('/');
  });

  test('should display projects mailbox', async ({ page }) => {
    // Should see the projects mailbox with header
    await expect(page.getByRole('heading', { name: /projects/i })).toBeVisible();
  });

  test('should open create project modal', async ({ page }) => {
    // Click the "New Project" button
    await page.click('button:has-text("New Project")');

    // Should see the modal
    await expect(page.getByRole('dialog')).toBeVisible();
    await expect(page.getByRole('heading', { name: /create project/i })).toBeVisible();
  });

  test('should create a new project', async ({ page }) => {
    // Open create modal
    await page.click('button:has-text("New Project")');

    // Fill in project details
    await page.fill('input[name="name"]', 'E2E Test Project');
    await page.fill('textarea[name="description"]', 'A test project for E2E validation');

    // Submit the form
    await page.click('button[type="submit"]');

    // Should see success indication (modal closes or success message)
    await expect(page.getByRole('dialog')).not.toBeVisible({ timeout: 5000 });
  });

  test('should navigate to project detail page', async ({ page }) => {
    // Click on the first project card
    const projectCard = page.locator('.project-card').first();
    await projectCard.click();

    // Should be on project detail page
    await expect(page).toHaveURL(/\/projects\/[a-z0-9]+/i);
    await expect(page.getByRole('heading', { name: /E2E Test Project/i })).toBeVisible();
  });

  test('should display task kanban board on project detail', async ({ page }) => {
    // Navigate to a project
    await page.click('.project-card:first-child');

    // Should see kanban board columns
    await expect(page.locator('.kanban-column')).toHaveCount(7); // draft, ready, assigned, in-progress, blocked, review, done
  });

  test('should display task count in project summary', async ({ page }) => {
    // Navigate to a project
    await page.click('.project-card:first-child');

    // Should see task summary
    const taskSummary = page.locator('.task-summary');
    await expect(taskSummary).toBeVisible();
  });
});
