import { readFileSync } from 'node:fs';
import { test as base, expect } from '@playwright/test';

export { expect };

export const accounts = JSON.parse(readFileSync(new URL('./test-accounts.json', import.meta.url), 'utf-8'));

// Every test starts from a known backend (switches off, explanation
// service up), and any uncaught page exception fails the test — a React
// crash must never pass just because the assertions happened to be true.
export const test = base.extend({
  page: async ({ page, request }, use) => {
    await request.post('/__e2e__/reset');
    const uncaught = [];
    page.on('pageerror', (error) => uncaught.push(error.message));
    await use(page);
    expect(uncaught, 'uncaught exceptions in the page').toEqual([]);
  },
});

export const control = {
  killSwitch: (request, feature, on) => request.post('/__e2e__/kill-switch', { data: { feature, on } }),
  explainOutage: (request, on) => request.post('/__e2e__/explain-outage', { data: { on } }),
  expiredToken: async (request) => (await (await request.get('/__e2e__/expired-token')).json()).token,
};

export async function openApp(page) {
  await page.goto('/patient');
  await expect(page.getByRole('heading', { level: 1, name: /uncovering what to know/i })).toBeVisible();
}

const nav = (page) => page.getByRole('navigation', { name: 'Main navigation' });
export const goTo = (page, label) => nav(page).getByRole('button', { name: label }).click();

export async function openChecker(page) {
  await openApp(page);
  await goTo(page, 'Quick check');
  await expect(page.getByRole('heading', { name: 'What are you checking?' })).toBeVisible();
}

export async function fillCheck(page, { checking = '', current = [], allergies = [] } = {}) {
  if (checking) {
    await page.getByLabel('Medication to check').fill(checking);
    await page.keyboard.press('Enter');
  }
  for (const name of current) {
    await page.getByLabel('Current medications').fill(name);
    await page.keyboard.press('Enter');
  }
  for (const name of allergies) {
    await page.getByLabel('Known allergies or past reactions').fill(name);
    await page.keyboard.press('Enter');
  }
}

export async function runCheck(page, input) {
  await openChecker(page);
  await fillCheck(page, input);
  await page.getByRole('button', { name: /check now/i }).click();
  await expect(page.getByText('Your results')).toBeVisible();
}

export async function signInAs(page, { email, password }, { via = 'header' } = {}) {
  if (via === 'header') await goTo(page, /^sign in/i);
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password').fill(password);
  await page.getByRole('tabpanel').getByRole('button', { name: 'Sign in' }).click();
}

export const storedToken = (page) => page.evaluate(() => sessionStorage.getItem('medtrust_token'));
