import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright E2E test configuration for Ringmaster frontend
 *
 * IMPORTANT: Tests run serially (fullyParallel: false) to avoid:
 * - React Router race conditions when tests navigate simultaneously
 * - Database conflicts from concurrent test data mutations
 * - WebSocket connection issues with multiple browser contexts
 *
 * To speed up tests, optimize individual test execution time rather than parallelization.
 *
 * NOTE: These tests require BOTH the frontend (Vite) and backend (Ringmaster API) to be running.
 * The webServer config starts both servers automatically.
 */
export default defineConfig({
  testDir: './e2e',
  // Run tests serially to avoid race conditions and data conflicts
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1, // Single worker to ensure serial execution

  reporter: 'html',

  use: {
    baseURL: 'http://localhost:5173',
    trace: 'on-first-retry',
    // Increase timeout for API interactions
    actionTimeout: 10000,
    navigationTimeout: 30000,
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],

  // Start both backend API and frontend dev server
  // Skip webServer if USE_EXISTING_SERVERS env var is set
  ...(!process.env.USE_EXISTING_SERVERS ? {
    webServer: [
      {
        // Use shell script to initialize database and start API server
        command: './start-backend-for-e2e.sh',
        url: 'http://localhost:8000',
        reuseExistingServer: !process.env.CI,
        timeout: 120000,
      },
      {
        command: 'npm run dev',
        url: 'http://localhost:5173',
        reuseExistingServer: !process.env.CI,
        timeout: 120000,
      },
    ],
  } : {}),
});
