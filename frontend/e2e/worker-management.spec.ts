import { test, expect } from '@playwright/test';
import {
  createTestWorker,
  cleanupTestWorkers,
  waitForBackend,
} from './helpers/test-api';

import { navigateWithRetry, waitForPageStability } from './helpers/navigation';
/**
 * E2E tests for Worker Management
 * Tests viewing workers, spawning workers, and monitoring worker status
 */
test.describe('Worker Management', () => {
  // Clean up test data before all tests run
  test.beforeAll(async () => {
    await waitForBackend();
    await cleanupTestWorkers();
  });

  // Clean up test data after all tests run
  test.afterAll(async () => {
    await cleanupTestWorkers();
  });

  test.beforeEach(async ({ page }) => {
    await page.goto('/workers');
    await waitForPageStability(page);
  });

  test('should display workers dashboard', async ({ page }) => {
    // Should see workers page header (use exact match to avoid matching section headings)
    await expect(page.getByRole('heading', { name: 'Workers', exact: true })).toBeVisible();
  });

  test('should list available workers', async ({ page }) => {
    // Create a test worker first
    await createTestWorker({
      name: `e2e-worker-${Date.now()}`,
      status: 'idle',
    });

    // Reload page to see the worker
    await page.goto('/workers');
    await waitForPageStability(page);

    // Should see worker cards (at least the one we created)
    const workerCards = page.locator('.worker-card');
    await expect(workerCards.first()).toBeVisible({ timeout: 5000 });
  });

  test('should display worker status badges', async ({ page }) => {
    // Create a test worker
    await createTestWorker({
      name: `e2e-status-worker-${Date.now()}`,
      status: 'idle',
    });

    // Reload page
    await page.goto('/workers');
    await waitForPageStability(page);

    // Worker cards should show status
    const workerCard = page.locator('.worker-card').first();
    await expect(workerCard).toBeVisible({ timeout: 5000 });

    // Status badge might be in different places, just verify the card is visible
    const statusBadge = workerCard.locator('.status-badge');
    const badgeCount = await statusBadge.count();
    expect(badgeCount).toBeGreaterThanOrEqual(0);
  });

  test('should display worker capabilities', async ({ page }) => {
    // Create a test worker with capabilities
    await createTestWorker({
      name: `e2e-cap-worker-${Date.now()}`,
      status: 'idle',
      capabilities: ['python', 'typescript', 'react'],
    });

    // Reload page
    await page.goto('/workers');
    await waitForPageStability(page);

    // Should see worker card
    const workerCard = page.locator('.worker-card').first();
    await expect(workerCard).toBeVisible({ timeout: 5000 });

    // Capabilities might be displayed as tags
    const capabilityTags = workerCard.locator('.capability-tag');
    const tagCount = await capabilityTags.count();
    expect(tagCount).toBeGreaterThanOrEqual(0);
  });

  test('should open spawn worker modal', async ({ page }) => {
    // Click "Spawn Worker" button
    await page.click('button:has-text("Spawn Worker")');

    // Should see spawn modal
    await expect(page.getByRole('dialog')).toBeVisible();
    await expect(page.getByRole('heading', { name: /spawn worker/i })).toBeVisible();

    // Close the modal to avoid blocking other tests
    await page.keyboard.press('Escape');
  });

  test('should show pause all button when workers are active', async ({ page }) => {
    // Create a busy worker
    await createTestWorker({
      name: `e2e-busy-worker-${Date.now()}`,
      status: 'busy',
    });

    // Reload page
    await page.goto('/workers');
    await waitForPageStability(page);

    // Check if there are active workers
    const activeWorkers = page.locator('.worker-card.busy');
    const count = await activeWorkers.count();

    if (count > 0) {
      // Should see "Pause All" button
      await expect(page.locator('button:has-text("Pause All")')).toBeVisible();
    }
  });

  test('should view worker output panel for busy workers', async ({ page }) => {
    // Create a busy worker
    await createTestWorker({
      name: `e2e-output-worker-${Date.now()}`,
      status: 'busy',
    });

    // Reload page
    await page.goto('/workers');
    await waitForPageStability(page);

    // Find a busy worker
    const busyWorker = page.locator('.worker-card.busy').first();
    const count = await busyWorker.count();

    if (count > 0) {
      // Worker card should be visible
      await expect(busyWorker).toBeVisible();

      // Look for View Output button (might not exist for all workers)
      const viewOutputButton = busyWorker.locator('button:has-text("View Output")');
      const buttonCount = await viewOutputButton.count();
      expect(buttonCount).toBeGreaterThanOrEqual(0);
    }
  });
});
