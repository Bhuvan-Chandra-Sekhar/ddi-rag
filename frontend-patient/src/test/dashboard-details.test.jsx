import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Dashboard from '../screens/Dashboard.jsx';
import DrugInfoPanel from '../components/DrugInfoPanel.jsx';
import Explanation from '../components/Explanation.jsx';
import { api } from '../api.js';
import { STATE_META } from '../meta.js';

vi.mock('../api.js', async (original) => {
  const actual = await original();
  return { ...actual, api: vi.fn(), getUser: vi.fn(() => ({ full_name: 'Alex Rivera' })) };
});

// The workflow states the backend can actually send (SafetyCaseState in
// ddi_rag/enums.py). tests/test_frontend_contract.py asserts this list and
// the enum stay identical, so a state added on the backend fails CI until
// the frontend learns it.
const BACKEND_STATES = [
  'draft', 'awaiting_analysis', 'awaiting_pharmacist_review', 'awaiting_prescriber_response',
  'escalated', 'ready_to_dispense', 'held_or_cancelled', 'closed',
];

// Shaped exactly like one entry of GET /v1/my/cases.
const realCase = (overrides = {}) => ({
  case_id: 'case-1',
  state: 'awaiting_pharmacist_review',
  medication: 'Warfarin',
  created_at: '2026-03-02T10:00:00',
  has_findings: false,
  interaction_review: null,
  communications: [],
  ...overrides,
});

describe('patient dashboard', () => {
  it('shows the signed-in patient and empty state', async () => {
    api.mockResolvedValue({ cases: [] });
    render(<Dashboard onSessionExpired={vi.fn()} />);
    expect(screen.getByText('Hi, Alex Rivera')).toBeInTheDocument();
    expect(await screen.findByText('No prescriptions on file yet')).toBeInTheDocument();
    expect(api).toHaveBeenCalledWith('/v1/my/cases');
  });

  it('knows a label for every state the backend can send', () => {
    expect(Object.keys(STATE_META).sort()).toEqual([...BACKEND_STATES].sort());
  });

  it.each([
    ['draft', 'Getting started'],
    ['awaiting_analysis', 'Reviewing your prescription'],
    ['awaiting_pharmacist_review', 'Your pharmacist is reviewing this'],
    ['awaiting_prescriber_response', 'Checking with your prescriber'],
    ['escalated', 'Under urgent review'],
    ['ready_to_dispense', 'Reviewed and ready'],
    ['held_or_cancelled', 'On hold — contact your pharmacy'],
    ['closed', 'Complete'],
  ])('shows the %s state as "%s"', async (state, label) => {
    api.mockResolvedValue({ cases: [realCase({ state })] });
    render(<Dashboard onSessionExpired={vi.fn()} />);
    expect(await screen.findByText(label)).toBeInTheDocument();
  });

  it('falls back to the neutral badge for a state it does not recognise, rather than inventing one', async () => {
    api.mockResolvedValue({ cases: [realCase({ state: 'review' })] });
    render(<Dashboard onSessionExpired={vi.fn()} />);
    expect(await screen.findByText('Getting started')).toBeInTheDocument();
  });

  it('shows a pending-review warning and the generic body when nothing has been sent yet', async () => {
    api.mockResolvedValue({ cases: [realCase({ has_findings: true, interaction_review: 'pending' })] });
    render(<Dashboard onSessionExpired={vi.fn()} />);
    expect(await screen.findByText(/pending clinical review/i)).toBeInTheDocument();
    expect(screen.queryByText(/reviewed — your pharmacist/i)).not.toBeInTheDocument();
    expect(screen.getByText(/isn't a guarantee of safety or risk/i)).toBeInTheDocument();
    expect(screen.getByText(/your Warfarin prescription/i)).toBeInTheDocument();
  });

  it('shows the reviewed confirmation and the pharmacist message when review is complete', async () => {
    api.mockResolvedValue({ cases: [realCase({
      medication: 'Aspirin', state: 'ready_to_dispense', has_findings: true, interaction_review: 'reviewed',
      communications: [{ explanation: 'Reviewed message', delivered_at: '2026-03-03T09:00:00' }],
    })] });
    render(<Dashboard onSessionExpired={vi.fn()} />);
    expect(await screen.findByText(/reviewed — your pharmacist has confirmed/i)).toBeInTheDocument();
    expect(screen.getByText('Reviewed message')).toBeInTheDocument();
    expect(screen.getByText('Reviewed and ready')).toBeInTheDocument();
    expect(screen.queryByText(/pending clinical review/i)).not.toBeInTheDocument();
  });

  it('shows neither review banner when a case has no findings', async () => {
    api.mockResolvedValue({ cases: [realCase()] });
    render(<Dashboard onSessionExpired={vi.fn()} />);
    await screen.findByText('Warfarin');
    expect(screen.queryByText(/pending clinical review/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/reviewed — your pharmacist/i)).not.toBeInTheDocument();
  });

  it('renders one card per case, each with its own badge and no duplicate-key warning', async () => {
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    api.mockResolvedValue({ cases: [
      realCase({ case_id: 'a', medication: 'Warfarin', state: 'awaiting_pharmacist_review' }),
      realCase({ case_id: 'b', medication: 'Aspirin', state: 'closed' }),
    ] });
    render(<Dashboard onSessionExpired={vi.fn()} />);
    const warfarin = (await screen.findByText('Warfarin')).closest('.card');
    const aspirin = screen.getByText('Aspirin').closest('.card');
    expect(within(warfarin).getByText('Your pharmacist is reviewing this')).toBeInTheDocument();
    expect(within(aspirin).getByText('Complete')).toBeInTheDocument();
    expect(errorSpy.mock.calls.flat().join(' ')).not.toMatch(/unique "key"|same key/i);
  });

  it('formats the created date when present and omits it when absent', async () => {
    api.mockResolvedValue({ cases: [
      realCase({ case_id: 'a', medication: 'Dated', created_at: '2026-03-02T10:00:00' }),
      realCase({ case_id: 'b', medication: 'Undated', created_at: null }),
    ] });
    render(<Dashboard onSessionExpired={vi.fn()} />);
    const dated = (await screen.findByText('Dated')).closest('.card');
    expect(within(dated).getByText(/2026/)).toBeInTheDocument();
    const undated = screen.getByText('Undated').closest('.card');
    expect(within(undated).queryByText(/20\d\d/)).not.toBeInTheDocument();
  });

  it('expires the session on authentication errors and shows other errors', async () => {
    const onSessionExpired = vi.fn();
    api.mockRejectedValueOnce(new Error('Request failed (401)'));
    const first = render(<Dashboard onSessionExpired={onSessionExpired} />);
    await waitFor(() => expect(onSessionExpired).toHaveBeenCalled());
    first.unmount();

    const otherExpired = vi.fn();
    api.mockRejectedValueOnce(new Error('Database offline'));
    render(<Dashboard onSessionExpired={otherExpired} />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Database offline');
    expect(otherExpired).not.toHaveBeenCalled();
  });

  it('also treats a token error message as an expired session', async () => {
    const onSessionExpired = vi.fn();
    api.mockRejectedValueOnce(new Error('Token has expired'));
    render(<Dashboard onSessionExpired={onSessionExpired} />);
    await waitFor(() => expect(onSessionExpired).toHaveBeenCalled());
  });

  it('treats a malformed or wrongly signed token (HTTP 422) as an unusable session, not a dead-end error', async () => {
    const onSessionExpired = vi.fn();
    api.mockRejectedValueOnce(new Error('Request failed (422)'));
    render(<Dashboard onSessionExpired={onSessionExpired} />);
    await waitFor(() => expect(onSessionExpired).toHaveBeenCalled());
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
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

  it('says so when a recognized drug has no answer text', async () => {
    api.mockResolvedValue({ detected_drugs: ['aspirin'], results: [] });
    render(<DrugInfoPanel med={{ input: 'aspirin' }} />);
    expect(await screen.findByText('No information found.')).toBeInTheDocument();
  });

  it('shows a lookup failure as an alert', async () => {
    api.mockRejectedValue(new Error('Lookup failed'));
    render(<DrugInfoPanel med={{ input: 'aspirin' }} />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Lookup failed');
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

  it('pluralises the source count and truncates very long citation text', async () => {
    const long = 'x'.repeat(400);
    api.mockResolvedValue({ explanation: 'Fine.', citations: [
      { generic_name: 'aspirin', section: 'drug_interactions', text: long },
      { generic_name: 'warfarin', section: 'warnings', text: 'Short' },
    ] });
    render(<Explanation findingIndex={0} inputs={{ medications: ['a'], allergies: [], notes: '' }} />);
    expect(await screen.findByText('Show 2 sources')).toBeInTheDocument();
    expect(screen.getByText(/drug interactions:/)).toBeInTheDocument();
    expect(screen.getByText(/x{280}…/)).toBeInTheDocument();
    expect(screen.queryByText(/x{281}/)).not.toBeInTheDocument();
  });
});
