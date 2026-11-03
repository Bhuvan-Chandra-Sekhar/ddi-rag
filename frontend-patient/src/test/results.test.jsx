import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Results from '../screens/Results.jsx';

vi.mock('../components/Explanation.jsx', () => ({ default: () => <div>Explanation loaded</div> }));
vi.mock('../components/DrugInfoPanel.jsx', () => ({ default: ({ med }) => <div>Info for {med.input}</div> }));

const draft = { checking: 'aspirin', current: ['warfarin'], allergies: [], notes: '' };
const base = {
  resolved_medications: [{ input: 'aspirin', identity_confirmed: true }, { input: 'warfarin', identity_confirmed: true }],
  findings: [],
  summary: {},
};

describe('results safety communication', () => {
  it('does not describe an empty result as safe', () => {
    render(<Results data={base} checkingCount={1} draft={draft} onNewCheck={vi.fn()} onCheckAnother={vi.fn()} />);
    expect(screen.getByText('Nothing flagged in our data')).toBeInTheDocument();
    expect(screen.getByText(/does not establish that the combination is safe/i)).toBeInTheDocument();
  });

  it('warns instead of reassuring when a medication was only approximately matched', () => {
    const data = { ...base, resolved_medications: [{ input: 'mystery', identity_confirmed: false }] };
    render(<Results data={data} checkingCount={1} draft={draft} onNewCheck={vi.fn()} onCheckAnother={vi.fn()} />);
    expect(screen.getByText(/not sure we understood everything/i)).toBeInTheDocument();
    expect(screen.queryByText('Nothing flagged in our data')).not.toBeInTheDocument();
  });

  it('shows urgent guidance when a finding requires a doctor', () => {
    const data = { ...base, overall_severity: 'critical', see_a_doctor: true, findings: [{ index: 0, type: 'ddi', severity: 'critical', see_a_doctor: true, clinical_effect: 'Risk', patient_guidance: 'Call care team' }] };
    render(<Results data={data} checkingCount={1} draft={draft} onNewCheck={vi.fn()} onCheckAnother={vi.fn()} />);
    expect(screen.getByText(/please talk to a doctor or pharmacist/i)).toBeInTheDocument();
    expect(screen.getByText(/see a doctor or pharmacist before taking/i)).toBeInTheDocument();
  });

  it('reveals additional findings and supports both restart actions', async () => {
    const user = userEvent.setup();
    const findings = Array.from({ length: 5 }, (_, index) => ({ index, type: 'ddi', severity: 'caution', clinical_effect: `Effect ${index}`, patient_guidance: 'Review' }));
    const onNewCheck = vi.fn();
    const onCheckAnother = vi.fn();
    render(<Results data={{ ...base, findings }} checkingCount={1} draft={draft} onNewCheck={onNewCheck} onCheckAnother={onCheckAnother} />);
    expect(screen.queryByText('Effect 4')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /show 2 more findings/i }));
    expect(screen.getByText('Effect 4')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /check a different drug/i }));
    await user.click(screen.getByRole('button', { name: /start a new check/i }));
    expect(onCheckAnother).toHaveBeenCalledOnce();
    expect(onNewCheck).toHaveBeenCalledOnce();
  });
});
