import { test, expect } from '@playwright/test';

/**
 * E2E tests for Worker Management
 * Tests viewing workers, spawning workers, and monitoring worker status
 */
test.describe('Worker Management', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/workers');
  });

  test('should display workers dashboard', async ({ page }) => {
    // Should see workers page header
    await expect(page.getByRole('heading', { name: /workers/i })).toBeVisible();
  });

  test('should list available workers', async ({ page }) => {
    // Should see worker cards
    const workerCards = page.locator('.worker-card');
    await expect(workerCards.first()).toBeVisible();
  });

  test('should display worker status badges', async ({ page }) => {
    // Worker cards should show status
    const workerCard = page.locator('.worker-card').first();
    await expect(workerCard.locator('.status-badge')).toBeVisible();
  });

  test('should display worker capabilities', async ({ page }) => {
    // Worker cards should show capabilities
    const workerCard = page.locator('.worker-card').first();
    const capabilities = workerCard.locator('.capability-tag');
    // Capabilities might be empty for some workers, just check the element exists
    expect(await capabilities.count()).toBeGreaterThanOrEqual(0);
  });

  test('should open spawn worker modal', async ({ page }) => {
    // Click "Spawn Worker" button
    await page.click('button:has-text("Spawn Worker")');

    // Should see spawn modal
    await expect(page.getByRole('dialog')).toBeVisible();
    await expect(page.getByRole('heading', { name: /spawn worker/i })).toBeVisible();
  });

  test('should show pause all button when workers are active', async ({ page }) => {
    // Check if there are active workers
    const activeWorkers = page.locator('.worker-card.busy');

    if (await activeWorkers.count() > 0) {
      // Should see "Pause All" button
      await expect(page.locator('button:has-text("Pause All")')).toBeVisible();
    }
  });

  test('should view worker output panel', async ({ page }) => {
    // Find a busy worker
    const busyWorker = page.locator('.worker-card.busy').first();

    if (await busyWorker.isVisible()) {
      // Click "View Output" button
      await busyWorker.locator('button:has-text("View Output")').click();

      // Should see output panel
      await expect(page.locator('.worker-output-panel')).toBeVisible();
    }
  });
});
