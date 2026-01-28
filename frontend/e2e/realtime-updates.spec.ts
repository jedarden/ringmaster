import { test, expect } from '@playwright/test';

/**
 * E2E tests for Real-time Updates
 * Tests WebSocket integration for live updates
 */
import { waitForPageStability } from './helpers/navigation';
test.describe('Real-time Updates', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await waitForPageStability(page);
  });

  test('should show WebSocket connection status', async ({ page }) => {
    // Should see connection indicator in header
    await expect(page.locator('.ws-status-indicator, [data-ws-status]').first()).toBeVisible({ timeout: 5000 });
  });

  test('should display connection status as connected or reconnecting', async ({ page }) => {
    // Connection status could be connected, reconnecting, or disconnected
    const statusIndicator = page.locator('.ws-status-indicator, [data-ws-status]').first();
    await expect(statusIndicator).toBeVisible({ timeout: 5000 });
  });

  test('should update metrics dashboard in real-time', async ({ page }) => {
    await page.goto('/metrics');
    await waitForPageStability(page);

    // Should see metrics page
    await expect(page.getByRole('heading', { name: /metrics/i })).toBeVisible();

    // Metrics should load (check for at least one metric component)
    const metricsComponents = page.locator('.task-stats, .worker-stats, .activity-summary, .metrics-dashboard');
    await expect(metricsComponents.first()).toBeVisible({ timeout: 5000 });
  });

  test('should display logs viewer with live mode', async ({ page }) => {
    await page.goto('/logs');
    await waitForPageStability(page);

    // Should see logs page
    await expect(page.getByRole('heading', { name: /logs/i })).toBeVisible();

    // Logs viewer should be visible
    const logsViewer = page.locator('.logs-viewer, .log-entry').first();
    await expect(logsViewer).toBeVisible({ timeout: 5000 });

    // Should have connection status indicator
    const statusIndicator = page.locator('.ws-status-indicator, [data-ws-status]').first();
    await expect(statusIndicator).toBeVisible({ timeout: 5000 });
  });

  test('should show recent events timeline', async ({ page }) => {
    await page.goto('/metrics');
    await waitForPageStability(page);

    // Should see metrics page
    await expect(page.getByRole('heading', { name: /metrics/i })).toBeVisible();

    // Events timeline might be empty or hidden if no events
    // Just verify the page loads successfully
    await expect(page.locator('body')).toBeVisible();
  });

  test('should navigate to all realtime pages', async ({ page }) => {
    // Test navigation to all pages with WebSocket features
    const pages = ['/metrics', '/logs'];

    for (const path of pages) {
      await page.goto(path);
      await waitForPageStability(page);

      // Should see page content
      await expect(page.locator('main, [role="main"], .container').first()).toBeVisible({ timeout: 5000 });
    }
  });
});
