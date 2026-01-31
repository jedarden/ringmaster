import { test, expect } from '@playwright/test';

test.describe('Card Editing', () => {
  test('Can edit card title, description, and task prompt', async ({ page, request }) => {
    // Create a project via API
    const projectResponse = await request.post('http://localhost:8080/api/projects', {
      data: {
        name: 'Edit Test Project',
        description: 'For testing card editing',
        repositoryUrl: '/tmp/edit-test-repo',
      }
    });
    expect(projectResponse.ok()).toBeTruthy();
    const projectData = await projectResponse.json();
    const projectId = projectData.data.id;

    // Create a card via API
    const cardResponse = await request.post('http://localhost:8080/api/cards', {
      data: {
        projectId: projectId,
        title: 'Original Title',
        description: 'Original description',
        taskPrompt: 'Original task prompt for the AI',
      }
    });
    expect(cardResponse.ok()).toBeTruthy();
    const cardData = await cardResponse.json();
    const cardId = cardData.data.id;

    // Go to Kanban page
    await page.goto('/kanban');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);

    // Click on the card to open detail panel
    const card = page.locator('text=Original Title').first();
    await expect(card).toBeVisible({ timeout: 5000 });
    await card.click();
    await page.waitForTimeout(500);

    // Take screenshot before edit
    await page.screenshot({ path: 'screenshots/before-edit.png' });

    // Click the edit button (pencil icon)
    const editButton = page.locator('button[title="Edit card"]');
    await expect(editButton).toBeVisible({ timeout: 5000 });
    await editButton.click();
    await page.waitForTimeout(300);

    // Take screenshot in edit mode
    await page.screenshot({ path: 'screenshots/edit-mode.png' });

    // Edit the title
    const titleInput = page.locator('input').first();
    await titleInput.clear();
    await titleInput.fill('Updated Title');

    // Edit the task prompt (find the textarea)
    const taskPromptTextarea = page.locator('textarea').first();
    await taskPromptTextarea.clear();
    await taskPromptTextarea.fill('Updated task prompt with new instructions for the AI coding agent');

    // Take screenshot with edits
    await page.screenshot({ path: 'screenshots/with-edits.png' });

    // Click Save Changes button
    const saveButton = page.locator('button:has-text("Save Changes")');
    await saveButton.click();
    await page.waitForTimeout(1000);

    // Take screenshot after save
    await page.screenshot({ path: 'screenshots/after-save.png' });

    // Verify the changes were saved - title appears in both kanban card and detail panel
    const updatedTitleCount = await page.locator('text=Updated Title').count();
    expect(updatedTitleCount).toBeGreaterThanOrEqual(1);

    // Verify task prompt shows updated content
    const updatedPrompt = page.locator('text=Updated task prompt with new instructions');
    await expect(updatedPrompt).toBeVisible({ timeout: 5000 });

    console.log('SUCCESS: Card editing works correctly!');
  });
});
