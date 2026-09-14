import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

// Real build step, real Tailwind compile — the styling gets baked into a
// static CSS file at build time. Nothing at runtime depends on a CDN
// script finishing before the page can render styled, unlike the old
// static/patient/index.html (Tailwind Play CDN).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  base: '/',
  build: { outDir: 'dist', emptyOutDir: true },
  server: {
    proxy: { '/api': 'http://127.0.0.1:5000', '/v1': 'http://127.0.0.1:5000' },
    // node_modules here is a symlink into ../../frontend-patient/node_modules
    // (shared install, no separate npm install needed) — Vite's default
    // fs.allow only covers the project root + its own node_modules, so it
    // 403's anything served through that symlink's real target (self-hosted
    // font files in particular, since those are fetched directly by the
    // browser via @fs/ URLs, not pre-bundled like JS deps are). Widening
    // fs.allow to the repo root fixes that without giving up the shared
    // install.
    fs: { allow: ['../..'] },
  },
});
