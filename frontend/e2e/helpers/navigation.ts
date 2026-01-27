/**
 * Navigation helper functions for E2E tests
 * Provides robust navigation with stability checks and error recovery
 */

import { Page } from '@playwright/test';

/**
 * Navigate to a URL with stability checks
 * Handles Playwright + React Router compatibility issues
 */
export async function navigateWithRetry(
  page: Page,
  url: string,
  options: { timeout?: number; maxRetries?: number } = {}
): Promise<boolean> {
  const { timeout = 30000, maxRetries = 3 } = options;

  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    try {
      // Navigate to the URL
      await page.goto(url, { timeout });

      // Wait for DOM content loaded first (more reliable than networkidle)
      await page.waitForLoadState('domcontentloaded', { timeout });

      // Additional wait for React Router to settle
      await page.waitForTimeout(100);

      // Check if page crashed (Playwright error detection)
      const isClosed = page.isClosed();
      if (isClosed) {
        throw new Error('Page was closed during navigation');
      }

      // Try to get the URL to verify page is still responsive
      await page.url();

      return true;
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error);

      // If this is the last attempt, throw the error
      if (attempt === maxRetries) {
        throw new Error(
          `Failed to navigate to ${url} after ${maxRetries} attempts: ${errorMessage}`
        );
      }

      // Log retry attempt
      console.warn(`Navigation attempt ${attempt}/${maxRetries} failed: ${errorMessage}. Retrying...`);

      // Wait before retry
      await page.waitForTimeout(500);
    }
  }

  return false;
}

/**
 * Navigate via click with stability checks (more reliable than direct navigation)
 */
export async function navigateViaClick(
  page: Page,
  selector: string,
  options: { timeout?: number } = {}
): Promise<void> {
  const { timeout = 10000 } = options;

  // Click the element
  await page.click(selector, { timeout });

  // Wait for navigation to complete
  await page.waitForLoadState('domcontentloaded', { timeout });

  // Additional wait for React Router to settle
  await page.waitForTimeout(100);
}

/**
 * Wait for page to be stable after navigation
 * Checks that the page is responsive and elements are interactive
 */
export async function waitForPageStability(
  page: Page,
  options: { timeout?: number } = {}
): Promise<void> {
  const { timeout = 5000 } = options;

  // Wait for DOM to be ready
  await page.waitForLoadState('domcontentloaded', { timeout });

  // Wait a bit for React Router and any client-side rendering
  await page.waitForTimeout(200);

  // Verify page is still responsive by getting the URL
  await page.url();
}

/**
 * Retry a block of code if the page crashes
 */
export async function withPageRetry<T>(
  page: Page,
  fn: () => Promise<T>,
  options: { maxRetries?: number; onRetry?: (attempt: number) => void } = {}
): Promise<T> {
  const { maxRetries = 3, onRetry } = options;

  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    try {
      return await fn();
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error);

      // Check if error is related to page crash
      const isPageCrash =
        errorMessage.includes('Page crashed') ||
        errorMessage.includes('Target closed') ||
        errorMessage.includes('Session closed');

      if (!isPageCrash || attempt === maxRetries) {
        throw error;
      }

      // Log retry attempt
      if (onRetry) {
        onRetry(attempt);
      } else {
        console.warn(`Page crashed on attempt ${attempt}/${maxRetries}. Retrying...`);
      }

      // Wait before retry
      await page.waitForTimeout(500);
    }
  }

  throw new Error('withPageRetry failed unexpectedly');
}
