import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Results from '../screens/Results.jsx';
import { api } from '../api.js';

// Only the network edge is faked. Explanation, DrugInfoPanel and
// FindingCard are the real components, so what Results passes them is
// what actually reaches the request.
vi.mock('../api.js', async (original) => ({ ...(await original()), api: vi.fn() }));

const draft = { checking: 'aspirin', current: ['warfarin'], allergies: [], notes: '' };
const base = {
  resolved_medications: [{ input: 'aspirin', identity_confirmed: true }, { input: 'warfarin', identity_confirmed: true }],
  findings: [],
  summary: {},
};
const renderResults = (data, { draftOverride = draft, checkingCount = 1, onNewCheck = vi.fn(), onCheckAnother = vi.fn() } = {}) =>
  render(<Results data={data} checkingCount={checkingCount} draft={draftOverride} onNewCheck={onNewCheck} onCheckAnother={onCheckAnother} />);

const finding = (index, overrides = {}) => ({
  index, type: 'ddi', severity: 'caution', clinical_effect: `Effect ${index}`, patient_guidance: 'Review',
  patient_factors: { ingredient_a: 'a', ingredient_b: 'b' }, ...overrides,
});
const calls = (path) => api.mock.calls.filter(([p]) => p === path);
const explainBodies = () => calls('/api/explain').map(([, opts]) => JSON.parse(opts.body));

beforeEach(() => {
  api.mockImplementation(async (path, opts) => {
    if (path === '/api/explain') {
      return { explanation: `Explained finding ${JSON.parse(opts.body).finding_index}`, citations: [] };
    }
    if (path === '/api/query') {
      const { prescription } = JSON.parse(opts.body);
      return { detected_drugs: [prescription], results: [{ answer: `Label text for ${prescription}` }] };
    }
    throw new Error(`unexpected request to ${path}`);
  });
});

describe('results safety communication', () => {
  it('does not describe an empty result as safe', () => {
    renderResults(base);
    expect(screen.getByText('Nothing flagged in our data')).toBeInTheDocument();
    expect(screen.getByText(/does not establish that the combination is safe/i)).toBeInTheDocument();
    expect(screen.getByText('No findings to show.')).toBeInTheDocument();
  });

  it('warns instead of reassuring when a medication was only approximately matched', () => {
    renderResults({ ...base, resolved_medications: [{ input: 'mystery', identity_confirmed: false }] });
    expect(screen.getByText(/not sure we understood everything/i)).toBeInTheDocument();
    expect(screen.queryByText('Nothing flagged in our data')).not.toBeInTheDocument();
    // "·approx" also appears inside the warning's own text, so scope to the chip.
    const chip = screen.getByRole('button', { name: /mystery/ });
    expect(within(chip).getByText('·approx')).toBeInTheDocument();
  });

  it('shows urgent guidance when a finding requires a doctor', () => {
    const data = { ...base, overall_severity: 'critical', see_a_doctor: true, findings: [finding(0, { severity: 'critical', see_a_doctor: true })] };
    renderResults(data);
    expect(screen.getByText(/please talk to a doctor or pharmacist/i)).toBeInTheDocument();
    expect(screen.getByText(/see a doctor or pharmacist before taking/i)).toBeInTheDocument();
  });

  it.each([
    ['critical', 'Critical'], ['major', 'Major'], ['caution', 'Caution'],
    ['informational', 'Informational'], ['unknown', 'Not yet clinically reviewed'],
  ])('names the highest priority %s finding in the banner', (severity, label) => {
    renderResults({ ...base, overall_severity: severity, findings: [finding(0, { severity })] });
    const banner = screen.getByText(/highest priority/i);
    expect(banner).toHaveTextContent(label);
    expect(screen.queryByText('Nothing flagged in our data')).not.toBeInTheDocument();
  });

  it('never claims safety for any overall severity', () => {
    renderResults({ ...base, overall_severity: 'informational', findings: [finding(0, { severity: 'informational' })] });
    expect(document.body.textContent).not.toMatch(/\bis safe\b|\bare safe\b|safe to take/i);
  });

  it('reveals additional findings and supports both restart actions', async () => {
    const user = userEvent.setup();
    const findings = Array.from({ length: 5 }, (_, index) => finding(index));
    const onNewCheck = vi.fn();
    const onCheckAnother = vi.fn();
    renderResults({ ...base, findings }, { onNewCheck, onCheckAnother });
    expect(screen.queryByText('Effect 4')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /show 2 more findings/i }));
    expect(screen.getByText('Effect 4')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /show .* more finding/i })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /check a different drug/i }));
    await user.click(screen.getByRole('button', { name: /start a new check/i }));
    expect(onCheckAnother).toHaveBeenCalledOnce();
    expect(onNewCheck).toHaveBeenCalledOnce();
  });

  it('says "1 more finding" in the singular', () => {
    renderResults({ ...base, findings: Array.from({ length: 4 }, (_, i) => finding(i)) });
    expect(screen.getByRole('button', { name: /show 1 more finding →/i })).toBeInTheDocument();
  });
});

describe('data coverage section', () => {
  const coverage = {
    pairs_checked: 3, pairs_approved: 1, pairs_with_no_rule: 2, pairs_unreviewed: 1, pairs_rejected: 1,
    unmatched_pairs: [{ ingredient_a: 'aspirin', ingredient_b: 'ibuprofen' }],
  };

  it('shows the counts, the gap warning, and the unmatched pairs', () => {
    renderResults({ ...base, ddi_coverage: coverage });
    expect(screen.getByText('Ingredient pairs').previousSibling).toHaveTextContent('3');
    expect(screen.getByText('Approved rules').previousSibling).toHaveTextContent('1');
    expect(screen.getByText('Without a rule').previousSibling).toHaveTextContent('2');
    expect(screen.getByText(/a missing rule means a gap in our data, not a safe combination/i)).toBeInTheDocument();
    expect(screen.getByText(/1 pair\(s\) have rules awaiting review/i)).toBeInTheDocument();
    expect(screen.getByText(/1 pair\(s\) have rejected rules/i)).toBeInTheDocument();
    expect(screen.getByText('aspirin + ibuprofen')).toBeInTheDocument();
  });

  it('explains when there were no pairs to compare', () => {
    renderResults({ ...base, ddi_coverage: { ...coverage, pairs_checked: 0, unmatched_pairs: [], pairs_unreviewed: 0, pairs_rejected: 0 } });
    expect(screen.getByText(/no distinct ingredient pairs to compare/i)).toBeInTheDocument();
  });

  it('does not treat missing coverage as confirmation of safety', () => {
    renderResults(base);
    expect(screen.getByText(/coverage information is unavailable/i)).toBeInTheDocument();
    expect(screen.getByText(/should not be interpreted as confirmation of safety/i)).toBeInTheDocument();
  });
});

describe('how Results wires the explanation requests', () => {
  it('sends the medications, allergies, notes and the finding index it was given', async () => {
    const withNotes = { checking: 'aspirin', current: ['warfarin'], allergies: ['penicillin'], notes: 'Previous rash' };
    renderResults({ ...base, findings: [finding(4)] }, { draftOverride: withNotes });
    await screen.findByText('Explained finding 4');
    expect(explainBodies()).toEqual([{
      medications: ['aspirin', 'warfarin'],
      allergies: ['penicillin'],
      finding_index: 4,
      patient_notes: 'Previous rash',
    }]);
  });

  it('uses the finding index, not its display position, and fetches the most urgent first', async () => {
    const findings = [
      finding(0, { severity: 'informational' }),
      finding(1, { severity: 'critical' }),
      finding(2, { severity: 'major' }),
    ];
    renderResults({ ...base, findings });
    await waitFor(() => expect(explainBodies()).toHaveLength(3));
    expect(explainBodies().map((b) => b.finding_index)).toEqual([1, 2, 0]);
  });

  it('puts a finding with a high reported severity ahead of a plain informational one', async () => {
    const findings = [
      finding(0, { severity: 'informational' }),
      finding(1, { severity: 'unknown', type: 'unknown', reported_severity: 'major' }),
    ];
    renderResults({ ...base, findings });
    await waitFor(() => expect(explainBodies()).toHaveLength(2));
    expect(explainBodies().map((b) => b.finding_index)).toEqual([1, 0]);
  });

  it('requests explanations only for the findings that are visible', async () => {
    renderResults({ ...base, findings: Array.from({ length: 5 }, (_, i) => finding(i)) });
    await waitFor(() => expect(explainBodies()).toHaveLength(3));
    expect(explainBodies().map((b) => b.finding_index).sort()).toEqual([0, 1, 2]);
  });

  it('requests only the newly revealed findings after "Show more", never repeating the first three', async () => {
    const user = userEvent.setup();
    renderResults({ ...base, findings: Array.from({ length: 5 }, (_, i) => finding(i)) });
    await waitFor(() => expect(explainBodies()).toHaveLength(3));
    await user.click(screen.getByRole('button', { name: /show 2 more findings/i }));
    await waitFor(() => expect(explainBodies()).toHaveLength(5));
    expect(explainBodies().map((b) => b.finding_index).sort()).toEqual([0, 1, 2, 3, 4]);
  });
});

describe('how Results wires the drug label lookup', () => {
  const chip = (name) => screen.getByRole('button', { name: new RegExp(`^${name}`) });

  it('looks up the medication whose chip was opened, then closes on a second click', async () => {
    const user = userEvent.setup();
    renderResults(base);
    expect(calls('/api/query')).toHaveLength(0);
    await user.click(chip('aspirin'));
    expect(await screen.findByText('Label text for aspirin')).toBeInTheDocument();
    expect(JSON.parse(calls('/api/query')[0][1].body)).toEqual({ prescription: 'aspirin', top_k: 3 });
    await user.click(chip('aspirin'));
    expect(screen.queryByText('Label text for aspirin')).not.toBeInTheDocument();
  });

  it('switches to another medication when its chip is opened, using that chip\'s own name', async () => {
    const user = userEvent.setup();
    renderResults(base);
    await user.click(chip('aspirin'));
    await screen.findByText('Label text for aspirin');
    await user.click(chip('warfarin'));
    expect(await screen.findByText('Label text for warfarin')).toBeInTheDocument();
    expect(screen.queryByText('Label text for aspirin')).not.toBeInTheDocument();
    expect(calls('/api/query').map(([, o]) => JSON.parse(o.body).prescription)).toEqual(['aspirin', 'warfarin']);
  });

  it('groups chips by whether they are being checked or already taken', () => {
    renderResults(base);
    const checking = screen.getByText("You're checking").parentElement;
    const taking = screen.getByText("Against what you're already taking").parentElement;
    expect(within(checking).getByRole('button', { name: /^aspirin/ })).toBeInTheDocument();
    expect(within(taking).getByRole('button', { name: /^warfarin/ })).toBeInTheDocument();
  });

  it('shows only the "already taking" group when nothing is being checked', () => {
    renderResults(base, { checkingCount: 0 });
    expect(screen.queryByText("You're checking")).not.toBeInTheDocument();
    expect(screen.getByText("Against what you're already taking")).toBeInTheDocument();
  });
});
