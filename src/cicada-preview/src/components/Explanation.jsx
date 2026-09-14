import { useEffect, useState } from 'react';
import { api, mdLite } from '../api.js';

// Ported from runExplain(). Auto-fetches on mount — this reproduces the
// original's "auto-fetch the first 3 visible findings, fetch on-demand
// once revealed by Show more" behavior for free: a FindingCard (and its
// Explanation) simply doesn't mount until it's visible, so "mounted" and
// "should fetch" are the same moment either way.
export default function Explanation({ findingIndex, inputs }) {
  const [state, setState] = useState({ status: 'loading', explanation: '', citations: [] });

  const load = () => {
    setState({ status: 'loading', explanation: '', citations: [] });
    api('/api/explain', {
      method: 'POST',
      body: JSON.stringify({
        medications: inputs.medications,
        allergies: inputs.allergies,
        finding_index: findingIndex,
        patient_notes: inputs.notes,
      }),
    })
      .then((data) => setState({ status: 'ok', explanation: data.explanation, citations: data.citations || [] }))
      .catch((err) => setState({ status: 'error', message: err.message }));
  };

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(load, []);

  if (state.status === 'loading') {
    return (
      <div className="flex items-center gap-2 text-[12.5px]" style={{ color: 'var(--ink-soft)' }}>
        <span className="spinner w-3.5 h-3.5" />Working out what this means for you…
      </div>
    );
  }
  if (state.status === 'error') {
    return (
      <>
        <p className="text-[12.5px] mb-2" style={{ color: 'var(--critical)' }}>
          Couldn't load an explanation: {state.message}
        </p>
        <button
          onClick={load}
          className="text-[12.5px] font-semibold px-3.5 py-1.5 rounded-full border"
          style={{ borderColor: 'var(--line)', color: 'var(--primary)' }}
        >
          Try again →
        </button>
      </>
    );
  }
  return (
    <div className="fade-in pt-2 border-t" style={{ borderColor: 'var(--line-soft)' }}>
      <div
        className="text-[13px] leading-relaxed mt-3"
        style={{ color: 'var(--ink)' }}
        dangerouslySetInnerHTML={{ __html: mdLite(state.explanation) }}
      />
      {state.citations.length > 0 && (
        <details className="mt-2">
          <summary className="text-[11.5px] font-semibold cursor-pointer" style={{ color: 'var(--ink-faint)' }}>
            Show {state.citations.length} source{state.citations.length > 1 ? 's' : ''}
          </summary>
          <div className="mt-2 space-y-2">
            {state.citations.map((c, i) => (
              <div
                key={i}
                className="text-[11.5px] leading-relaxed p-2.5 rounded-lg"
                style={{ background: 'var(--paper)', color: 'var(--ink-soft)' }}
              >
                <span className="font-semibold">
                  {c.generic_name || ''} — {(c.section || '').replace(/_/g, ' ')}:
                </span>{' '}
                {(c.text || '').slice(0, 280)}
                {(c.text || '').length > 280 ? '…' : ''}
              </div>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}
