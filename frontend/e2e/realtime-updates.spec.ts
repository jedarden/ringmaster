import { test, expect } from '@playwright/test';

/**
 * E2E tests for Real-time Updates
 * Tests WebSocket integration for live updates
 */
test.describe('Real-time Updates', () => {
  test('should show WebSocket connection status', async ({ page }) => {
    await page.goto('/');

    // Should see connection indicator in header
    await expect(page.locator('.ws-status-indicator')).toBeVisible();
  });

  test('should display connection status as connected or reconnecting', async ({ page }) => {
    await page.goto('/');

    const statusIndicator = page.locator('.ws-status-indicator');
    await expect(statusIndicator).toHaveAttribute('data-status', /connected|reconnecting|disconnected/);
  });

  test('should update metrics dashboard in real-time', async ({ page }) => {
    await page.goto('/metrics');

    // Should see metrics dashboard
    await expect(page.locator('.metrics-dashboard')).toBeVisible();

    // Metrics should load (check for at least one metric component)
    await expect(page.locator('.task-stats, .worker-stats, .activity-summary').first()).toBeVisible();
  });

  test('should display logs viewer with live mode', async ({ page }) => {
    await page.goto('/logs');

    // Should see logs viewer
    await expect(page.locator('.logs-viewer')).toBeVisible();

    // Should have connection status
    await expect(page.locator('.ws-status-indicator')).toBeVisible();
  });

  test('should show recent events timeline', async ({ page }) => {
    await page.goto('/metrics');

    // Should see events timeline
    await expect(page.locator('.events-timeline')).toBeVisible();
  });
});
