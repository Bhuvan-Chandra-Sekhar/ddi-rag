import AxeBuilder from '@axe-core/playwright';
import { accounts, control, expect, fillCheck, goTo, openApp, openChecker, runCheck, signInAs, test } from './helpers.js';

// Automated WCAG 2.1 A/AA scan of every screen a patient can reach, plus
// the things a scanner cannot see: keyboard operation, where focus goes
// after navigating, and what a screen reader is told as state changes.

// Rules that currently fail and are tracked, with where and why. Anything
// NOT listed here fails the build; a listed rule that stops failing also
// fails (so this list can only shrink). Empty means a clean scan.
const KNOWN_VIOLATIONS = {};

const WCAG = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'];

// Screens fade in (.reveal). Axe reads the colour that is actually painted,
// so scanning mid-fade sees partly transparent text and reports a contrast
// failure that is not there once the animation ends. Wait for every
// animation that has an end; the endless decorative ones never finish.
async function settle(page) {
  await page.evaluate(() =>
    Promise.all(
      document
        .getAnimations()
        .filter((animation) => animation.effect && animation.effect.getComputedTiming().iterations !== Infinity)
        .map((animation) => animation.finished.catch(() => {}))
    )
  );
}

async function scan(page, name) {
  await settle(page);
  const { violations } = await new AxeBuilder({ page }).withTags(WCAG).analyze();
  const found = [...new Set(violations.map((v) => v.id))].sort();
  const allowed = (KNOWN_VIOLATIONS[name] ?? []).slice().sort();
  const detail = violations.map((v) => `${v.id} (${v.impact}): ${v.help}\n    ` +
    v.nodes.slice(0, 4).map((n) => n.target.join(' ')).join('\n    ')).join('\n  ');
  expect(found, `axe violations on "${name}":\n  ${detail}`).toEqual(allowed);
}

test.describe('automated WCAG scan of every screen', () => {
  test('home', async ({ page }) => {
    await openApp(page);
    await scan(page, 'home');
  });

  test('quick check form', async ({ page }) => {
    await openChecker(page);
    await scan(page, 'checker');
  });

  test('quick check form with entries, a limit notice and an error showing', async ({ page }) => {
    await openChecker(page);
    await fillCheck(page, { checking: 'aspirin', current: Array.from({ length: 7 }, (_, i) => `drug${i + 1}`) });
    await page.getByLabel('Current medications').fill('overflow');
    await page.getByLabel('Current medications').press('Enter');
    await page.getByRole('button', { name: /check now/i }).click();
    await expect(page.getByRole('alert')).toBeVisible();
    await scan(page, 'checker-with-messages');
  });

  test('results with findings, an explanation and the coverage section', async ({ page }) => {
    await runCheck(page, { checking: 'aspirin', current: ['warfarin'] });
    await expect(page.getByText('E2E explanation for a major ddi finding.')).toBeVisible();
    await scan(page, 'results');
  });

  test('results with nothing flagged', async ({ page }) => {
    await runCheck(page, { checking: 'metformin', current: ['paracetamol'] });
    await scan(page, 'results-empty');
  });

  test('sign in', async ({ page }) => {
    await openApp(page);
    await goTo(page, /^sign in/i);
    await scan(page, 'auth-sign-in');
  });

  test('create account', async ({ page }) => {
    await openApp(page);
    await goTo(page, /^sign in/i);
    await page.getByRole('tab', { name: 'Create account' }).click();
    await expect(page.getByLabel('Care organization')).toBeVisible();
    await scan(page, 'auth-register');
  });

  test('prescription dashboard', async ({ page }) => {
    await openApp(page);
    await goTo(page, /^sign in/i);
    await signInAs(page, accounts.patient, { via: 'none' });
    await expect(page.getByText('Reviewed and ready')).toBeVisible();
    await scan(page, 'dashboard');
  });
});

test.describe('keyboard operation', () => {
  test('the whole quick check can be completed without a mouse', async ({ page, isMobile }) => {
    test.skip(isMobile, 'physical-keyboard flow; covered on desktop');
    await openApp(page);
    await page.getByRole('navigation', { name: 'Main navigation' }).getByRole('button', { name: 'Quick check' }).focus();
    await page.keyboard.press('Enter');
    await expect(page.getByRole('heading', { name: 'What are you checking?' })).toBeVisible();

    await page.getByLabel('Medication to check').focus();
    await page.keyboard.type('aspirin');
    await page.keyboard.press('Enter');
    await page.getByLabel('Current medications').focus();
    await page.keyboard.type('warfarin');
    await page.keyboard.press('Enter');
    await page.getByRole('button', { name: /check now/i }).focus();
    await page.keyboard.press('Enter');
    await expect(page.getByText('Interaction: aspirin + warfarin')).toBeVisible();
  });

  test('sign-in tabs follow the ARIA tabs pattern in a real browser', async ({ page, isMobile }) => {
    test.skip(isMobile, 'arrow-key navigation needs a keyboard');
    await openApp(page);
    await goTo(page, /^sign in/i);
    const signIn = page.getByRole('tab', { name: 'Sign in' });
    const create = page.getByRole('tab', { name: 'Create account' });
    await signIn.focus();
    await page.keyboard.press('ArrowRight');
    await expect(create).toBeFocused();
    await expect(create).toHaveAttribute('aria-selected', 'true');
    await expect(page.getByRole('tabpanel')).toHaveAccessibleName('Create account');
    await page.keyboard.press('Home');
    await expect(signIn).toBeFocused();
    // Only the selected tab sits in the Tab order; Tab leaves the tablist.
    await page.keyboard.press('Tab');
    await expect(page.getByLabel('Email')).toBeFocused();
  });

  test('every control reached with Tab on the quick check form shows a visible focus indicator', async ({ page, isMobile }) => {
    test.skip(isMobile, 'physical-keyboard flow; covered on desktop');
    await openChecker(page);
    const withoutIndicator = [];
    for (let i = 0; i < 12; i += 1) {
      await page.keyboard.press('Tab');
      const state = await page.evaluate(() => {
        const el = document.activeElement;
        if (!el || el === document.body) return null;
        const s = getComputedStyle(el);
        const ring = s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) > 0;
        const glow = s.boxShadow && s.boxShadow !== 'none';
        const border = el.matches('input, textarea, select');
        return { name: el.getAttribute('aria-label') || el.id || el.textContent.trim().slice(0, 30) || el.tagName, visible: ring || glow || border };
      });
      if (state && !state.visible) withoutIndicator.push(state.name);
    }
    expect(withoutIndicator, 'focused controls with no visible indicator').toEqual([]);
  });
});

test.describe('focus and announcements', () => {
  test('navigating moves focus into the new view instead of leaving it on a removed button', async ({ page }) => {
    await openApp(page);
    await goTo(page, 'Quick check');
    await expect(page.getByRole('heading', { name: 'What are you checking?' })).toBeFocused();

    await goTo(page, /^sign in/i);
    await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeFocused();
  });

  test('focus lands on the results after a check completes', async ({ page }) => {
    await runCheck(page, { checking: 'aspirin', current: ['warfarin'] });
    const inMain = await page.evaluate(() => !!document.activeElement && document.activeElement.closest('main') !== null);
    expect(inMain).toBe(true);
  });

  test('errors, limits and loading states are exposed as live regions', async ({ page }) => {
    await openChecker(page);
    await page.getByRole('button', { name: /check now/i }).click();
    await expect(page.getByRole('alert')).toHaveText('Add at least one drug to check.');

    const field = page.getByLabel('Current medications');
    for (let i = 1; i <= 9; i += 1) {
      await field.fill(`drug${i}`);
      await field.press('Enter');
    }
    await expect(page.getByRole('status')).toContainText('up to 8 medications');
    await expect(field).toHaveAccessibleDescription(/up to 8 medications/i);
  });

  test('the scanning screen announces progress politely', async ({ page }) => {
    await page.route('**/api/self-check', async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 1500));
      await route.continue();
    });
    await openChecker(page);
    await fillCheck(page, { checking: 'aspirin', current: ['warfarin'] });
    await page.getByRole('button', { name: /check now/i }).click();
    const region = page.getByRole('status').filter({ hasText: 'Reading the evidence' });
    await expect(region).toBeVisible();
    await expect(region).toHaveAttribute('aria-live', 'polite');
  });

  test('a failed sign-in is announced as an alert', async ({ page }) => {
    await openApp(page);
    await goTo(page, /^sign in/i);
    await signInAs(page, { email: accounts.patient.email, password: 'wrong-password' }, { via: 'none' });
    await expect(page.getByRole('alert')).toHaveText('Invalid email or password.');
  });
});

test.describe('reduced motion', () => {
  test('honours the preference on the homepage', async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await openApp(page);
    const animating = await page.evaluate(() => {
      const names = [];
      for (const el of document.querySelectorAll('.cicada-journey *')) {
        const s = getComputedStyle(el);
        if (s.animationName !== 'none' && parseFloat(s.animationDuration) > 0) {
          names.push(`${el.className && el.className.baseVal !== undefined ? el.className.baseVal : el.className}:${s.animationName}`);
        }
      }
      return names;
    });
    expect(animating, 'elements still animating under prefers-reduced-motion').toEqual([]);
  });
});
