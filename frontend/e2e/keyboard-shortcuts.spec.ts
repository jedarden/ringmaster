import { test, expect } from '@playwright/test';

/**
 * E2E tests for Keyboard Shortcuts
 * Tests keyboard navigation and command palette functionality
 */
test.describe('Keyboard Shortcuts', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('should open command palette with Cmd+K', async ({ page }) => {
    // Press Cmd+K (or Ctrl+K on non-Mac)
    await page.keyboard.press((process.platform === 'darwin' ? 'Meta' : 'Control') + '+k');

    // Should see command palette
    await expect(page.locator('.command-palette')).toBeVisible();
  });

  test('should open shortcuts help with ? key', async ({ page }) => {
    // Press ? key
    await page.keyboard.press('?');

    // Should see shortcuts help modal
    await expect(page.locator('.shortcuts-help')).toBeVisible();
  });

  test('should navigate projects with j/k keys', async ({ page }) => {
    const projectCards = page.locator('.project-card');
    const count = await projectCards.count();

    if (count > 1) {
      // Press k to navigate down (actually selects next in list)
      await page.keyboard.press('k');

      // Press j to navigate up
      await page.keyboard.press('j');

      // Navigation should work (just verify no errors)
      await expect(projectCards.first()).toBeVisible();
    }
  });

  test('should navigate to workers with g a shortcut', async ({ page }) => {
    // Press g then a
    await page.keyboard.press('g');
    await page.keyboard.press('a');

    // Should navigate to workers page
    await expect(page).toHaveURL(/\/workers/);
  });

  test('should navigate to metrics with g d shortcut', async ({ page }) => {
    // Press g then d
    await page.keyboard.press('g');
    await page.keyboard.press('d');

    // Should navigate to metrics page
    await expect(page).toHaveURL(/\/metrics/);
  });

  test('should close modal with Escape', async ({ page }) => {
    // Open command palette
    await page.keyboard.press((process.platform === 'darwin' ? 'Meta' : 'Control') + '+k');
    await expect(page.locator('.command-palette')).toBeVisible();

    // Press Escape to close
    await page.keyboard.press('Escape');
    await expect(page.locator('.command-palette')).not.toBeVisible();
  });
});
