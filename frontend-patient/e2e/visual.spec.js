import { expect, openApp, test } from './helpers.js';

// The homepage's scroll journey: a tree that grows and fades, a symbol,
// then wings and the three choices. Home.jsx drives it by writing CSS custom
// properties on <main> as the page scrolls, and index.css turns those into
// opacity/transform. jsdom has no layout, scroll or CSS, so only a real
// browser can tell whether any of that still works.
//
// Assertions are on state and geometry (stable across machines). Pixel
// screenshots at each stop are attached to the report for a human to look
// at; they are not compared against stored images, because anti-aliasing
// differs between operating systems and would make the suite flaky.

const STOPS = [0, 0.5, 1, 1.7, 2.1, 2.4, 2.6]; // multiples of the viewport height, as Home.jsx measures progress

const readState = (page) =>
  page.evaluate(() => {
    const main = document.querySelector('main.cicada-journey');
    const num = (name) => parseFloat(main.style.getPropertyValue(name));
    const tree = document.querySelector('.journey-stage .living-tree');
    const butterfly = document.querySelector('.stage-butterfly');
    const symbol = document.querySelector('.stage-symbol');
    const box = tree.getBoundingClientRect();
    return {
      grow: num('--tree-grow'),
      gone: num('--tree-gone'),
      symbol: num('--symbol-visible'),
      wings: num('--wings-visible'),
      introWings: num('--intro-wings'),
      choicesReady: main.classList.contains('choices-ready'),
      treeOpacity: parseFloat(getComputedStyle(tree).opacity),
      treeCenterX: box.left + box.width / 2,
      butterflyOpacity: parseFloat(getComputedStyle(butterfly).opacity),
      symbolOpacity: parseFloat(getComputedStyle(symbol).opacity),
      scrollY: window.scrollY,
    };
  });

async function scrollToStop(page, progress) {
  await page.evaluate((p) => {
    const main = document.querySelector('main.cicada-journey');
    const top = main.getBoundingClientRect().top + window.scrollY;
    window.scrollTo({ top: top + p * window.innerHeight, left: 0, behavior: 'instant' });
  }, progress);
  // Home.jsx batches updates in requestAnimationFrame.
  await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
}

test.describe('homepage scroll journey', () => {
  test('starts untouched: tree whole, nothing else shown yet', async ({ page }) => {
    await openApp(page);
    const s = await readState(page);
    expect(s).toMatchObject({ grow: 0, gone: 0, symbol: 0, wings: 0, introWings: 1, choicesReady: false });
    expect(s.treeOpacity).toBe(1);
    expect(s.butterflyOpacity).toBe(0);
  });

  test('every stage advances in order as the person scrolls down, and never goes backwards', async ({ page }) => {
    await openApp(page);
    const states = [];
    for (const stop of STOPS) {
      await scrollToStop(page, stop);
      states.push({ stop, ...(await readState(page)) });
    }
    for (let i = 1; i < states.length; i += 1) {
      const [before, after] = [states[i - 1], states[i]];
      expect(after.grow, `grow at ${after.stop}`).toBeGreaterThanOrEqual(before.grow);
      expect(after.gone, `gone at ${after.stop}`).toBeGreaterThanOrEqual(before.gone);
      expect(after.symbol, `symbol at ${after.stop}`).toBeGreaterThanOrEqual(before.symbol);
      expect(after.wings, `wings at ${after.stop}`).toBeGreaterThanOrEqual(before.wings);
      expect(after.introWings, `introWings at ${after.stop}`).toBeLessThanOrEqual(before.introWings);
    }
    const at = Object.fromEntries(states.map((s) => [s.stop, s]));
    expect(at[1].grow).toBeGreaterThan(0.2);          // tree is growing...
    expect(at[1].gone).toBe(0);                       // ...and still there
    expect(at[2.1].gone).toBe(1);                     // tree has gone
    expect(at[2.1].symbol).toBeGreaterThan(0.9);      // the symbol has taken over
    expect(at[2.6].wings).toBe(1);                    // wings fully arrived
    expect(at[2.6].choicesReady).toBe(true);          // and the choices are live
    expect(at[2.4].choicesReady).toBe(false);         // but not a moment before
  });

  test('the CSS turns that state into what the person sees', async ({ page }) => {
    await openApp(page);
    const start = await readState(page);
    await scrollToStop(page, 1);
    const growing = await readState(page);
    await scrollToStop(page, 2.1);
    const gone = await readState(page);
    await scrollToStop(page, 2.6);
    const wings = await readState(page);

    expect(growing.treeCenterX, 'the tree drifts sideways as it grows').toBeGreaterThan(start.treeCenterX + 20);
    expect(growing.treeOpacity).toBe(1);
    expect(gone.treeOpacity, 'the tree has faded out').toBeLessThan(0.05);
    expect(wings.butterflyOpacity, 'the wings have faded in').toBeGreaterThan(0.95);
    expect(start.butterflyOpacity).toBe(0);
  });

  test('scrolling back up restores each earlier stage exactly', async ({ page }) => {
    await openApp(page);
    await scrollToStop(page, 1);
    const earlier = await readState(page);
    await scrollToStop(page, 2.6);
    await scrollToStop(page, 1);
    const returned = await readState(page);
    expect(returned.grow).toBeCloseTo(earlier.grow, 3);
    expect(returned.gone).toBe(earlier.gone);
    expect(returned.wings).toBe(0);
    expect(returned.choicesReady).toBe(false);
    await scrollToStop(page, 0);
    expect(await readState(page)).toMatchObject({ grow: 0, gone: 0, symbol: 0, wings: 0, introWings: 1 });
  });

  test('the three choices are reachable and work once the journey ends', async ({ page }) => {
    await openApp(page);
    await scrollToStop(page, 2.6);
    // Scoped to the journey's own options: the header also has a "Quick check".
    const options = page.locator('.butterfly-option');
    await expect(options).toHaveCount(3);
    for (const name of [/quick check/i, /patient portal/i, /clinic portal/i]) {
      const choice = options.filter({ hasText: name });
      await expect(choice).toBeVisible();
      await expect(choice).toBeEnabled();
    }
    await options.filter({ hasText: /quick check/i }).click();
    await expect(page.getByRole('heading', { name: 'What are you checking?' })).toBeVisible();
  });

  test('the screen visibly changes at every stage (screenshots attached to the report)', async ({ page }, testInfo) => {
    await openApp(page);
    const shots = [];
    for (const stop of [0, 1, 2.1, 2.6]) {
      await scrollToStop(page, stop);
      const image = await page.screenshot();
      shots.push(image);
      await testInfo.attach(`journey-at-${stop}x-viewport.png`, { body: image, contentType: 'image/png' });
    }
    for (let i = 1; i < shots.length; i += 1) {
      expect(shots[i].equals(shots[i - 1]), `screenshot ${i} identical to ${i - 1}: nothing changed on screen`).toBe(false);
    }
  });

  test('a window resize recomputes the journey instead of leaving stale values', async ({ page }) => {
    await openApp(page);
    await scrollToStop(page, 1);
    const before = await readState(page);
    await page.setViewportSize({ width: 900, height: 500 });
    await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    const after = await readState(page);
    // Same scroll offset over a shorter viewport is further along the journey.
    expect(after.grow).toBeGreaterThan(before.grow);
  });
});
