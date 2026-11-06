import { defineConfig } from '@playwright/test';

const baseURL = 'http://127.0.0.1:5181';

export default defineConfig({
  testDir: 'tests/browser',
  timeout: 60_000,
  use: {
    baseURL,
    viewport: { width: 1440, height: 1100 },
    screenshot: 'only-on-failure',
  },
  webServer: {
    command: 'npm run dev -- --strictPort',
    url: baseURL,
    reuseExistingServer: !process.env.CI,
  },
  reporter: 'list',
});
