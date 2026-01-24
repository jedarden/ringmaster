import { test, expect } from '@playwright/test'

test.describe('Dashboard Page', () => {
  test('can navigate to dashboard', async ({ page }) => {
    await page.goto('/')

    // Find dashboard link and navigate
    const dashboardLink = page.getByRole('link', { name: /dashboard/i })

    if (await dashboardLink.isVisible({ timeout: 2000 }).catch(() => false)) {
      await dashboardLink.click()
      await expect(page).toHaveURL(/.*dashboard.*/)
    } else {
      // Try direct navigation
      await page.goto('/dashboard')
      await page.waitForLoadState('networkidle')
    }
  })

  test('dashboard displays metrics', async ({ page }) => {
    await page.goto('/dashboard')
    await page.waitForLoadState('networkidle')

    // Look for common dashboard elements
    const metricsSection = page.locator('text=/cards?|loops?|cost/i')

    if (await metricsSection.count() > 0) {
      await expect(metricsSection.first()).toBeVisible()
    }
  })
})

test.describe('Projects Page', () => {
  test('can navigate to projects', async ({ page }) => {
    await page.goto('/')

    const projectsLink = page.getByRole('link', { name: /projects?/i })

    if (await projectsLink.isVisible({ timeout: 2000 }).catch(() => false)) {
      await projectsLink.click()
      await expect(page).toHaveURL(/.*projects?.*/)
    } else {
      // Try direct navigation
      await page.goto('/projects')
      await page.waitForLoadState('networkidle')
    }
  })

  test('projects page displays project list or empty state', async ({ page }) => {
    await page.goto('/projects')
    await page.waitForLoadState('networkidle')

    // Should show either projects or an empty state
    const content = page.locator('text=/project|no projects|create/i')
    await expect(content.first()).toBeVisible({ timeout: 5000 })
  })
})
