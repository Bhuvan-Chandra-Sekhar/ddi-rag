import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Dashboard from '../screens/Dashboard.jsx';
import DrugInfoPanel from '../components/DrugInfoPanel.jsx';
import Explanation from '../components/Explanation.jsx';
import { api } from '../api.js';

vi.mock('../api.js', async (original) => {
  const actual = await original();
  return { ...actual, api: vi.fn(), getUser: vi.fn(() => ({ full_name: 'Alex Rivera' })) };
});

describe('patient dashboard', () => {
  beforeEach(() => vi.clearAllMocks());

  it('shows the signed-in patient and empty state', async () => {
    api.mockResolvedValue({ cases: [] });
    render(<Dashboard onSessionExpired={vi.fn()} />);
    expect(screen.getByText('Hi, Alex Rivera')).toBeInTheDocument();
    expect(await screen.findByText('No prescriptions on file yet')).toBeInTheDocument();
  });

  it('renders reviewed and pending prescription states', async () => {
    api.mockResolvedValue({ cases: [
      { id: 1, medication: 'Warfarin', state: 'review', has_findings: true, interaction_review: 'pending', communications: [] },
      { id: 2, medication: 'Aspirin', state: 'ready', has_findings: true, interaction_review: 'complete', communications: [{ explanation: 'Reviewed message' }] },
    ] });
    render(<Dashboard onSessionExpired={vi.fn()} />);
    expect(await screen.findByText('Warfarin')).toBeInTheDocument();
    expect(screen.getByText(/pending clinical review/i)).toBeInTheDocument();
    expect(screen.getByText(/reviewed — your pharmacist/i)).toBeInTheDocument();
    expect(screen.getByText('Reviewed message')).toBeInTheDocument();
  });

  it('expires the session on authentication errors and shows other errors', async () => {
    const onSessionExpired = vi.fn();
    api.mockRejectedValueOnce(new Error('Request failed (401)'));
    const first = render(<Dashboard onSessionExpired={onSessionExpired} />);
    await waitFor(() => expect(onSessionExpired).toHaveBeenCalled());
    first.unmount();
    api.mockRejectedValueOnce(new Error('Database offline'));
    render(<Dashboard onSessionExpired={vi.fn()} />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Database offline');
  });
});

describe('drug information and explanations', () => {
  it('does not show unrelated label content for an unrecognized drug', async () => {
    api.mockResolvedValue({ detected_drugs: [], results: [{ answer: 'Unrelated answer' }] });
    render(<DrugInfoPanel med={{ input: 'mysterypill' }} />);
    expect(await screen.findByText(/don't have FDA label data indexed/i)).toBeInTheDocument();
    expect(screen.queryByText('Unrelated answer')).not.toBeInTheDocument();
  });

  it('renders an escaped FDA summary for a recognized drug', async () => {
    api.mockResolvedValue({ detected_drugs: ['aspirin'], results: [{ answer: '**Use care** <unsafe>' }] });
    render(<DrugInfoPanel med={{ input: 'aspirin' }} />);
    expect(await screen.findByText('Use care')).toBeInTheDocument();
    expect(screen.getByText('<unsafe>')).toBeInTheDocument();
    expect(document.querySelector('unsafe')).toBeNull();
  });

  it('retries a failed explanation and renders citations', async () => {
    const user = userEvent.setup();
    api.mockRejectedValueOnce(new Error('Explanation unavailable'))
      .mockResolvedValueOnce({ explanation: 'Ask your pharmacist.', citations: [{ generic_name: 'aspirin', section: 'drug_interactions', text: 'Source text' }] });
    render(<Explanation findingIndex={3} inputs={{ medications: ['aspirin'], allergies: [], notes: '' }} />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Explanation unavailable');
    await user.click(screen.getByRole('button', { name: /try again/i }));
    expect(await screen.findByText('Ask your pharmacist.')).toBeInTheDocument();
    expect(screen.getByText('Show 1 source')).toBeInTheDocument();
  });
});
