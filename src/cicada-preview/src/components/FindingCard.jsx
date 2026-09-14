import Explanation from './Explanation.jsx';
import { SEVERITY_META, findingTitle } from '../meta.js';

// Ported from findingCard().
export default function FindingCard({ finding: f, inputs }) {
  const meta = SEVERITY_META[f.severity] || SEVERITY_META.unknown;
  // reported_severity "unknown" here means the source dataset itself has no
  // severity rating for this pairing — a different thing from our own
  // governance status (which is also, confusingly, called "unknown"). Only
  // show the hint when there's an actual rating to report.
  const hasRealReportedSeverity = f.reported_severity && f.reported_severity !== 'unknown';
  const reportedMeta = hasRealReportedSeverity ? SEVERITY_META[f.reported_severity] : null;

  return (
    <div className="card card-shadow rounded-2xl p-5" style={{ borderLeft: `3px solid ${meta.color}` }}>
      <div className="flex items-start justify-between gap-3 mb-2">
        <p className="text-[14px] font-semibold leading-snug">{findingTitle(f)}</p>
        <span
          className="inline-flex items-center gap-1.5 text-[10.5px] font-bold uppercase tracking-wide px-2.5 py-1 rounded-full whitespace-nowrap"
          style={{ background: meta.bg, color: meta.color }}
        >
          {meta.label}
        </span>
      </div>

      {f.type === 'unknown' && reportedMeta && (
        <p className="text-[11.5px] font-semibold mb-3" style={{ color: reportedMeta.color }}>
          Our data suggests: {reportedMeta.label} (not yet confirmed by a pharmacist)
        </p>
      )}
      {f.type === 'unknown' && !reportedMeta && (
        <p className="text-[11.5px] mb-3" style={{ color: 'var(--ink-faint)' }}>
          No severity rating available in our data for this pairing.
        </p>
      )}

      <p className="text-[13px] leading-relaxed mb-3" style={{ color: 'var(--ink-soft)' }}>
        {f.clinical_effect || ''}
      </p>

      {f.see_a_doctor && (
        <div
          className="flex items-center gap-2 text-[12.5px] font-bold px-3 py-2 rounded-lg mb-3"
          style={{ background: 'rgba(255,92,92,0.14)', color: 'var(--critical)' }}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" style={{ flexShrink: 0 }}>
            <path d="M12 3.5 L22 20.5 L2 20.5 Z" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
            <path d="M12 9.5 V14.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            <circle cx="12" cy="17.3" r="1.1" fill="currentColor" />
          </svg>
          See a doctor or pharmacist before taking these together
        </div>
      )}

      <p className="text-[12px] mb-3" style={{ color: 'var(--ink-faint)' }}>
        {f.patient_guidance || f.recommended_action || ''}
      </p>

      <Explanation findingIndex={f.index} inputs={inputs} />
    </div>
  );
}
