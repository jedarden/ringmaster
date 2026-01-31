import { test, expect } from '@playwright/test';

test('Debug dashboard loading', async ({ page }) => {
  // Collect all console messages
  const messages: string[] = [];
  const errors: string[] = [];

  page.on('console', msg => {
    messages.push(`[${msg.type()}] ${msg.text()}`);
    if (msg.type() === 'error') {
      errors.push(msg.text());
    }
  });

  page.on('pageerror', error => {
    errors.push(`PAGE ERROR: ${error.message}`);
  });

  // Navigate to dashboard
  await page.goto('/dashboard');
  await page.waitForTimeout(3000);

  // Take screenshot
  await page.screenshot({ path: 'screenshots/debug-dashboard.png' });

  // Print all console output
  console.log('=== Console Messages ===');
  messages.forEach(m => console.log(m));

  console.log('\n=== Errors ===');
  errors.forEach(e => console.log(e));

  // Check page content
  const html = await page.content();
  console.log('\n=== Page contains "Dashboard":', html.includes('Dashboard'));
  console.log('=== Page contains "Total Cards":', html.includes('Total Cards'));
  console.log('=== Page contains "error":', html.toLowerCase().includes('error'));

  // Check if root element has content
  const rootContent = await page.evaluate(() => {
    const root = document.getElementById('root');
    return root ? root.innerHTML.length : 0;
  });
  console.log('=== Root element HTML length:', rootContent);
});
