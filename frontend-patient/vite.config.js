import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

// Real build step, real Tailwind compile — the styling gets baked into a
// static CSS file at build time. Nothing at runtime depends on a CDN
// script finishing before the page can render styled, unlike the old
// static/patient/index.html (Tailwind Play CDN).
export default defineConfig({
  plugins: [react(), tailwindcss()],
});
