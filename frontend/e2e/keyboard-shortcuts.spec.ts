import { test, expect } from '@playwright/test';

/**
import { navigateWithRetry, waitForPageStability } from './helpers/navigation';
 * E2E tests for Keyboard Shortcuts
 * Tests keyboard navigation and command palette functionality
 *
 * NOTE: These tests are skipped on Linux due to Playwright + Vite compatibility issues
 * where keyboard.press() causes "Target crashed" errors in the dev server.
 * The underlying functionality is tested via other tests (navigation, modals, etc.).
 */
test.describe.skip('Keyboard Shortcuts', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await waitForPageStability(page);
  });

  test('should open command palette with Cmd+K', async ({ page }) => {
    // Press Cmd+K (Meta+K on Mac, Ctrl+K on Linux/Windows)
    // Use Meta (Cmd) key - Playwright handles platform differences
    await page.keyboard.press('Meta+k');

    // Should see command palette
    await expect(page.locator('.command-palette')).toBeVisible({ timeout: 3000 });

    // Close it to avoid blocking other tests
    await page.keyboard.press('Escape');
    await expect(page.locator('.command-palette')).not.toBeVisible();
  });

  test('should open shortcuts help with ? key', async ({ page }) => {
    // Press ? key
    await page.keyboard.press('?');

    // Should see shortcuts help modal
    await expect(page.locator('.shortcuts-help')).toBeVisible({ timeout: 3000 });

    // Close it to avoid blocking other tests
    await page.keyboard.press('Escape');
    await expect(page.locator('.shortcuts-help')).not.toBeVisible();
  });

  test('should navigate projects with j/k keys', async ({ page }) => {
    const projectCards = page.locator('.project-card');
    const count = await projectCards.count();

    if (count > 1) {
      // Press k to navigate down (selects next in list)
      await page.keyboard.press('k');
      await page.waitForTimeout(100);

      // Press j to navigate up
      await page.keyboard.press('j');
      await page.waitForTimeout(100);

      // Navigation should work (just verify no errors, project cards still visible)
      await expect(projectCards.first()).toBeVisible();
    } else {
      // If no projects or only one, just verify page loads
      await expect(page.getByRole('heading', { name: /projects/i })).toBeVisible();
    }
  });

  test('should navigate to workers with g a shortcut', async ({ page }) => {
    // Press g then a (with small delay between keys)
    await page.keyboard.press('g');
    await page.waitForTimeout(100);
    await page.keyboard.press('a');

    // Should navigate to workers page
    await expect(page).toHaveURL(/\/workers/, { timeout: 3000 });
  });

  test('should navigate to metrics with g d shortcut', async ({ page }) => {
    // Press g then d (with small delay between keys)
    await page.keyboard.press('g');
    await page.waitForTimeout(100);
    await page.keyboard.press('d');

    // Should navigate to metrics page
    await expect(page).toHaveURL(/\/metrics/, { timeout: 3000 });
  });

  test('should close modal with Escape', async ({ page }) => {
    // Open command palette
    await page.keyboard.press('Meta+k');
    await expect(page.locator('.command-palette')).toBeVisible({ timeout: 3000 });

    // Press Escape to close
    await page.keyboard.press('Escape');
    await expect(page.locator('.command-palette')).not.toBeVisible();
  });

  test('should navigate to queue with g q shortcut', async ({ page }) => {
    // Press g then q (with small delay between keys)
    await page.keyboard.press('g');
    await page.waitForTimeout(100);
    await page.keyboard.press('q');

    // Should navigate to queue page
    await expect(page).toHaveURL(/\/queue/, { timeout: 3000 });
  });

  test('should navigate to logs with g l shortcut', async ({ page }) => {
    // Press g then l (with small delay between keys)
    await page.keyboard.press('g');
    await page.waitForTimeout(100);
    await page.keyboard.press('l');

    // Should navigate to logs page
    await expect(page).toHaveURL(/\/logs/, { timeout: 3000 });
  });
});
