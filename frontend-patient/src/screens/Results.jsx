import { useMemo, useState } from 'react';
import DrugInfoPanel from '../components/DrugInfoPanel.jsx';
import FindingCard from '../components/FindingCard.jsx';
import { DEFAULT_VISIBLE_FINDINGS, SEVERITY_META, findingUrgency } from '../meta.js';

function OverallBanner({ overallSeverity, seeADoctor, hasUnresolvedMed }) {
  if (seeADoctor) {
    return (
      <Banner color="var(--critical)" bg="rgba(255,92,92,0.16)" tint="rgba(255,92,92,0.08)">
        <p className="font-display text-[19px] font-semibold mb-1" style={{ color: 'var(--critical)' }}>
          Please talk to a doctor or pharmacist before taking these together
        </p>
        <p className="text-[13px] leading-relaxed" style={{ color: 'var(--ink-soft)' }}>
          Something below looks serious enough to check first — see which finding triggered this and
          why in the details below.
        </p>
      </Banner>
    );
  }
  // Never show the reassuring "nothing flagged" message when we're not
  // confident we understood every name typed in — a patient typing two
  // drugs into one field can end up with one name silently dropped during
  // matching, and a green checkmark in that case is a false, dangerous
  // reassurance, not an honest "no findings".
  if (!overallSeverity && hasUnresolvedMed) {
    return (
      <Banner color="var(--caution)" bg="rgba(255,184,41,0.16)">
        <p className="font-display text-[19px] font-semibold mb-1">We're not sure we understood everything you entered</p>
        <p className="text-[13px] leading-relaxed" style={{ color: 'var(--ink-soft)' }}>
          One or more items below (marked <strong>·approx</strong>) didn't match a known medication
          exactly — if you typed more than one drug into the same box, try adding them as separate
          entries instead. No findings below isn't a clean bill of health until every item is confirmed.
        </p>
      </Banner>
    );
  }
  if (!overallSeverity) {
    return (
      <Banner color="var(--safe)" bg="rgba(62,207,142,0.16)" icon="check">
        <p className="font-display text-[19px] font-semibold mb-1">Nothing flagged in our data</p>
        <p className="text-[13px] leading-relaxed" style={{ color: 'var(--ink-soft)' }}>
          No duplicate ingredients, recorded allergy conflicts, or known interaction rules matched what
          you entered. That's reassuring, but it isn't a guarantee — it only reflects what's in this
          dataset, and no pharmacist has reviewed it.
        </p>
      </Banner>
    );
  }
  const meta = SEVERITY_META[overallSeverity] || SEVERITY_META.unknown;
  return (
    <Banner color={meta.color} bg={meta.bg}>
      <p className="font-display text-[19px] font-semibold mb-1">
        We found something to review — highest priority: <span style={{ color: meta.color }}>{meta.label}</span>
      </p>
      <p className="text-[13px] leading-relaxed" style={{ color: 'var(--ink-soft)' }}>
        See the findings below. None of this has been confirmed by a pharmacist — treat anything above
        "Informational" as worth a real conversation with one, especially "Critical" or "Major".
      </p>
    </Banner>
  );
}

function Banner({ color, bg, tint, icon = 'warning', children }) {
  return (
    <div
      className="card card-shadow rounded-2xl p-6 flex items-start gap-4"
      style={{ borderLeft: `4px solid ${color}`, background: tint }}
    >
      <div className="w-9 h-9 rounded-full flex items-center justify-center flex-shrink-0" style={{ background: bg }}>
        {icon === 'check' ? (
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
            <path d="M5 12.5 L9.5 17 L19 7" stroke={color} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        ) : (
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
            <path d="M12 3.5 L22 20.5 L2 20.5 Z" stroke={color} strokeWidth="2" strokeLinejoin="round" />
            <path d="M12 9.5 V14.5" stroke={color} strokeWidth="2" strokeLinecap="round" />
            <circle cx="12" cy="17.3" r="1.1" fill={color} />
          </svg>
        )}
      </div>
      <div>{children}</div>
    </div>
  );
}

function MedChips({ meds, offset, onToggle }) {
  return (
    <div className="flex flex-wrap gap-2">
      {meds.map((m, i) => (
        <button
          key={offset + i}
          onClick={() => onToggle(offset + i)}
          className="chip inline-flex items-center gap-1.5 text-[12.5px] font-medium pl-3 pr-3 py-1.5 rounded-full"
        >
          {m.input}
          {!m.identity_confirmed && (
            <span title="Matched approximately — for best results use the name printed on the label" style={{ color: 'var(--accent)' }}>
              ·approx
            </span>
          )}
        </button>
      ))}
    </div>
  );
}

// Ported from renderResults().
export default function Results({ data, checkingCount, draft, onNewCheck, onCheckAnother }) {
  const { resolved_medications: resolvedMedications = [], findings: rawFindings = [], overall_severity, see_a_doctor } = data;
  const checkingMeds = resolvedMedications.slice(0, checkingCount);
  const currentMeds = resolvedMedications.slice(checkingCount);
  const hasUnresolvedMed = resolvedMedications.some((m) => !m.identity_confirmed);

  const inputs = useMemo(
    () => ({
      medications: [...(draft.checking ? [draft.checking] : []), ...draft.current],
      allergies: [...draft.allergies],
      notes: draft.notes,
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    []
  );

  // Most urgent first — the explanations then auto-fetch in this order
  // too, so the thing most worth reading loads first.
  const findings = useMemo(() => [...rawFindings].sort((a, b) => findingUrgency(b) - findingUrgency(a)), [rawFindings]);
  const [visibleCount, setVisibleCount] = useState(DEFAULT_VISIBLE_FINDINGS);
  const [openDrugIndex, setOpenDrugIndex] = useState(null);

  const visible = findings.slice(0, visibleCount);
  const remaining = findings.length - visibleCount;

  return (
    <main className="flex-1 w-full max-w-3xl mx-auto px-6 py-10">
      <div className="reveal space-y-6">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <p className="label-tag" style={{ color: 'var(--accent)' }}>Your results</p>
          <div className="flex items-center gap-4">
            <button
              onClick={onCheckAnother}
              className="text-[12.5px] font-semibold px-3.5 py-1.5 rounded-full border"
              style={{ borderColor: 'var(--primary)', color: 'var(--primary)' }}
            >
              Check a different drug →
            </button>
            <button onClick={onNewCheck} className="text-[12.5px] font-semibold underline underline-link" style={{ color: 'var(--ink-soft)' }}>
              Start a new check
            </button>
          </div>
        </div>

        <OverallBanner overallSeverity={overall_severity} seeADoctor={see_a_doctor} hasUnresolvedMed={hasUnresolvedMed} />

        {checkingMeds.length > 0 && (
          <div>
            <p className="text-[12px] font-semibold uppercase tracking-wide mb-2.5" style={{ color: 'var(--ink-faint)' }}>You're checking</p>
            <MedChips meds={checkingMeds} offset={0} onToggle={(i) => setOpenDrugIndex((cur) => (cur === i ? null : i))} />
          </div>
        )}

        {currentMeds.length > 0 && (
          <div>
            <p className="text-[12px] font-semibold uppercase tracking-wide mb-2.5" style={{ color: 'var(--ink-faint)' }}>Against what you're already taking</p>
            <MedChips meds={currentMeds} offset={checkingCount} onToggle={(i) => setOpenDrugIndex((cur) => (cur === i ? null : i))} />
          </div>
        )}

        {openDrugIndex !== null && resolvedMedications[openDrugIndex] && (
          <DrugInfoPanel med={resolvedMedications[openDrugIndex]} />
        )}

        <div>
          <p className="text-[12px] font-semibold uppercase tracking-wide mb-2.5" style={{ color: 'var(--ink-faint)' }}>
            Findings {findings.length ? `(${findings.length})` : ''}
          </p>
          <div className="space-y-3">
            {findings.length ? (
              visible.map((f) => <FindingCard key={f.index} finding={f} inputs={inputs} />)
            ) : (
              <div className="card rounded-2xl p-6 text-center" style={{ borderStyle: 'dashed' }}>
                <p className="text-[13px]" style={{ color: 'var(--ink-soft)' }}>No findings to show.</p>
              </div>
            )}
          </div>
          {remaining > 0 && (
            <button
              onClick={() => setVisibleCount((c) => c + remaining)}
              className="w-full mt-3 text-[13px] font-semibold py-2.5 rounded-xl border"
              style={{ borderColor: 'var(--line)', color: 'var(--primary)', background: 'var(--paper-raised)' }}
            >
              Show {remaining} more finding{remaining > 1 ? 's' : ''} →
            </button>
          )}
        </div>
      </div>
    </main>
  );
}
