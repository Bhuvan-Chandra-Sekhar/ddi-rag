import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import FindingCard from '../components/FindingCard.jsx';
import { api } from '../api.js';

vi.mock('../api.js', async (original) => ({ ...(await original()), api: vi.fn() }));

const inputs = { medications: ['aspirin', 'warfarin'], allergies: [], notes: '' };
const card = (finding) => render(<FindingCard finding={{ index: 0, clinical_effect: 'Some effect.', ...finding }} inputs={inputs} />);

beforeEach(() => {
  api.mockResolvedValue({ explanation: 'Explained.', citations: [] });
});

// The wording on an unreviewed finding is the safety-critical part: it
// must never read as a confirmed result.
describe('unreviewed (type "unknown") findings', () => {
  const unreviewed = { type: 'unknown', severity: 'unknown', patient_factors: { ingredient_a: 'a', ingredient_b: 'b' } };

  it('labels the finding as not yet clinically reviewed', () => {
    card(unreviewed);
    expect(screen.getByText('Not yet clinically reviewed')).toBeInTheDocument();
    expect(screen.getByText('Unreviewed pairing: a + b')).toBeInTheDocument();
  });

  it('shows the dataset\'s rating, clearly marked as unconfirmed', () => {
    card({ ...unreviewed, reported_severity: 'major' });
    expect(screen.getByText(/our data suggests: major \(not yet confirmed by a pharmacist\)/i)).toBeInTheDocument();
  });

  it('says there is no rating when the dataset has none', () => {
    card(unreviewed);
    expect(screen.getByText(/no severity rating available in our data for this pairing/i)).toBeInTheDocument();
  });

  it('treats a reported severity of "unknown" as no rating at all', () => {
    card({ ...unreviewed, reported_severity: 'unknown' });
    expect(screen.getByText(/no severity rating available/i)).toBeInTheDocument();
    expect(screen.queryByText(/our data suggests/i)).not.toBeInTheDocument();
  });
});

describe('confirmed findings', () => {
  it('shows the severity badge and the clinical effect without the unreviewed hints', () => {
    card({ type: 'ddi', severity: 'major', patient_factors: { ingredient_a: 'aspirin', ingredient_b: 'warfarin' } });
    expect(screen.getByText('Major')).toBeInTheDocument();
    expect(screen.getByText('Some effect.')).toBeInTheDocument();
    expect(screen.queryByText(/our data suggests/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/no severity rating/i)).not.toBeInTheDocument();
  });

  it('falls back to the "not yet reviewed" label for a severity it does not recognise', () => {
    card({ type: 'ddi', severity: 'catastrophic' });
    expect(screen.getByText('Not yet clinically reviewed')).toBeInTheDocument();
  });

  it('shows the see-a-doctor strip only when the finding asks for it', () => {
    const { unmount } = card({ type: 'ddi', severity: 'critical', see_a_doctor: true });
    expect(screen.getByText(/see a doctor or pharmacist before taking these together/i)).toBeInTheDocument();
    unmount();
    card({ type: 'ddi', severity: 'caution', see_a_doctor: false });
    expect(screen.queryByText(/see a doctor or pharmacist/i)).not.toBeInTheDocument();
  });

  it('prefers patient guidance, then the recommended action, then nothing', () => {
    const first = card({ type: 'ddi', severity: 'caution', patient_guidance: 'Patient words', recommended_action: 'Clinical words' });
    expect(screen.getByText('Patient words')).toBeInTheDocument();
    expect(screen.queryByText('Clinical words')).not.toBeInTheDocument();
    first.unmount();
    const second = card({ type: 'ddi', severity: 'caution', recommended_action: 'Clinical words' });
    expect(screen.getByText('Clinical words')).toBeInTheDocument();
    second.unmount();
    card({ type: 'ddi', severity: 'caution' });
    expect(screen.queryByText(/words/)).not.toBeInTheDocument();
  });

  it('asks for the explanation of its own finding index', async () => {
    card({ index: 7, type: 'ddi', severity: 'caution' });
    expect(await screen.findByText('Explained.')).toBeInTheDocument();
    expect(JSON.parse(api.mock.calls[0][1].body)).toMatchObject({ finding_index: 7, medications: ['aspirin', 'warfarin'] });
  });
});
