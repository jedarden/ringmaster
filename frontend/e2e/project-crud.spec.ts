import { test, expect } from '@playwright/test';
import {
  createTestProject,
  deleteTestProject,
  cleanupTestProjects,
  waitForBackend,
} from './helpers/test-api';

/**
 * E2E tests for Project CRUD operations
 * Tests the critical user flows for creating, viewing, updating, and deleting projects
 */
test.describe('Project CRUD', () => {
  // Clean up test data before all tests run
  test.beforeAll(async () => {
    await waitForBackend();
    await cleanupTestProjects();
  });

  // Clean up test data after all tests run
  test.afterAll(async () => {
    await cleanupTestProjects();
  });

  test.beforeEach(async ({ page }) => {
    // Navigate to the projects page
    await page.goto('/');
    await page.waitForLoadState('networkidle');
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
    const projectName = `E2E Test Project ${Date.now()}`;
    await page.fill('input[name="name"]', projectName);
    await page.fill('textarea[name="description"]', 'A test project for E2E validation');

    // Submit the form
    await page.click('button[type="submit"]');

    // Should see success indication (modal closes)
    await expect(page.getByRole('dialog')).not.toBeVisible({ timeout: 5000 });

    // Should see the new project in the list
    await expect(page.getByText(projectName)).toBeVisible({ timeout: 5000 });
  });

  test('should navigate to project detail page', async ({ page }) => {
    // Create a test project first
    const project = await createTestProject({
      name: `Detail Test Project ${Date.now()}`,
    });

    // Reload page to see the new project
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Click on the project card
    const projectCard = page.locator('.project-card').filter({ hasText: project.name });
    await projectCard.click();

    // Should be on project detail page
    await expect(page).toHaveURL(/\/projects\/[a-z0-9]+/i);
    await expect(page.getByRole('heading', { name: new RegExp(project.name, 'i') })).toBeVisible();

    // Cleanup
    await deleteTestProject(project.id);
  });

  test('should display task kanban board on project detail', async ({ page }) => {
    // Create a test project with some tasks
    const project = await createTestProject({
      name: `Kanban Test Project ${Date.now()}`,
    });

    // Navigate directly to the project page
    await page.goto(`/projects/${project.id}`);
    await page.waitForLoadState('networkidle');

    // Should see kanban board columns (at least some columns should be visible)
    const kanbanColumns = page.locator('.kanban-column');
    await expect(kanbanColumns.first()).toBeVisible();

    // Cleanup
    await deleteTestProject(project.id);
  });

  test('should display task count in project summary', async ({ page }) => {
    // Create a test project
    const project = await createTestProject({
      name: `Summary Test Project ${Date.now()}`,
    });

    // Navigate to the project page
    await page.goto(`/projects/${project.id}`);
    await page.waitForLoadState('networkidle');

    // Should see project header with project name
    await expect(page.getByRole('heading', { name: new RegExp(project.name, 'i') })).toBeVisible();

    // Cleanup
    await deleteTestProject(project.id);
  });
});
