import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Auth from '../screens/Auth.jsx';
import Scanning from '../screens/Scanning.jsx';
import { api, setToken, setUser } from '../api.js';

vi.mock('../api.js', () => ({ api: vi.fn(), setToken: vi.fn(), setUser: vi.fn() }));

describe('authentication', () => {
  beforeEach(() => vi.clearAllMocks());

  it('logs in and persists the returned session', async () => {
    const user = userEvent.setup();
    const onAuthenticated = vi.fn();
    api.mockResolvedValue({ access_token: 'token-1', user: { id: 1, role: 'patient' } });
    render(<Auth onAuthenticated={onAuthenticated} onSkip={vi.fn()} />);
    await user.type(screen.getByLabelText('Email'), 'person@example.com');
    await user.type(screen.getByLabelText('Password'), 'password');
    await user.click(screen.getAllByRole('button', { name: 'Sign in' }).at(-1));
    await waitFor(() => expect(onAuthenticated).toHaveBeenCalledWith({ id: 1, role: 'patient' }));
    expect(setToken).toHaveBeenCalledWith('token-1');
    expect(setUser).toHaveBeenCalledWith({ id: 1, role: 'patient' });
  });

  it('shows login errors and permits retry', async () => {
    const user = userEvent.setup();
    api.mockRejectedValue(new Error('Invalid credentials'));
    render(<Auth onAuthenticated={vi.fn()} onSkip={vi.fn()} />);
    await user.type(screen.getByLabelText('Email'), 'person@example.com');
    await user.type(screen.getByLabelText('Password'), 'password');
    await user.click(screen.getAllByRole('button', { name: 'Sign in' }).at(-1));
    expect(await screen.findByRole('alert')).toHaveTextContent('Invalid credentials');
    expect(screen.getAllByRole('button', { name: 'Sign in' }).at(-1)).toBeEnabled();
  });

  it('rejects a patient account from the clinical console', async () => {
    const user = userEvent.setup();
    api.mockResolvedValue({ access_token: 'token-1', user: { role: 'patient' } });
    render(<Auth mode="clinician" onAuthenticated={vi.fn()} onSkip={vi.fn()} />);
    expect(screen.queryByRole('button', { name: 'Create account' })).not.toBeInTheDocument();
    await user.type(screen.getByLabelText('Email'), 'person@example.com');
    await user.type(screen.getByLabelText('Password'), 'password');
    await user.click(screen.getAllByRole('button', { name: 'Sign in' }).at(-1));
    expect(await screen.findByRole('alert')).toHaveTextContent('does not have clinical console access');
    expect(setToken).not.toHaveBeenCalled();
  });

  it('loads organizations, registers, then logs the new user in', async () => {
    const user = userEvent.setup();
    api.mockResolvedValueOnce({ organizations: [{ id: 7, name: 'Community Health' }] })
      .mockResolvedValueOnce({ ok: true })
      .mockResolvedValueOnce({ access_token: 'new-token', user: { id: 2, role: 'patient' } });
    const onAuthenticated = vi.fn();
    render(<Auth onAuthenticated={onAuthenticated} onSkip={vi.fn()} />);
    await user.click(screen.getByRole('button', { name: 'Create account' }));
    expect(await screen.findByRole('option', { name: 'Community Health' })).toBeInTheDocument();
    await user.type(screen.getByLabelText('First name'), 'Sam');
    await user.type(screen.getByLabelText('Last name'), 'Lee');
    await user.type(screen.getByLabelText('Email'), 'sam@example.com');
    await user.type(screen.getByLabelText('Password'), 'password1');
    await user.click(screen.getAllByRole('button', { name: 'Create account' }).at(-1));
    await waitFor(() => expect(onAuthenticated).toHaveBeenCalled());
    expect(api).toHaveBeenNthCalledWith(2, '/api/auth/register', expect.objectContaining({ method: 'POST' }));
    expect(api).toHaveBeenNthCalledWith(3, '/api/auth/login', expect.objectContaining({ method: 'POST' }));
  });

  it('disables registration when no organizations are available', async () => {
    const user = userEvent.setup();
    api.mockResolvedValue({ organizations: [] });
    render(<Auth onAuthenticated={vi.fn()} onSkip={vi.fn()} />);
    await user.click(screen.getByRole('button', { name: 'Create account' }));
    expect(await screen.findByText(/account creation is unavailable/i)).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: 'Create account' }).at(-1)).toBeDisabled();
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
