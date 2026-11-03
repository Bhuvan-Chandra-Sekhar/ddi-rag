import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Home from '../screens/Home.jsx';
import App from '../App.jsx';

describe('homepage paths', () => {
  it.each([
    ['Quick check', 'checker'],
    ['Patient portal', 'auth'],
    ['Clinic portal', 'clinician'],
  ])('routes %s to %s', async (label, destination) => {
    const user = userEvent.setup();
    const onNav = vi.fn();
    render(<Home onNav={onNav} />);
    await user.click(screen.getByRole('button', { name: new RegExp(label, 'i') }));
    expect(onNav).toHaveBeenCalledWith(destination);
  });

  it('exposes the scroll journey landmarks and exactly three choices', () => {
    render(<Home onNav={vi.fn()} />);
    expect(screen.getByRole('heading', { name: /uncovering what to know/i })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /your medications/i })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Choose your path' })).toBeInTheDocument();
    expect(screen.getAllByRole('button')).toHaveLength(3);
  });
});

describe('top-level patient journey', () => {
  beforeEach(() => sessionStorage.clear());

  it('starts signed-out users on the homepage and navigates to quick check', async () => {
    const user = userEvent.setup();
    render(<App />);
    expect(screen.getByRole('heading', { name: /uncovering what to know/i })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Quick check' }));
    expect(screen.getByRole('heading', { name: 'What are you checking?' })).toBeInTheDocument();
    expect(window.scrollTo).toHaveBeenCalled();
  });

  it('starts a stored session on the prescription dashboard', async () => {
    sessionStorage.setItem('medtrust_token', 'token');
    sessionStorage.setItem('medtrust_user', JSON.stringify({ full_name: 'Alex' }));
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ cases: [] }) }));
    render(<App />);
    expect(screen.getByText('Hi, Alex')).toBeInTheDocument();
    expect(await screen.findByText('No prescriptions on file yet')).toBeInTheDocument();
  });

  it('signs out by clearing the session and returning home', async () => {
    const user = userEvent.setup();
    sessionStorage.setItem('medtrust_token', 'token');
    sessionStorage.setItem('medtrust_user', JSON.stringify({ full_name: 'Alex' }));
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ cases: [] }) }));
    render(<App />);
    await user.click(screen.getByRole('button', { name: /sign out/i }));
    expect(sessionStorage.getItem('medtrust_token')).toBeNull();
    expect(screen.getByRole('heading', { name: /uncovering what to know/i })).toBeInTheDocument();
  });
});
