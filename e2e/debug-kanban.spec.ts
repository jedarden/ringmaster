import { test, expect } from '@playwright/test';

test('Debug kanban loading', async ({ page }) => {
  const errors: string[] = [];

  page.on('pageerror', error => {
    errors.push(`PAGE ERROR: ${error.message}`);
  });

  await page.goto('/kanban');
  await page.waitForTimeout(3000);

  await page.screenshot({ path: 'screenshots/debug-kanban.png' });

  console.log('=== Errors ===');
  errors.forEach(e => console.log(e));

  const hasContent = await page.locator('text=Draft').isVisible().catch(() => false) ||
                     await page.locator('text=Kanban').isVisible().catch(() => false);
  console.log('=== Has content:', hasContent);
});
