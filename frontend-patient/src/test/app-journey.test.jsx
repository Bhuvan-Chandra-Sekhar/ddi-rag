import { describe, expect, it, vi } from 'vitest';
import { render, renderHook, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from '../App.jsx';
import { useAppState } from '../state/AppStateContext.jsx';
import { findingTitle, findingUrgency } from '../meta.js';

// Real App, real api(), real components. Only `fetch` is faked, so the
// request bodies asserted here are exactly what would leave the browser.
// The Playwright suite repeats these journeys against the real Flask app.
const stubBackend = (routes) => {
  const handler = vi.fn(async (url, init = {}) => {
    const path = new URL(url).pathname;
    const route = routes[path];
    if (!route) return { ok: false, status: 404, json: async () => ({ error: `unexpected request to ${path}` }) };
    const result = await route(init.body ? JSON.parse(init.body) : undefined);
    const status = result.status ?? 200;
    return { ok: status < 400, status, json: async () => result.body };
  });
  vi.stubGlobal('fetch', handler);
  return handler;
};
const requestsTo = (fetchMock, path) =>
  fetchMock.mock.calls.filter(([url]) => new URL(url).pathname === path).map(([, init]) => JSON.parse(init.body));

const majorInteraction = {
  resolved_medications: [
    { input: 'aspirin', identity_confirmed: true },
    { input: 'warfarin', identity_confirmed: true },
  ],
  findings: [{
    index: 0, type: 'ddi', severity: 'major', clinical_effect: 'Raises bleeding risk.',
    patient_guidance: 'Ask your pharmacist.', see_a_doctor: false,
    patient_factors: { ingredient_a: 'aspirin', ingredient_b: 'warfarin' },
  }],
  overall_severity: 'major',
  see_a_doctor: false,
  ddi_coverage: { pairs_checked: 1, pairs_approved: 1, pairs_with_no_rule: 0, pairs_unreviewed: 0, pairs_rejected: 0, unmatched_pairs: [] },
};

const headerSignIn = () =>
  within(screen.getByRole('navigation', { name: 'Main navigation' })).getByRole('button', { name: /^sign in/i });

const startQuickCheck = async (user) => {
  await user.click(screen.getByRole('button', { name: 'Quick check' }));
  await user.type(screen.getByLabelText('Medication to check'), 'aspirin{Enter}');
  await user.type(screen.getByLabelText('Current medications'), 'warfarin{Enter}');
  await user.click(screen.getByRole('button', { name: /check now/i }));
};

describe('quick check journey', () => {
  it('goes from the homepage to results, sending exactly what was entered', async () => {
    const user = userEvent.setup();
    const backend = stubBackend({
      '/api/self-check': () => ({ body: majorInteraction }),
      '/api/explain': () => ({ body: { explanation: 'Both thin the blood.', citations: [] } }),
    });
    render(<App />);
    await startQuickCheck(user);

    expect(await screen.findByText('Interaction: aspirin + warfarin')).toBeInTheDocument();
    expect(requestsTo(backend, '/api/self-check')).toEqual([{ medications: ['aspirin', 'warfarin'], allergies: [] }]);
    expect(await screen.findByText('Both thin the blood.')).toBeInTheDocument();
    expect(requestsTo(backend, '/api/explain')).toEqual([{
      medications: ['aspirin', 'warfarin'], allergies: [], finding_index: 0, patient_notes: '',
    }]);
  });

  it('returns to the form with the server\'s message when the check fails', async () => {
    const user = userEvent.setup();
    stubBackend({
      '/api/self-check': () => ({
        status: 503,
        body: { error: 'temporarily_unavailable', message: 'This feature is temporarily disabled for maintenance.' },
      }),
    });
    render(<App />);
    await startQuickCheck(user);

    expect(await screen.findByRole('heading', { name: 'What are you checking?' })).toBeInTheDocument();
    const alert = screen.getByRole('alert');
    expect(alert).toHaveTextContent('This feature is temporarily disabled for maintenance.');
    expect(alert).not.toHaveTextContent('temporarily_unavailable');
    // The person's entries survive the failure.
    expect(screen.getByRole('button', { name: 'Remove aspirin' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Remove warfarin' })).toBeInTheDocument();
  });

  it('clears the previous error when the check is submitted again', async () => {
    const user = userEvent.setup();
    let attempt = 0;
    stubBackend({
      '/api/self-check': () => (++attempt === 1 ? { status: 500, body: { error: 'internal_error', message: 'Try again.' } } : { body: majorInteraction }),
      '/api/explain': () => ({ body: { explanation: 'ok', citations: [] } }),
    });
    render(<App />);
    await startQuickCheck(user);
    await screen.findByText('Try again.');
    await user.click(screen.getByRole('button', { name: /check now/i }));
    expect(await screen.findByText('Interaction: aspirin + warfarin')).toBeInTheDocument();
    expect(screen.queryByText('Try again.')).not.toBeInTheDocument();
  });

  it('"Start a new check" empties the form', async () => {
    const user = userEvent.setup();
    stubBackend({
      '/api/self-check': () => ({ body: majorInteraction }),
      '/api/explain': () => ({ body: { explanation: 'ok', citations: [] } }),
    });
    render(<App />);
    await startQuickCheck(user);
    await user.click(await screen.findByRole('button', { name: /start a new check/i }));
    expect(screen.getByRole('heading', { name: 'What are you checking?' })).toBeInTheDocument();
    expect(screen.queryAllByRole('button', { name: /^Remove / })).toHaveLength(0);
  });

  it('"Check a different drug" keeps the current medications but frees the checking field', async () => {
    const user = userEvent.setup();
    stubBackend({
      '/api/self-check': () => ({ body: majorInteraction }),
      '/api/explain': () => ({ body: { explanation: 'ok', citations: [] } }),
    });
    render(<App />);
    await startQuickCheck(user);
    await user.click(await screen.findByRole('button', { name: /check a different drug/i }));
    expect(screen.getByLabelText('Medication to check')).toHaveValue('');
    expect(screen.getByRole('button', { name: 'Remove warfarin' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Remove aspirin' })).not.toBeInTheDocument();
  });
});

describe('signing in', () => {
  it('opens the dashboard for a patient who signs in, and lists their cases', async () => {
    const user = userEvent.setup();
    const backend = stubBackend({
      '/api/auth/login': () => ({ body: { access_token: 'jwt-1', user: { id: 'u1', role: 'patient', full_name: 'Alex Rivera' } } }),
      '/v1/my/cases': () => ({ body: { cases: [{
        case_id: 'c1', state: 'awaiting_pharmacist_review', medication: 'Warfarin', created_at: null,
        has_findings: false, interaction_review: null, communications: [],
      }] } }),
    });
    render(<App />);
    await user.click(headerSignIn());
    await user.type(screen.getByLabelText('Email'), 'alex@example.com');
    await user.type(screen.getByLabelText('Password'), 'password1');
    await user.click(within(screen.getByRole('tabpanel')).getByRole('button', { name: 'Sign in' }));

    expect(await screen.findByText('Hi, Alex Rivera')).toBeInTheDocument();
    expect(await screen.findByText('Your pharmacist is reviewing this')).toBeInTheDocument();
    expect(sessionStorage.getItem('medtrust_token')).toBe('jwt-1');
    const cases = backend.mock.calls.find(([url]) => new URL(url).pathname === '/v1/my/cases');
    expect(cases[1].headers.Authorization).toBe('Bearer jwt-1');
  });

  it('sends a clinician to the clinical console only after a staff login', async () => {
    const user = userEvent.setup();
    const location = { href: 'http://localhost/', origin: 'http://localhost' };
    vi.stubGlobal('location', location);
    stubBackend({
      '/api/auth/login': () => ({ body: { access_token: 'staff-jwt', user: { role: 'pharmacist' } } }),
    });
    render(<App />);
    await user.click(screen.getByRole('button', { name: /clinic portal/i }));
    await user.type(screen.getByLabelText('Email'), 'pharm@example.com');
    await user.type(screen.getByLabelText('Password'), 'password1');
    await user.click(within(screen.getByRole('tabpanel')).getByRole('button', { name: 'Sign in' }));
    await vi.waitFor(() => expect(location.href).toBe('/clinical'));
    // The console boots on `cc_token`, and the patient keys stay untouched.
    expect(sessionStorage.getItem('cc_token')).toBe('staff-jwt');
    expect(JSON.parse(sessionStorage.getItem('cc_user'))).toEqual({ role: 'pharmacist' });
    expect(sessionStorage.getItem('medtrust_token')).toBeNull();
    expect(sessionStorage.getItem('medtrust_user')).toBeNull();
  });

  it('does not redirect a patient who tries the clinical sign-in', async () => {
    const user = userEvent.setup();
    const location = { href: 'http://localhost/', origin: 'http://localhost' };
    vi.stubGlobal('location', location);
    stubBackend({
      '/api/auth/login': () => ({ body: { access_token: 'jwt', user: { role: 'patient' } } }),
    });
    render(<App />);
    await user.click(screen.getByRole('button', { name: /clinic portal/i }));
    await user.type(screen.getByLabelText('Email'), 'patient@example.com');
    await user.type(screen.getByLabelText('Password'), 'password1');
    await user.click(within(screen.getByRole('tabpanel')).getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('does not have clinical console access');
    expect(location.href).toBe('http://localhost/');
    expect(sessionStorage.getItem('medtrust_token')).toBeNull();
  });

  it('falls back to the sign-in form when the stored token is gone by the time the dashboard shows', async () => {
    const user = userEvent.setup();
    sessionStorage.setItem('medtrust_token', 'stale');
    sessionStorage.setItem('medtrust_user', JSON.stringify({ full_name: 'Alex' }));
    stubBackend({ '/v1/my/cases': () => ({ status: 401, body: { msg: 'Token has expired' } }) });
    render(<App />);
    // The dashboard sees a 401, signs the session out and returns home.
    expect(await screen.findByRole('heading', { name: /uncovering what to know/i })).toBeInTheDocument();
    expect(sessionStorage.getItem('medtrust_token')).toBeNull();
    expect(headerSignIn()).toBeInTheDocument();
    await user.click(headerSignIn());
    expect(screen.getByRole('tablist')).toBeInTheDocument();
  });
});

describe('navigation', () => {
  it('marks the current section in the main navigation', async () => {
    const user = userEvent.setup();
    render(<App />);
    const nav = screen.getByRole('navigation', { name: 'Main navigation' });
    expect(within(nav).getByRole('button', { name: 'Overview' })).toHaveAttribute('aria-current', 'page');
    await user.click(within(nav).getByRole('button', { name: 'Quick check' }));
    expect(within(nav).getByRole('button', { name: 'Quick check' })).toHaveAttribute('aria-current', 'page');
    expect(within(nav).getByRole('button', { name: 'Overview' })).not.toHaveAttribute('aria-current');
    await user.click(screen.getByRole('button', { name: 'MedTrust Connect home' }));
    expect(screen.getByRole('heading', { name: /uncovering what to know/i })).toBeInTheDocument();
  });

  it('moves focus to the new view\'s heading after navigating, instead of stranding it on a removed button', async () => {
    const user = userEvent.setup();
    render(<App />);
    expect(document.body).toHaveFocus(); // first load does not steal focus
    const nav = screen.getByRole('navigation', { name: 'Main navigation' });
    await user.click(within(nav).getByRole('button', { name: 'Quick check' }));
    expect(screen.getByRole('heading', { name: 'What are you checking?' })).toHaveFocus();
    await user.click(within(nav).getByRole('button', { name: /^sign in/i }));
    expect(screen.getByRole('heading', { name: 'Welcome back' })).toHaveFocus();
  });

  it('falls back to focusing <main> when a view has no heading', async () => {
    const user = userEvent.setup();
    stubBackend({
      '/api/self-check': () => ({ body: { ...majorInteraction, findings: [], overall_severity: null, see_a_doctor: false } }),
    });
    render(<App />);
    await startQuickCheck(user);
    await screen.findByText('Your results');
    expect(document.activeElement.tagName).toBe('MAIN');
  });

  it('shows account links only while signed in', () => {
    sessionStorage.setItem('medtrust_token', 'jwt');
    sessionStorage.setItem('medtrust_user', JSON.stringify({ full_name: 'Alex' }));
    stubBackend({ '/v1/my/cases': () => ({ body: { cases: [] } }) });
    render(<App />);
    expect(screen.getByRole('button', { name: 'My prescriptions' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /sign out/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^sign in/i })).not.toBeInTheDocument();
  });
});

describe('useAppState', () => {
  it('refuses to be used outside its provider', () => {
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    expect(() => renderHook(() => useAppState())).toThrow(/within an AppStateProvider/);
    expect(errorSpy).toHaveBeenCalled();
  });
});

describe('finding presentation helpers', () => {
  it.each([
    [{ type: 'allergy', patient_factors: { ingredient: 'penicillin' } }, 'Matches a known allergy — penicillin'],
    [{ type: 'duplicate', patient_factors: { ingredient: 'aspirin', occurrence_count: 3 } }, 'Duplicate ingredient — aspirin appears 3×'],
    [{ type: 'duplicate', patient_factors: { ingredient: 'aspirin' } }, 'Duplicate ingredient — aspirin appears 2×'],
    [{ type: 'ddi', patient_factors: { ingredient_a: 'a', ingredient_b: 'b' } }, 'Interaction: a + b'],
    [{ type: 'ddi' }, 'Interaction: ? + ?'],
    [{ type: 'unknown', patient_factors: { ingredient_a: 'a', ingredient_b: 'b' } }, 'Unreviewed pairing: a + b'],
    [{ type: 'unknown' }, 'Unreviewed pairing: ? + ?'],
    [{ type: 'something_new' }, 'Finding'],
  ])('titles %j as "%s"', (finding, title) => {
    expect(findingTitle(finding)).toBe(title);
  });

  it('ranks an unreviewed finding by the higher of its severity and reported severity', () => {
    expect(findingUrgency({ severity: 'critical' })).toBeGreaterThan(findingUrgency({ severity: 'major' }));
    expect(findingUrgency({ severity: 'unknown', reported_severity: 'major' })).toBeGreaterThan(findingUrgency({ severity: 'caution' }));
    expect(findingUrgency({ severity: 'informational' })).toBe(0);
    expect(findingUrgency({ severity: 'not-a-severity' })).toBe(0);
  });
});
