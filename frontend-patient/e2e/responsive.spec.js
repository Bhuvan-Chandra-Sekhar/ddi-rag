import { accounts, expect, fillCheck, goTo, openApp, openChecker, runCheck, signInAs, test } from './helpers.js';

// Runs on the phone-sized project (Pixel 7). A layout that overflows
// sideways, or a navigation that cannot be tapped, is invisible to jsdom.

// Resolves to the offending elements (empty when the page fits), so a
// failure says WHICH element is too wide instead of just "false".
const overflowing = (page) =>
  page.evaluate(() => {
    const limit = document.documentElement.clientWidth;
    if (document.documentElement.scrollWidth <= limit + 1) return [];
    return [...document.querySelectorAll('body *')]
      .filter((el) => el.getBoundingClientRect().right > limit + 1)
      .slice(0, 6)
      .map((el) => `${el.tagName.toLowerCase()}.${String(el.className && el.className.baseVal !== undefined ? el.className.baseVal : el.className).slice(0, 60)} ` +
        `right=${Math.round(el.getBoundingClientRect().right)} > ${limit} :: "${(el.textContent || '').trim().slice(0, 40)}"`);
  });
const noSidewaysScroll = async (page) => (await overflowing(page)).length === 0;

test.describe('on a phone', () => {
  test('no screen scrolls sideways', async ({ page }) => {
    await openApp(page);
    expect(await overflowing(page), 'home').toEqual([]);

    await goTo(page, 'Quick check');
    expect(await overflowing(page), 'checker').toEqual([]);

    await fillCheck(page, { checking: 'aspirin', current: ['warfarin', 'a-very-long-medication-name-that-could-overflow'] });
    expect(await overflowing(page), 'checker with entries').toEqual([]);

    await page.getByRole('button', { name: /check now/i }).click();
    await expect(page.getByText('Your results')).toBeVisible();
    expect(await overflowing(page), 'results').toEqual([]);

    await goTo(page, /^sign in/i);
    expect(await overflowing(page), 'sign in').toEqual([]);
    await page.getByRole('tab', { name: 'Create account' }).tap();
    await expect(page.getByLabel('Care organization')).toBeVisible();
    expect(await overflowing(page), 'create account').toEqual([]);

    await page.getByRole('tab', { name: 'Sign in' }).tap();
    await signInAs(page, accounts.patient, { via: 'none' });
    await expect(page.getByText('Reviewed and ready')).toBeVisible();
    expect(await overflowing(page), 'dashboard').toEqual([]);
  });

  test('the main navigation fits the screen and every item can be tapped', async ({ page }) => {
    await openApp(page);
    const nav = page.getByRole('navigation', { name: 'Main navigation' });
    const viewport = page.viewportSize();
    const buttons = await nav.getByRole('button').all();
    expect(buttons.length).toBeGreaterThanOrEqual(3);
    for (const button of buttons) {
      await expect(button).toBeVisible();
      const box = await button.boundingBox();
      expect(box.x, 'inside the screen on the left').toBeGreaterThanOrEqual(0);
      expect(box.x + box.width, 'inside the screen on the right').toBeLessThanOrEqual(viewport.width);
      expect(box.height, 'tall enough to tap (WCAG 2.2 target size minimum)').toBeGreaterThanOrEqual(24);
    }
    await nav.getByRole('button', { name: 'Quick check' }).tap();
    await expect(page.getByRole('heading', { name: 'What are you checking?' })).toBeVisible();
    await nav.getByRole('button', { name: 'Overview' }).tap();
    await expect(page.getByRole('heading', { level: 1, name: /uncovering what to know/i })).toBeVisible();
  });

  test('a whole quick check can be done by touch', async ({ page }) => {
    await openChecker(page);
    await page.getByLabel('Medication to check').fill('aspirin');
    await page.getByLabel('Medication to check').press('Enter');
    await page.getByLabel('Current medications').fill('warfarin');
    await page.getByRole('button', { name: 'Add' }).last().tap();
    await page.getByRole('button', { name: /check now/i }).tap();
    await expect(page.getByText('Interaction: aspirin + warfarin')).toBeVisible();
    await expect(page.getByText(/please talk to a doctor or pharmacist/i)).toBeVisible();
  });

  test('the homepage journey still reaches its choices on a small screen', async ({ page }) => {
    await openApp(page);
    await page.evaluate(() => {
      const main = document.querySelector('main.cicada-journey');
      const top = main.getBoundingClientRect().top + window.scrollY;
      window.scrollTo({ top: top + 2.6 * window.innerHeight, behavior: 'instant' });
    });
    // The header has a "Quick check" button too; the journey's own is the butterfly option.
    await expect(page.locator('.butterfly-option', { hasText: /quick check/i })).toBeVisible();
    expect(await overflowing(page)).toEqual([]);
  });
});
