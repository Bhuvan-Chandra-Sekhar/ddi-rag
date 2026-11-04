import { control, expect, fillCheck, openChecker, runCheck, test } from './helpers.js';

// Real React, real Flask, real rule engine, real database. The seeded
// rules: aspirin+warfarin (approved, major), nitroglycerin+sildenafil
// (approved, critical), ibuprofen+lisinopril (still a draft, reported major).

const finding = (page, title) => page.locator('div.card', { hasText: title }).first();

test.describe('quick check: findings reach the screen with the right meaning', () => {
  test('an approved major interaction shows its severity, the doctor warning and an explanation', async ({ page }) => {
    await runCheck(page, { checking: 'aspirin', current: ['warfarin'] });

    const card = finding(page, 'Interaction: aspirin + warfarin');
    await expect(card).toBeVisible();
    await expect(card.getByText('Major', { exact: true })).toBeVisible();
    await expect(card).toContainText('E2E: aspirin with warfarin interacts.');
    await expect(card).toContainText('See a doctor or pharmacist before taking these together');
    await expect(page.getByText(/please talk to a doctor or pharmacist/i)).toBeVisible();
    await expect(card).toContainText('E2E explanation for a major ddi finding.');
    await expect(card.getByText('Show 1 source')).toBeVisible();
  });

  test('an approved critical interaction is labelled critical', async ({ page }) => {
    await runCheck(page, { checking: 'sildenafil', current: ['nitroglycerin'] });
    const card = finding(page, 'Interaction: nitroglycerin + sildenafil');
    await expect(card.getByText('Critical', { exact: true })).toBeVisible();
    await expect(page.getByText(/highest priority|please talk to a doctor/i).first()).toBeVisible();
  });

  test('a draft rule is shown as unreviewed, with the dataset rating clearly marked unconfirmed', async ({ page }) => {
    await runCheck(page, { checking: 'ibuprofen', current: ['lisinopril'] });
    const card = finding(page, 'Unreviewed pairing: ibuprofen + lisinopril');
    await expect(card.getByText('Not yet clinically reviewed')).toBeVisible();
    await expect(card).toContainText('Our data suggests: Major (not yet confirmed by a pharmacist)');
  });

  test('an allergy match is critical', async ({ page }) => {
    await runCheck(page, { checking: 'penicillin', allergies: ['penicillin'] });
    const card = finding(page, 'Matches a known allergy — penicillin');
    await expect(card.getByText('Critical', { exact: true })).toBeVisible();
  });

  test('a duplicate ingredient is reported', async ({ page }) => {
    await runCheck(page, { checking: 'aspirin', current: ['aspirin'] });
    await expect(finding(page, 'Duplicate ingredient — aspirin appears 2×')).toBeVisible();
  });

  test('"nothing flagged" never reads as "safe", and the gap in the data is visible', async ({ page }) => {
    await runCheck(page, { checking: 'metformin', current: ['paracetamol'] });

    await expect(page.getByText('Nothing flagged in our data')).toBeVisible();
    await expect(page.getByText(/does not establish that the combination is safe/i)).toBeVisible();
    await expect(page.getByText('No findings to show.')).toBeVisible();

    const withoutRule = page.getByText('Without a rule');
    await expect(withoutRule.locator('xpath=preceding-sibling::p')).toHaveText('1');
    await page.getByText('See pairs without a rule').click();
    await expect(page.getByText('metformin + paracetamol')).toBeVisible();
    // The page may only mention "safe" inside a negation. Remove the two
    // hedged sentences it is allowed to contain, then nothing may remain.
    const text = (await page.locator('body').innerText())
      .replace(/does not establish that the combination is safe/gi, '')
      .replace(/not a safe combination/gi, '');
    expect(text).not.toMatch(/\b(is|are) safe\b|safe to take/i);
  });

  test('an unrecognised name warns instead of reassuring', async ({ page }) => {
    await runCheck(page, { checking: 'mysterypill', current: ['metformin'] });
    await expect(page.getByText(/not sure we understood everything/i)).toBeVisible();
    await expect(page.getByText('Nothing flagged in our data')).toHaveCount(0);
    await expect(page.getByRole('button', { name: /mysterypill/ })).toContainText('·approx');
  });

  test('a drug chip opens the label summary, a second click closes it', async ({ page }) => {
    await runCheck(page, { checking: 'aspirin', current: ['warfarin'] });
    await page.getByRole('button', { name: /^aspirin/ }).click();
    await expect(page.getByText('FDA label summary — aspirin')).toBeVisible();
    await expect(page.getByText('E2E fixture text.')).toBeVisible();
    await page.getByRole('button', { name: /^aspirin/ }).click();
    await expect(page.getByText('FDA label summary — aspirin')).toHaveCount(0);
  });
});

test.describe('quick check: more findings than fit on the screen', () => {
  const crowded = { checking: 'aspirin', current: ['aspirin', 'warfarin', 'nitroglycerin', 'sildenafil'], allergies: ['aspirin'] };

  test('only the visible findings are explained, and "show more" explains only the rest', async ({ page }) => {
    const explained = [];
    page.on('request', (request) => {
      if (request.url().endsWith('/api/explain')) explained.push(request.postDataJSON().finding_index);
    });
    await runCheck(page, crowded);

    const more = page.getByRole('button', { name: /show \d+ more findings?/i });
    await expect(more).toBeVisible();
    await expect.poll(() => explained.length).toBe(3);

    const hidden = Number((await more.innerText()).match(/\d+/)[0]);
    await more.click();
    await expect.poll(() => explained.length).toBe(3 + hidden);
    expect(new Set(explained).size).toBe(explained.length); // nothing requested twice
    await expect(more).toHaveCount(0);
  });

  test('every explanation request carries what was entered, in the shape the API accepts', async ({ page }) => {
    const bodies = [];
    page.on('request', (request) => {
      if (request.url().endsWith('/api/explain')) bodies.push(request.postDataJSON());
    });
    await openChecker(page);
    await fillCheck(page, { checking: 'aspirin', current: ['warfarin'], allergies: ['penicillin'] });
    await page.getByText('Add context').click();
    await page.getByLabel('Additional context').fill('Previous rash');
    await page.getByRole('button', { name: /check now/i }).click();
    await expect(page.getByText('Interaction: aspirin + warfarin')).toBeVisible();
    await expect.poll(() => bodies.length).toBeGreaterThan(0);
    for (const body of bodies) {
      expect(body).toMatchObject({
        medications: ['aspirin', 'warfarin'], allergies: ['penicillin'], patient_notes: 'Previous rash',
      });
      expect(Number.isInteger(body.finding_index)).toBe(true);
    }
  });
});

test.describe('quick check: failures are explained, not hidden', () => {
  test('a disabled check returns to the form with the human message, never the code', async ({ page, request }) => {
    await control.killSwitch(request, 'self_check', true);
    await openChecker(page);
    await fillCheck(page, { checking: 'aspirin', current: ['warfarin'] });
    await page.getByRole('button', { name: /check now/i }).click();

    await expect(page.getByRole('heading', { name: 'What are you checking?' })).toBeVisible();
    const alert = page.getByRole('alert');
    await expect(alert).toContainText('temporarily disabled for maintenance');
    await expect(alert).not.toContainText('temporarily_unavailable');
    await expect(page.getByRole('button', { name: 'Remove aspirin' })).toBeVisible();

    await control.killSwitch(request, 'self_check', false);
    await page.getByRole('button', { name: /check now/i }).click();
    await expect(page.getByText('Interaction: aspirin + warfarin')).toBeVisible();
  });

  test('an explanation outage keeps the finding, says so, and recovers on retry', async ({ page, request }) => {
    await control.explainOutage(request, true);
    await runCheck(page, { checking: 'aspirin', current: ['warfarin'] });

    const card = finding(page, 'Interaction: aspirin + warfarin');
    await expect(card).toContainText('Major');
    const alert = card.getByRole('alert');
    await expect(alert).toContainText("Couldn't load an explanation");
    await expect(alert).toContainText('temporarily unavailable');
    await expect(alert).not.toContainText('explanation_unavailable');

    await control.explainOutage(request, false);
    await card.getByRole('button', { name: /try again/i }).click();
    await expect(card).toContainText('E2E explanation for a major ddi finding.');
    await expect(card.getByRole('alert')).toHaveCount(0);
  });

  test('an empty submission is refused with an alert', async ({ page }) => {
    await openChecker(page);
    await page.getByRole('button', { name: /check now/i }).click();
    await expect(page.getByRole('alert')).toHaveText('Add at least one drug to check.');
  });
});

test.describe('quick check: the medication limit in a real browser', () => {
  test('accepts eight, refuses and explains the ninth, and frees a slot when one is removed', async ({ page }) => {
    await openChecker(page);
    const field = page.getByLabel('Current medications');
    const chips = page.getByRole('button', { name: /^Remove / });
    for (let i = 1; i <= 8; i += 1) {
      await field.fill(`drug${i}`);
      await page.keyboard.press('Enter');
    }
    await expect(chips).toHaveCount(8);
    await expect(page.getByRole('status')).toHaveCount(0);

    await field.fill('drug9');
    await page.keyboard.press('Enter');
    await expect(chips).toHaveCount(8);
    await expect(page.getByRole('status')).toContainText('up to 8 medications');
    await expect(field).toHaveValue('drug9');

    await page.getByRole('button', { name: 'Remove drug1' }).click();
    await expect(page.getByRole('status')).toHaveCount(0);
    await field.press('Enter'); // the field still holds "drug9"; pressing on it also refocuses it
    await expect(chips).toHaveCount(8);
    await expect(page.getByRole('button', { name: 'Remove drug9' })).toBeVisible();
  });

  test('submitting with a refused entry still in the field does not silently drop it', async ({ page }) => {
    await openChecker(page);
    const field = page.getByLabel('Current medications');
    for (let i = 1; i <= 8; i += 1) {
      await field.fill(`drug${i}`);
      await page.keyboard.press('Enter');
    }
    await field.fill('ninth');
    await page.getByRole('button', { name: /check now/i }).click();
    await expect(page.getByRole('alert')).toContainText('was not added because the list is full');
    await expect(page.getByRole('heading', { name: 'What are you checking?' })).toBeVisible();
  });
});

test.describe('quick check: starting over', () => {
  test('"Start a new check" empties the form; "Check a different drug" keeps the rest', async ({ page }) => {
    await runCheck(page, { checking: 'aspirin', current: ['warfarin'] });
    await page.getByRole('button', { name: /check a different drug/i }).click();
    await expect(page.getByLabel('Medication to check')).toHaveValue('');
    await expect(page.getByRole('button', { name: 'Remove warfarin' })).toBeVisible();

    await page.getByLabel('Medication to check').fill('aspirin');
    await page.keyboard.press('Enter');
    await page.getByRole('button', { name: /check now/i }).click();
    await page.getByRole('button', { name: /start a new check/i }).click();
    await expect(page.getByRole('button', { name: /^Remove / })).toHaveCount(0);
  });
});
