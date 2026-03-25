const { defineConfig } = require('@playwright/test');

const port = Number(process.env.PLAYWRIGHT_TEST_PORT || 19000);
const baseURL = `http://127.0.0.1:${port}`;

module.exports = defineConfig({
  testDir: './playwright/tests',
  timeout: 30_000,
  expect: {
    timeout: 5_000,
  },
  fullyParallel: true,
  reporter: [['list']],
  use: {
    baseURL,
    trace: 'on-first-retry',
  },
  webServer: {
    command: 'node ./playwright/server.js',
    url: `${baseURL}/health`,
    reuseExistingServer: true,
    timeout: 30_000,
  },
});
