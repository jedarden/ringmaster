import { test, expect } from '@playwright/test';

test.describe('Card Interaction Tests', () => {
  test('Create project and card, verify click opens detail panel', async ({ page, request }) => {
    // First create a project via API
    const projectResponse = await request.post('http://localhost:8080/api/projects', {
      data: {
        name: 'Click Test Project',
        description: 'For testing clicks',
        repositoryUrl: '/tmp/test-repo',
      }
    });
    expect(projectResponse.ok()).toBeTruthy();
    const projectData = await projectResponse.json();
    const projectId = projectData.data.id;

    // Create a card via API
    const cardResponse = await request.post('http://localhost:8080/api/cards', {
      data: {
        projectId: projectId,
        title: 'Test Click Card',
        description: 'Testing click functionality',
        taskPrompt: 'Test the click feature',
      }
    });
    expect(cardResponse.ok()).toBeTruthy();

    // Now go to Kanban page
    await page.goto('/kanban');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);

    // Take screenshot of initial state
    await page.screenshot({ path: 'screenshots/kanban-with-card.png' });

    // Find the card
    const card = page.locator('text=Test Click Card').first();
    await expect(card).toBeVisible({ timeout: 5000 });

    // Click on the card
    await card.click();

    // Wait for the detail panel to open
    await page.waitForTimeout(500);

    // Take screenshot after click
    await page.screenshot({ path: 'screenshots/after-card-click.png' });

    // The CardDetailPanel should appear
    // Check for elements that should be in the detail panel
    const taskPromptVisible = await page.locator('text=Task Prompt').isVisible().catch(() => false);
    console.log('Task Prompt label visible:', taskPromptVisible);

    // Check if we can see the detail panel content
    const detailPanelContent = await page.locator('text=Test the click feature').isVisible().catch(() => false);
    console.log('Task prompt content visible:', detailPanelContent);

    // Success if task prompt is visible (it's in the detail panel)
    if (taskPromptVisible || detailPanelContent) {
      console.log('SUCCESS: Card detail panel opened on click!');
    } else {
      // Check what's visible
      const html = await page.content();
      console.log('Page contains "Task Prompt":', html.includes('Task Prompt'));
      console.log('Page contains "Test the click feature":', html.includes('Test the click feature'));
    }

    // The click should work - verify by finding content unique to the detail panel
    expect(taskPromptVisible || detailPanelContent).toBeTruthy();
  });
});
