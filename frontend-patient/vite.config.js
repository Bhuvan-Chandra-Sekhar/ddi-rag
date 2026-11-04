import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

// Real build step, real Tailwind compile — the styling gets baked into a
// static CSS file at build time. Nothing at runtime depends on a CDN
// script finishing before the page can render styled, unlike the old
// static/patient/index.html (Tailwind Play CDN).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  test: {
    environment: 'jsdom',
    setupFiles: './src/test/setup.js',
    clearMocks: true,
    restoreMocks: true,
    // Playwright specs live in e2e/ and are run by `npm run e2e`, not Vitest.
    exclude: ['e2e/**', 'node_modules/**'],
    coverage: {
      provider: 'v8',
      reportsDirectory: './coverage',
      reporter: ['text', 'html', 'lcov'],
      include: ['src/**/*.{js,jsx}'],
      exclude: ['src/test/**', 'src/main.jsx'],
      // A floor just under what the suite achieves today, so coverage can
      // only ratchet up. Branches are the number that matters most here:
      // the warning and error paths are the product, not the happy path.
      // The per-file lines are stricter for the code that decides what a
      // patient is told. HeroConstellation.jsx is currently unreferenced
      // (0%) and is what keeps the global figures below the per-file ones.
      thresholds: {
        statements: 88,
        branches: 90,
        functions: 90,
        lines: 88,
        'src/api.js': { statements: 100, branches: 100, functions: 100, lines: 100 },
        'src/screens/Results.jsx': { statements: 95, branches: 88, functions: 95, lines: 95 },
        'src/components/FindingCard.jsx': { statements: 95, branches: 90, functions: 95, lines: 95 },
        'src/screens/Auth.jsx': { statements: 95, branches: 90, functions: 95, lines: 95 },
        'src/screens/Checker.jsx': { statements: 95, branches: 85, functions: 95, lines: 95 },
        'src/screens/Dashboard.jsx': { statements: 95, branches: 90, functions: 95, lines: 95 },
      },
    },
  },
  base: '/static/patient-app/',
  build: { outDir: '../ddi_rag/static/patient-app', emptyOutDir: true },
  server: { proxy: { '/api': 'http://127.0.0.1:5000', '/v1': 'http://127.0.0.1:5000' } },
});
