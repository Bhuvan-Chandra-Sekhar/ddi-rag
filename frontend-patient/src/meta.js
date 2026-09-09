// Ported verbatim from static/patient/index.html.

export const SEVERITY_META = {
  critical: { label: 'Critical', color: 'var(--critical)', bg: 'rgba(255,92,92,0.14)' },
  major: { label: 'Major', color: 'var(--major)', bg: 'rgba(255,138,61,0.14)' },
  caution: { label: 'Caution', color: 'var(--caution)', bg: 'rgba(255,184,41,0.14)' },
  informational: { label: 'Informational', color: 'var(--informational)', bg: 'rgba(111,200,255,0.14)' },
  unknown: { label: 'Not yet clinically reviewed', color: 'var(--unknown)', bg: 'rgba(184,146,255,0.14)' },
};

const SEVERITY_RANK = { critical: 4, major: 3, unknown: 2, caution: 1, informational: 0 };
// How urgently a finding deserves attention — takes the higher of its
// confirmed severity and its (unreviewed) reported_severity, so a
// well-documented-but-unapproved MAJOR interaction still sorts and reads
// as important instead of blending in with a truly informational one.
export const findingUrgency = (f) => Math.max(SEVERITY_RANK[f.severity] ?? 0, SEVERITY_RANK[f.reported_severity] ?? 0);

export function findingTitle(f) {
  const factors = f.patient_factors || {};
  if (f.type === 'allergy') return `Matches a known allergy — ${factors.ingredient || ''}`;
  if (f.type === 'duplicate') return `Duplicate ingredient — ${factors.ingredient || ''} appears ${factors.occurrence_count || 2}×`;
  if (f.type === 'ddi') return `Interaction: ${factors.ingredient_a || '?'} + ${factors.ingredient_b || '?'}`;
  if (f.type === 'unknown') return `Unreviewed pairing: ${factors.ingredient_a || '?'} + ${factors.ingredient_b || '?'}`;
  return 'Finding';
}

// bg/fg/dot are inline-style values (rgba tints + CSS vars) — on a black
// void canvas they render as tinted pills rather than light rectangles.
export const STATE_META = {
  draft: { label: 'Getting started', bg: 'rgba(154,154,154,0.14)', fg: 'var(--ink-soft)', dot: 'var(--ink-soft)' },
  awaiting_analysis: { label: 'Reviewing your prescription', bg: 'rgba(154,154,154,0.14)', fg: 'var(--ink-soft)', dot: 'var(--ink-soft)' },
  awaiting_pharmacist_review: { label: 'Your pharmacist is reviewing this', bg: 'rgba(111,200,255,0.14)', fg: 'var(--informational)', dot: 'var(--informational)' },
  awaiting_prescriber_response: { label: 'Checking with your prescriber', bg: 'rgba(255,184,41,0.14)', fg: 'var(--caution)', dot: 'var(--caution)' },
  escalated: { label: 'Under urgent review', bg: 'rgba(255,92,92,0.14)', fg: 'var(--critical)', dot: 'var(--critical)' },
  ready_to_dispense: { label: 'Reviewed and ready', bg: 'rgba(62,207,142,0.14)', fg: 'var(--safe)', dot: 'var(--safe)' },
  held_or_cancelled: { label: 'On hold — contact your pharmacy', bg: 'rgba(255,92,92,0.14)', fg: 'var(--critical)', dot: 'var(--critical)' },
  closed: { label: 'Complete', bg: 'rgba(62,207,142,0.14)', fg: 'var(--safe)', dot: 'var(--safe)' },
};

export const MAX_MEDS_TOTAL = 8;
export const DEFAULT_VISIBLE_FINDINGS = 3;
