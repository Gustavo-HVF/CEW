import { defineConfig } from '@playwright/test';

// CEW_CHROMIUM permite usar um Chromium ja instalado (ex.: /opt/pw-browsers/chromium).
const executablePath = process.env.CEW_CHROMIUM || undefined;

export default defineConfig({
  testDir: './tests',
  testMatch: '**/*.spec.js', // so testes de navegador; scripts de Node (ex.: tests/nucleo_node.mjs) ficam de fora
  timeout: 60_000,
  use: { baseURL: 'http://localhost:4173', viewport: { width: 1280, height: 720 }, launchOptions: { executablePath } },
  webServer: { command: 'npx vite preview --port 4173 --strictPort', url: 'http://localhost:4173', reuseExistingServer: true, timeout: 60_000 },
});
