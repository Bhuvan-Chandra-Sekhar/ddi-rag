import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Auth from '../screens/Auth.jsx';
import Scanning from '../screens/Scanning.jsx';
import { api, setConsoleSession, setToken, setUser } from '../api.js';

vi.mock('../api.js', () => ({ api: vi.fn(), setToken: vi.fn(), setUser: vi.fn(), setConsoleSession: vi.fn() }));

// Scoped to the active tab panel: the tab and the submit button are
// different roles now, so these queries are unambiguous without picking
// "the last match".
const panel = () => screen.getByRole('tabpanel');
const submitButton = (name) => within(panel()).getByRole('button', { name });
const bodyOf = (callIndex) => JSON.parse(api.mock.calls[callIndex][1].body);

const fillLogin = async (user, email = 'person@example.com', password = 'password') => {
  await user.type(within(panel()).getByLabelText('Email'), email);
  await user.type(within(panel()).getByLabelText('Password'), password);
};

const fillRegistration = async (user) => {
  await user.type(screen.getByLabelText('First name'), 'Sam');
  await user.type(screen.getByLabelText('Last name'), 'Lee');
  await user.type(screen.getByLabelText('Email'), 'sam@example.com');
  await user.type(screen.getByLabelText('Password'), 'password1');
};

const organizations = { organizations: [{ id: '7', name: 'Community Health' }, { id: '9', name: 'Riverside Clinic' }] };

describe('authentication tabs', () => {
  it('exposes a tablist with one selected tab and a labelled panel', () => {
    render(<Auth onAuthenticated={vi.fn()} onSkip={vi.fn()} />);
    expect(screen.getByRole('tablist')).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Sign in' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tab', { name: 'Create account' })).toHaveAttribute('aria-selected', 'false');
    expect(panel()).toHaveAccessibleName('Sign in');
  });

  it('gives the tab and the submit button different roles, so "Sign in" is never ambiguous', () => {
    render(<Auth onAuthenticated={vi.fn()} onSkip={vi.fn()} />);
    expect(screen.getAllByRole('button', { name: 'Sign in' })).toHaveLength(1);
    expect(screen.getAllByRole('tab', { name: 'Sign in' })).toHaveLength(1);
  });

  it('keeps only the selected tab in the keyboard Tab order', () => {
    render(<Auth onAuthenticated={vi.fn()} onSkip={vi.fn()} />);
    expect(screen.getByRole('tab', { name: 'Sign in' })).toHaveAttribute('tabindex', '0');
    expect(screen.getByRole('tab', { name: 'Create account' })).toHaveAttribute('tabindex', '-1');
  });

  it('moves between tabs with the arrow, Home and End keys and moves focus with them', async () => {
    const user = userEvent.setup();
    api.mockResolvedValue(organizations);
    render(<Auth onAuthenticated={vi.fn()} onSkip={vi.fn()} />);
    const signIn = screen.getByRole('tab', { name: 'Sign in' });
    const create = screen.getByRole('tab', { name: 'Create account' });

    signIn.focus();
    await user.keyboard('{ArrowRight}');
    expect(create).toHaveAttribute('aria-selected', 'true');
    expect(create).toHaveFocus();
    expect(panel()).toHaveAccessibleName('Create account');

    await user.keyboard('{ArrowRight}');
    expect(signIn).toHaveAttribute('aria-selected', 'true');
    expect(signIn).toHaveFocus();

    await user.keyboard('{ArrowLeft}');
    expect(create).toHaveAttribute('aria-selected', 'true');

    await user.keyboard('{Home}');
    expect(signIn).toHaveAttribute('aria-selected', 'true');
    await user.keyboard('{End}');
    expect(create).toHaveAttribute('aria-selected', 'true');
  });

  it('clears an old error when switching tabs', async () => {
    const user = userEvent.setup();
    api.mockRejectedValueOnce(new Error('Invalid credentials')).mockResolvedValue(organizations);
    render(<Auth onAuthenticated={vi.fn()} onSkip={vi.fn()} />);
    await fillLogin(user);
    await user.click(submitButton('Sign in'));
    expect(await screen.findByRole('alert')).toHaveTextContent('Invalid credentials');
    await user.click(screen.getByRole('tab', { name: 'Create account' }));
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('offers the quick check instead of an account', async () => {
    const user = userEvent.setup();
    const onSkip = vi.fn();
    render(<Auth onAuthenticated={vi.fn()} onSkip={onSkip} />);
    await user.click(screen.getByRole('button', { name: /try the quick check instead/i }));
    expect(onSkip).toHaveBeenCalledOnce();
  });
});

describe('sign in', () => {
  it('posts the credentials, persists the returned session, and reports the user', async () => {
    const user = userEvent.setup();
    const onAuthenticated = vi.fn();
    api.mockResolvedValue({ access_token: 'token-1', user: { id: 1, role: 'patient' } });
    render(<Auth onAuthenticated={onAuthenticated} onSkip={vi.fn()} />);
    await fillLogin(user);
    await user.click(submitButton('Sign in'));
    await waitFor(() => expect(onAuthenticated).toHaveBeenCalledWith({ id: 1, role: 'patient' }));
    expect(api).toHaveBeenCalledWith('/api/auth/login', expect.objectContaining({ method: 'POST' }));
    expect(bodyOf(0)).toEqual({ email: 'person@example.com', password: 'password' });
    expect(setToken).toHaveBeenCalledWith('token-1');
    expect(setUser).toHaveBeenCalledWith({ id: 1, role: 'patient' });
  });

  it('submits with the Enter key', async () => {
    const user = userEvent.setup();
    api.mockResolvedValue({ access_token: 't', user: { role: 'patient' } });
    render(<Auth onAuthenticated={vi.fn()} onSkip={vi.fn()} />);
    await user.type(within(panel()).getByLabelText('Email'), 'person@example.com');
    await user.type(within(panel()).getByLabelText('Password'), 'password{Enter}');
    await waitFor(() => expect(api).toHaveBeenCalledTimes(1));
  });

  it('shows login errors, re-enables the button, and clears the error on a successful retry', async () => {
    const user = userEvent.setup();
    const onAuthenticated = vi.fn();
    api.mockRejectedValueOnce(new Error('Invalid credentials'))
      .mockResolvedValueOnce({ access_token: 't', user: { role: 'patient' } });
    render(<Auth onAuthenticated={onAuthenticated} onSkip={vi.fn()} />);
    await fillLogin(user);
    await user.click(submitButton('Sign in'));
    expect(await screen.findByRole('alert')).toHaveTextContent('Invalid credentials');
    expect(submitButton('Sign in')).toBeEnabled();
    await user.click(submitButton('Sign in'));
    await waitFor(() => expect(onAuthenticated).toHaveBeenCalled());
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('sends one request when the form is submitted twice in the same tick', async () => {
    let finish;
    api.mockReturnValue(new Promise((resolve) => { finish = resolve; }));
    render(<Auth onAuthenticated={vi.fn()} onSkip={vi.fn()} />);
    fireEvent.change(within(panel()).getByLabelText('Email'), { target: { value: 'person@example.com' } });
    fireEvent.change(within(panel()).getByLabelText('Password'), { target: { value: 'password' } });
    const form = panel().querySelector('form');
    fireEvent.submit(form);
    fireEvent.submit(form);
    expect(api).toHaveBeenCalledTimes(1);
    expect(submitButton('Signing in…')).toBeDisabled();
    finish({ access_token: 't', user: { role: 'patient' } });
  });

  it('rejects a patient account from the clinical console without storing a session', async () => {
    const user = userEvent.setup();
    api.mockResolvedValue({ access_token: 'token-1', user: { role: 'patient' } });
    render(<Auth mode="clinician" onAuthenticated={vi.fn()} onSkip={vi.fn()} />);
    expect(screen.queryByRole('tab', { name: 'Create account' })).not.toBeInTheDocument();
    await fillLogin(user);
    await user.click(submitButton('Sign in'));
    expect(await screen.findByRole('alert')).toHaveTextContent('does not have clinical console access');
    expect(setToken).not.toHaveBeenCalled();
    expect(setUser).not.toHaveBeenCalled();
    expect(setConsoleSession).not.toHaveBeenCalled();
  });

  it.each(['pharmacist', 'prescriber', 'safety_officer', 'administrator'])(
    'admits a %s to the clinical console, storing the session where the console looks for it',
    async (role) => {
      const user = userEvent.setup();
      const onAuthenticated = vi.fn();
      api.mockResolvedValue({ access_token: 'staff-token', user: { role } });
      render(<Auth mode="clinician" onAuthenticated={onAuthenticated} onSkip={vi.fn()} />);
      await fillLogin(user);
      await user.click(submitButton('Sign in'));
      await waitFor(() => expect(onAuthenticated).toHaveBeenCalledWith({ role }));
      expect(setConsoleSession).toHaveBeenCalledWith('staff-token', { role });
      // A staff token must not become the patient app's session.
      expect(setToken).not.toHaveBeenCalled();
      expect(setUser).not.toHaveBeenCalled();
    }
  );

  it('keeps a patient sign-in on the patient session keys', async () => {
    const user = userEvent.setup();
    api.mockResolvedValue({ access_token: 'patient-token', user: { role: 'patient' } });
    render(<Auth onAuthenticated={vi.fn()} onSkip={vi.fn()} />);
    await fillLogin(user);
    await user.click(submitButton('Sign in'));
    await waitFor(() => expect(setToken).toHaveBeenCalledWith('patient-token'));
    expect(setConsoleSession).not.toHaveBeenCalled();
  });
});

describe('create account', () => {
  const openRegistration = async (user) => {
    await user.click(screen.getByRole('tab', { name: 'Create account' }));
    await screen.findByRole('option', { name: 'Community Health' });
  };

  it('sends every field the backend expects, then signs the new user in', async () => {
    const user = userEvent.setup();
    const onAuthenticated = vi.fn();
    api.mockResolvedValueOnce(organizations)
      .mockResolvedValueOnce({ user: { id: 2 } })
      .mockResolvedValueOnce({ access_token: 'new-token', user: { id: 2, role: 'patient' } });
    render(<Auth onAuthenticated={onAuthenticated} onSkip={vi.fn()} />);
    await openRegistration(user);
    await fillRegistration(user);
    await user.click(submitButton('Create account'));
    await waitFor(() => expect(onAuthenticated).toHaveBeenCalledWith({ id: 2, role: 'patient' }));

    expect(api).toHaveBeenNthCalledWith(1, '/v1/organizations');
    expect(api).toHaveBeenNthCalledWith(2, '/api/auth/register', expect.objectContaining({ method: 'POST' }));
    expect(bodyOf(1)).toEqual({
      email: 'sam@example.com',
      password: 'password1',
      first_name: 'Sam',
      last_name: 'Lee',
      full_name: 'Sam Lee',
      organization_id: '7',
    });
    expect(api).toHaveBeenNthCalledWith(3, '/api/auth/login', expect.objectContaining({ method: 'POST' }));
    expect(bodyOf(2)).toEqual({ email: 'sam@example.com', password: 'password1' });
    expect(setToken).toHaveBeenCalledWith('new-token');
    expect(setUser).toHaveBeenCalledWith({ id: 2, role: 'patient' });
  });

  it('sends the organization the person actually selected', async () => {
    const user = userEvent.setup();
    api.mockResolvedValueOnce(organizations)
      .mockResolvedValueOnce({})
      .mockResolvedValueOnce({ access_token: 't', user: { role: 'patient' } });
    render(<Auth onAuthenticated={vi.fn()} onSkip={vi.fn()} />);
    await openRegistration(user);
    await user.selectOptions(screen.getByLabelText('Care organization'), 'Riverside Clinic');
    await fillRegistration(user);
    await user.click(submitButton('Create account'));
    await waitFor(() => expect(api).toHaveBeenCalledTimes(3));
    expect(bodyOf(1).organization_id).toBe('9');
  });

  it('submits with the Enter key', async () => {
    const user = userEvent.setup();
    api.mockResolvedValueOnce(organizations)
      .mockResolvedValueOnce({})
      .mockResolvedValueOnce({ access_token: 't', user: { role: 'patient' } });
    render(<Auth onAuthenticated={vi.fn()} onSkip={vi.fn()} />);
    await openRegistration(user);
    await user.type(screen.getByLabelText('First name'), 'Sam');
    await user.type(screen.getByLabelText('Last name'), 'Lee');
    await user.type(screen.getByLabelText('Email'), 'sam@example.com');
    await user.type(screen.getByLabelText('Password'), 'password1{Enter}');
    await waitFor(() => expect(api).toHaveBeenCalledWith('/api/auth/register', expect.anything()));
  });

  it('declares the eight-character minimum and required fields to the browser', async () => {
    // jsdom does not enforce minlength for typed values, so whether the
    // browser actually blocks a short password is proven in the Playwright
    // suite (e2e/auth.spec.js). Here we pin that the constraint is declared.
    const user = userEvent.setup();
    api.mockResolvedValueOnce(organizations);
    render(<Auth onAuthenticated={vi.fn()} onSkip={vi.fn()} />);
    await openRegistration(user);
    expect(screen.getByLabelText('Password')).toHaveAttribute('minlength', '8');
    for (const label of ['First name', 'Last name', 'Email', 'Password', 'Care organization']) {
      expect(screen.getByLabelText(label)).toBeRequired();
    }
  });

  it('shows the server\'s message if a too-short password reaches it anyway', async () => {
    const user = userEvent.setup();
    api.mockResolvedValueOnce(organizations).mockRejectedValueOnce(new Error('Password must be at least 8 characters'));
    render(<Auth onAuthenticated={vi.fn()} onSkip={vi.fn()} />);
    await openRegistration(user);
    await fillRegistration(user);
    await user.click(submitButton('Create account'));
    expect(await screen.findByRole('alert')).toHaveTextContent('Password must be at least 8 characters');
  });

  it('shows the server error when registration fails, and never attempts a sign-in', async () => {
    const user = userEvent.setup();
    api.mockResolvedValueOnce(organizations).mockRejectedValueOnce(new Error('Email already registered'));
    render(<Auth onAuthenticated={vi.fn()} onSkip={vi.fn()} />);
    await openRegistration(user);
    await fillRegistration(user);
    await user.click(submitButton('Create account'));
    expect(await screen.findByRole('alert')).toHaveTextContent('Email already registered');
    expect(api).toHaveBeenCalledTimes(2);
    expect(setToken).not.toHaveBeenCalled();
    expect(submitButton('Create account')).toBeEnabled();
  });

  it('explains plainly when the account was created but the automatic sign-in failed', async () => {
    const user = userEvent.setup();
    const onAuthenticated = vi.fn();
    api.mockResolvedValueOnce(organizations)
      .mockResolvedValueOnce({})
      .mockRejectedValueOnce(new Error('Service unavailable'));
    render(<Auth onAuthenticated={onAuthenticated} onSkip={vi.fn()} />);
    await openRegistration(user);
    await fillRegistration(user);
    await user.click(submitButton('Create account'));
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(/your account was created/i);
    expect(alert).toHaveTextContent(/service unavailable/i);
    expect(alert).toHaveTextContent(/use sign in/i);
    expect(onAuthenticated).not.toHaveBeenCalled();
    expect(setToken).not.toHaveBeenCalled();
  });

  it('sends one registration when the form is submitted twice in the same tick', async () => {
    const user = userEvent.setup();
    let finish;
    api.mockResolvedValueOnce(organizations).mockReturnValueOnce(new Promise((resolve) => { finish = resolve; }));
    render(<Auth onAuthenticated={vi.fn()} onSkip={vi.fn()} />);
    await openRegistration(user);
    await fillRegistration(user);
    const form = panel().querySelector('form');
    fireEvent.submit(form);
    fireEvent.submit(form);
    expect(api.mock.calls.filter(([path]) => path === '/api/auth/register')).toHaveLength(1);
    finish({});
  });

  it('disables registration when no organizations are available', async () => {
    const user = userEvent.setup();
    api.mockResolvedValue({ organizations: [] });
    render(<Auth onAuthenticated={vi.fn()} onSkip={vi.fn()} />);
    await user.click(screen.getByRole('tab', { name: 'Create account' }));
    expect(await screen.findByText(/account creation is unavailable/i)).toBeInTheDocument();
    expect(submitButton('Create account')).toBeDisabled();
  });

  it('disables registration when the organization list cannot be loaded', async () => {
    const user = userEvent.setup();
    api.mockRejectedValue(new Error('Could not reach the server.'));
    render(<Auth onAuthenticated={vi.fn()} onSkip={vi.fn()} />);
    await user.click(screen.getByRole('tab', { name: 'Create account' }));
    expect(await screen.findByText(/account creation is unavailable/i)).toBeInTheDocument();
    expect(submitButton('Create account')).toBeDisabled();
  });
});

describe('scanning request', () => {
  it('submits medications and allergies and returns the result', async () => {
    const onDone = vi.fn();
    api.mockResolvedValue({ findings: [] });
    render(<Scanning medications={['aspirin', 'warfarin']} allergies={['penicillin']} onDone={onDone} onError={vi.fn()} />);
    await waitFor(() => expect(onDone).toHaveBeenCalledWith({ findings: [] }));
    expect(api).toHaveBeenCalledWith('/api/self-check', {
      method: 'POST',
      body: JSON.stringify({ medications: ['aspirin', 'warfarin'], allergies: ['penicillin'] }),
    });
  });

  it('returns API errors to the parent', async () => {
    const onError = vi.fn();
    api.mockRejectedValue(new Error('Service unavailable'));
    render(<Scanning medications={['aspirin']} allergies={[]} onDone={vi.fn()} onError={onError} />);
    await waitFor(() => expect(onError).toHaveBeenCalledWith('Service unavailable'));
  });
});
