import { accounts, control, expect, goTo, openApp, signInAs, storedToken, test } from './helpers.js';

// Real tokens signed and verified by flask-jwt-extended, real password
// hashing, real organisation list, real authorisation on /v1/my/cases.

const uniqueEmail = (prefix) => `${prefix}.${Date.now()}.${Math.floor(Math.random() * 1e6)}@e2e.test`;

async function openAuth(page) {
  await openApp(page);
  await goTo(page, /^sign in/i);
  await expect(page.getByRole('tablist')).toBeVisible();
}

test.describe('patient sign-in', () => {
  test('the seeded patient signs in and sees each case with the right status and wording', async ({ page }) => {
    await openAuth(page);
    await signInAs(page, accounts.patient, { via: 'none' });

    await expect(page.getByText(`Hi, ${accounts.patient.fullName}`)).toBeVisible();
    expect(await storedToken(page)).toBeTruthy();

    const card = (medication) => page.locator('div.card', { has: page.getByRole('heading', { name: medication }) });

    const pending = card('Lisinopril');
    await expect(pending.getByText('Your pharmacist is reviewing this')).toBeVisible();
    await expect(pending).toContainText('Pending clinical review');
    await expect(pending).toContainText("This isn't a guarantee of safety or risk");

    const released = card('Aspirin');
    await expect(released.getByText('Reviewed and ready')).toBeVisible();
    await expect(released).toContainText('Reviewed — your pharmacist has confirmed this');
    await expect(released).toContainText('E2E: your pharmacist reviewed this and released it.');

    const held = card('Metformin');
    await expect(held.getByText('On hold — contact your pharmacy')).toBeVisible();
  });

  test('a wrong password shows the server\'s message and stores no session', async ({ page }) => {
    await openAuth(page);
    await signInAs(page, { email: accounts.patient.email, password: 'definitely-wrong' }, { via: 'none' });
    await expect(page.getByRole('alert')).toHaveText('Invalid email or password.');
    expect(await storedToken(page)).toBeNull();
    await expect(page.getByRole('tabpanel').getByRole('button', { name: 'Sign in' })).toBeEnabled();
  });

  test('Enter in the password field signs in', async ({ page }) => {
    await openAuth(page);
    await page.getByLabel('Email').fill(accounts.patient.email);
    await page.getByLabel('Password').fill(accounts.patient.password);
    await page.keyboard.press('Enter');
    await expect(page.getByText(`Hi, ${accounts.patient.fullName}`)).toBeVisible();
  });

  test('a refresh keeps the session; signing out ends it', async ({ page }) => {
    await openAuth(page);
    await signInAs(page, accounts.patient, { via: 'none' });
    await expect(page.getByText(`Hi, ${accounts.patient.fullName}`)).toBeVisible();

    await page.reload();
    await expect(page.getByText(`Hi, ${accounts.patient.fullName}`)).toBeVisible();

    await page.getByRole('navigation', { name: 'Main navigation' }).getByRole('button', { name: /sign out/i }).click();
    await expect(page.getByRole('heading', { level: 1, name: /uncovering what to know/i })).toBeVisible();
    expect(await storedToken(page)).toBeNull();
    await expect(page.getByRole('navigation', { name: 'Main navigation' }).getByRole('button', { name: /^sign in/i })).toBeVisible();
  });
});

test.describe('real token handling', () => {
  test('the API refuses a request with no token or a forged one', async ({ request }) => {
    expect((await request.get('/v1/my/cases')).status()).toBe(401);
    const forged = await request.get('/v1/my/cases', { headers: { Authorization: 'Bearer not.a.real.token' } });
    expect([401, 422]).toContain(forged.status());
  });

  test('an expired token signs the person out instead of showing a dead end', async ({ page, request }) => {
    const expired = await control.expiredToken(request);
    await page.addInitScript((token) => {
      sessionStorage.setItem('medtrust_token', token);
      sessionStorage.setItem('medtrust_user', JSON.stringify({ full_name: 'Alex Rivera' }));
    }, expired);
    await page.goto('/patient');
    await expect(page.getByRole('heading', { level: 1, name: /uncovering what to know/i })).toBeVisible();
    expect(await storedToken(page)).toBeNull();
  });

  test('a garbled token signs the person out instead of showing "Request failed (422)"', async ({ page }) => {
    await page.addInitScript(() => {
      sessionStorage.setItem('medtrust_token', 'garbage-not-a-jwt');
      sessionStorage.setItem('medtrust_user', JSON.stringify({ full_name: 'Alex Rivera' }));
    });
    await page.goto('/patient');
    await expect(page.getByRole('heading', { level: 1, name: /uncovering what to know/i })).toBeVisible();
    await expect(page.getByText(/request failed/i)).toHaveCount(0);
    expect(await storedToken(page)).toBeNull();
  });
});

test.describe('creating an account', () => {
  test('registers through the real form, signs in automatically, and lands on an empty dashboard', async ({ page }) => {
    await openAuth(page);
    await page.getByRole('tab', { name: 'Create account' }).click();

    const organisation = page.getByLabel('Care organization');
    await expect(organisation.locator('option')).toHaveText([accounts.organization, accounts.otherOrganization]);

    const email = uniqueEmail('new.patient');
    await page.getByLabel('First name').fill('Sam');
    await page.getByLabel('Last name').fill('Lee');
    await organisation.selectOption({ label: accounts.otherOrganization });
    await page.getByLabel('Email').fill(email);
    await page.getByLabel('Password').fill('a-long-enough-password');
    await page.getByRole('tabpanel').getByRole('button', { name: 'Create account' }).click();

    await expect(page.getByText('Hi, Sam Lee')).toBeVisible();
    await expect(page.getByText('No prescriptions on file yet')).toBeVisible();
    expect(await storedToken(page)).toBeTruthy();

    // The account is real: it can sign in again from scratch.
    await page.getByRole('navigation', { name: 'Main navigation' }).getByRole('button', { name: /sign out/i }).click();
    await goTo(page, /^sign in/i);
    await signInAs(page, { email, password: 'a-long-enough-password' }, { via: 'none' });
    await expect(page.getByText('Hi, Sam Lee')).toBeVisible();
  });

  test('the browser blocks a password shorter than eight characters, so no request is sent', async ({ page }) => {
    const registrations = [];
    page.on('request', (request) => {
      if (request.url().endsWith('/api/auth/register')) registrations.push(request.url());
    });
    await openAuth(page);
    await page.getByRole('tab', { name: 'Create account' }).click();
    await page.getByLabel('First name').fill('Sam');
    await page.getByLabel('Last name').fill('Lee');
    await page.getByLabel('Email').fill(uniqueEmail('short'));
    await page.getByLabel('Password').fill('short');
    await page.getByRole('tabpanel').getByRole('button', { name: 'Create account' }).click();

    await expect(page.getByLabel('Password')).toHaveJSProperty('validity.tooShort', true);
    expect(registrations).toEqual([]);
    await expect(page.getByText(/^Hi, /)).toHaveCount(0);
  });

  test('an email that is already registered is refused with the server\'s message', async ({ page }) => {
    await openAuth(page);
    await page.getByRole('tab', { name: 'Create account' }).click();
    await page.getByLabel('First name').fill('Alex');
    await page.getByLabel('Last name').fill('Rivera');
    await page.getByLabel('Email').fill(accounts.patient.email);
    await page.getByLabel('Password').fill('a-long-enough-password');
    await page.getByRole('tabpanel').getByRole('button', { name: 'Create account' }).click();
    await expect(page.getByRole('alert')).toHaveText('An account with this email already exists.');
    expect(await storedToken(page)).toBeNull();
  });

  test('switching tabs clears the previous error', async ({ page }) => {
    await openAuth(page);
    await signInAs(page, { email: accounts.patient.email, password: 'wrong-password' }, { via: 'none' });
    await expect(page.getByRole('alert')).toBeVisible();
    await page.getByRole('tab', { name: 'Create account' }).click();
    await expect(page.getByRole('alert')).toHaveCount(0);
  });
});

test.describe('the clinical console hand-off', () => {
  const openClinicPortal = async (page) => {
    await openApp(page);
    await page.getByRole('button', { name: /clinic portal/i }).click();
    await expect(page.getByText('Clinical console').first()).toBeVisible();
  };

  test('a patient account is refused at the clinical sign-in and stays on the patient app', async ({ page }) => {
    await openClinicPortal(page);
    await signInAs(page, accounts.patient, { via: 'none' });
    await expect(page.getByRole('alert')).toContainText('does not have clinical console access');
    expect(await storedToken(page)).toBeNull();
    expect(new URL(page.url()).pathname).toBe('/patient');
  });

  test('a pharmacist is sent to the console and arrives already signed in', async ({ page }) => {
    await openClinicPortal(page);
    await signInAs(page, accounts.pharmacist, { via: 'none' });

    await page.waitForURL('**/clinical');
    await expect(page).toHaveTitle(/Clinical Console/);
    // The person just signed in. Landing on the console's own sign-in form
    // would mean the session did not carry across.
    await expect(page.locator('#login-form')).toBeHidden();
  });
});
