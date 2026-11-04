import { expect, test } from './helpers.js';

// What a visitor's browser actually receives from the deployed shape: the
// built bundle, served by Flask under /static/patient-app/. The launcher
// deliberately starts Flask from a directory that is NOT ddi_rag/, so this
// also proves the assets do not depend on the working directory
// (`gunicorn --chdir ddi_rag` used to be the only reason they were found).

const MIME = { js: /javascript/, css: /text\/css/, woff2: /font\/woff2|application\/(font-)?woff2|octet-stream/, png: /image\/png/ };

async function assetUrls(request) {
  const html = await (await request.get('/patient')).text();
  const urls = [...html.matchAll(/(?:src|href)="(\/static\/patient-app\/[^"]+)"/g)].map((m) => m[1]);
  return { html, urls };
}

test.describe('the built bundle is served correctly', () => {
  test('/patient returns the app shell and every asset it references loads with the right type', async ({ request }) => {
    const response = await request.get('/patient');
    expect(response.status()).toBe(200);
    expect(response.headers()['content-type']).toMatch(/text\/html/);

    const { html, urls } = await assetUrls(request);
    expect(html).toContain('<div id="root">');
    expect(urls.length).toBeGreaterThanOrEqual(2); // at least the script and the stylesheet
    expect(urls.some((u) => u.endsWith('.js'))).toBe(true);
    expect(urls.some((u) => u.endsWith('.css'))).toBe(true);

    for (const url of urls) {
      const asset = await request.get(url);
      expect(asset.status(), url).toBe(200);
      const extension = url.split('.').pop();
      if (MIME[extension]) expect(asset.headers()['content-type'], url).toMatch(MIME[extension]);
    }
  });

  test('a missing asset is a real 404, not the app shell served as if it were found', async ({ request }) => {
    const response = await request.get('/static/patient-app/assets/does-not-exist.js');
    expect(response.status()).toBe(404);
    expect(response.headers()['content-type'] ?? '').not.toMatch(/javascript/);
  });

  test('the entry point stays below /static/patient-app/, matching vite.config.js base', async ({ request }) => {
    const { urls } = await assetUrls(request);
    for (const url of urls) expect(url.startsWith('/static/patient-app/')).toBe(true);
  });

  test('the clinical console and the health check are served too', async ({ request }) => {
    const clinical = await request.get('/clinical');
    expect(clinical.status()).toBe(200);
    expect(await clinical.text()).toContain('Clinical Console');
    const health = await request.get('/api/health');
    expect(health.status()).toBe(200);
    expect(await health.json()).toEqual({ status: 'ok' });
  });
});

test.describe('loading it in a real browser', () => {
  test('mounts with no console errors, no failed requests, and no 4xx/5xx responses', async ({ page }) => {
    const problems = [];
    page.on('console', (message) => {
      if (message.type() === 'error') problems.push(`console.error: ${message.text()}`);
    });
    page.on('requestfailed', (request) => problems.push(`failed: ${request.url()} (${request.failure()?.errorText})`));
    page.on('response', (response) => {
      if (response.status() >= 400) problems.push(`${response.status()}: ${response.url()}`);
    });

    await page.goto('/patient', { waitUntil: 'networkidle' });
    await expect(page.getByRole('heading', { level: 1, name: /uncovering what to know/i })).toBeVisible();
    // Scroll through the whole homepage so lazily referenced images and
    // fonts are requested too.
    await page.evaluate(async () => {
      for (let y = 0; y <= document.body.scrollHeight; y += 600) {
        window.scrollTo(0, y);
        await new Promise((resolve) => setTimeout(resolve, 40));
      }
    });
    await page.waitForLoadState('networkidle');
    expect(problems).toEqual([]);
  });

  test('every request the page makes stays on the same origin', async ({ page, baseURL }) => {
    const external = [];
    page.on('request', (request) => {
      const url = new URL(request.url());
      if (!['data:', 'blob:'].includes(url.protocol) && url.origin !== new URL(baseURL).origin) external.push(request.url());
    });
    await page.goto('/patient', { waitUntil: 'networkidle' });
    expect(external, 'no CDN or third-party requests (the old Tailwind Play CDN dependency)').toEqual([]);
  });

  test('the in-page "Scroll to explore" anchor works under the /patient path', async ({ page }) => {
    await page.goto('/patient');
    await page.getByRole('link', { name: /scroll to explore/i }).click();
    await expect(page).toHaveURL(/\/patient#how-it-works$/);
    await expect(page.getByRole('heading', { name: /your medications/i })).toBeInViewport();
  });
});
