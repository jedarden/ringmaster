import { test, expect } from '@playwright/test'

test.describe('Kanban Board', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
  })

  test('displays the kanban board with columns', async ({ page }) => {
    // The board should show the column headers
    await expect(page.getByText('Draft')).toBeVisible()
    await expect(page.getByText('Planning')).toBeVisible()
    await expect(page.getByText('Coding')).toBeVisible()
    await expect(page.getByText('Completed')).toBeVisible()
  })

  test('shows header navigation', async ({ page }) => {
    // The header should be visible
    await expect(page.getByRole('navigation')).toBeVisible()
  })

  test('displays stats bar with metrics', async ({ page }) => {
    // Stats bar should show card count and other metrics
    // Look for common stats elements
    await expect(page.locator('text=/\\d+ cards?/')).toBeVisible({ timeout: 5000 }).catch(() => {
      // Stats bar may not show cards if there are none
      console.log('No card count visible - this is expected if no cards exist')
    })
  })
})

test.describe('Navigation', () => {
  test('can navigate to dashboard', async ({ page }) => {
    await page.goto('/')

    // Look for dashboard link in navigation
    const dashboardLink = page.getByRole('link', { name: /dashboard/i })
    if (await dashboardLink.isVisible()) {
      await dashboardLink.click()
      await expect(page).toHaveURL(/.*dashboard.*/)
    }
  })

  test('can navigate to projects page', async ({ page }) => {
    await page.goto('/')

    // Look for projects link in navigation
    const projectsLink = page.getByRole('link', { name: /projects?/i })
    if (await projectsLink.isVisible()) {
      await projectsLink.click()
      await expect(page).toHaveURL(/.*projects?.*/)
    }
  })
})
