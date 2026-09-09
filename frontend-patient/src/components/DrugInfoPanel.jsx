import { useEffect, useState } from 'react';
import { api, mdLite } from '../api.js';

// Ported from toggleDrugInfo(). Results owns which drug (if any) is open;
// this just fetches and renders for whichever `med` it's given, re-fetching
// whenever the open drug changes.
export default function DrugInfoPanel({ med }) {
  const [state, setState] = useState({ status: 'loading' });

  useEffect(() => {
    let cancelled = false;
    setState({ status: 'loading' });
    api('/api/query', { method: 'POST', body: JSON.stringify({ prescription: med.input, top_k: 3 }) })
      .then((data) => {
        if (cancelled) return;
        // An empty detected_drugs means the typed name wasn't recognized
        // against our indexed FDA label data — answer_ddi() falls back to
        // an unfiltered search in that case, which can surface text about
        // unrelated drugs. Say so plainly rather than show a summary that
        // looks like it's about this medication when it isn't.
        if (!data.detected_drugs || !data.detected_drugs.length) {
          setState({ status: 'unrecognized' });
          return;
        }
        const first = (data.results || [])[0];
        setState({ status: 'ok', answer: (first && first.answer) || 'No information found.' });
      })
      .catch((err) => !cancelled && setState({ status: 'error', message: err.message }));
    return () => { cancelled = true; };
  }, [med.input]);

  if (state.status === 'loading') {
    return (
      <div className="flex items-center gap-2 text-[12.5px] card rounded-xl p-4" style={{ color: 'var(--ink-soft)' }}>
        <span className="spinner w-3.5 h-3.5" />Looking up {med.input}…
      </div>
    );
  }
  if (state.status === 'error') {
    return <p className="text-[12.5px]" style={{ color: 'var(--critical)' }}>{state.message}</p>;
  }
  if (state.status === 'unrecognized') {
    return (
      <div className="fade-in card rounded-xl p-4" style={{ borderStyle: 'dashed' }}>
        <p className="text-[13px] leading-relaxed" style={{ color: 'var(--ink-soft)' }}>
          We don't have FDA label data indexed for "{med.input}" under that exact name yet. Try the
          generic ingredient name printed on the label.
        </p>
      </div>
    );
  }
  return (
    <div className="fade-in card card-shadow rounded-xl p-4">
      <p className="text-[12px] font-semibold uppercase tracking-wide mb-2" style={{ color: 'var(--ink-faint)' }}>
        FDA label summary — {med.input}
      </p>
      <div
        className="text-[13px] leading-relaxed"
        style={{ color: 'var(--ink)' }}
        dangerouslySetInnerHTML={{ __html: mdLite(state.answer) }}
      />
    </div>
  );
}
