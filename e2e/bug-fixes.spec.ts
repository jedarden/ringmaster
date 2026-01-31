import { test, expect } from '@playwright/test';

test.describe('Bug Fixes', () => {
  test('Delete project works correctly', async ({ page, request }) => {
    // Create a project via API
    const createResponse = await request.post('http://localhost:8080/api/projects', {
      data: {
        name: 'Delete Test Project',
        description: 'Testing deletion fix',
        repositoryUrl: '/tmp/delete-test',
      }
    });
    expect(createResponse.ok()).toBeTruthy();
    const projectData = await createResponse.json();
    const projectId = projectData.data.id;

    // Go to projects page
    await page.goto('/projects');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);

    // Find the delete button for our project and click it
    page.on('dialog', dialog => dialog.accept()); // Auto-accept confirmation

    const deleteButton = page.locator(`text=Delete Test Project`).locator('..').locator('..').locator('button').last();
    await deleteButton.click();

    // Wait for deletion to complete
    await page.waitForTimeout(1000);

    // Verify project is removed from the list
    const projectExists = await page.locator('text=Delete Test Project').count();
    expect(projectExists).toBe(0);

    console.log('SUCCESS: Project deletion works!');
  });

  test('Dashboard page loads correctly', async ({ page }) => {
    // Create some test data first
    const apiContext = await page.context().request;

    // Create a project
    const projectResponse = await apiContext.post('http://localhost:8080/api/projects', {
      data: {
        name: 'Dashboard Test Project',
        description: 'For dashboard testing',
        repositoryUrl: '/tmp/dashboard-test',
      }
    });
    expect(projectResponse.ok()).toBeTruthy();
    const projectData = await projectResponse.json();

    // Create a card
    await apiContext.post('http://localhost:8080/api/cards', {
      data: {
        projectId: projectData.data.id,
        title: 'Dashboard Test Card',
        description: 'Testing dashboard',
        taskPrompt: 'Test the dashboard',
      }
    });

    // Go to dashboard page
    await page.goto('/dashboard');

    // Wait for page to load (not stuck on spinner)
    await page.waitForTimeout(3000);

    // Take screenshot
    await page.screenshot({ path: 'screenshots/dashboard-fixed.png' });

    // Check that dashboard content is visible, not just the spinner
    const hasContent = await page.locator('text=Dashboard').isVisible();
    const hasSpinnerOnly = await page.locator('.animate-spin').count() > 0 && !hasContent;

    if (hasSpinnerOnly) {
      console.log('FAIL: Dashboard stuck on spinner');
      throw new Error('Dashboard stuck on loading spinner');
    }

    // Verify stats cards are visible
    const totalCardsVisible = await page.locator('text=Total Cards').isVisible();
    expect(totalCardsVisible).toBeTruthy();

    console.log('SUCCESS: Dashboard loads correctly!');
  });
});
