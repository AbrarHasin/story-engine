import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,                    // serialize all tests — avoids backend overload
  forbidOnly: !!process.env.CI,
  retries: 0,
  timeout: 150_000,
  reporter: [['html', { open: 'never' }], ['list']],
  use: {
    baseURL: 'http://localhost:5173',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
  // Dev servers are managed manually via start-dev.sh
  // Run: bash start-dev.sh before running tests
});
