import { useEffect, useState } from 'react';
import { api } from '../api.js';

const PHRASES = [
  'Resolving medication identities…',
  'Cross-referencing known interactions…',
  'Checking allergy conflicts…',
  'Compiling your report…',
];

// Ported from runCheck()'s transitional UI. Performs the actual
// /api/self-check call and hands the result (or error) back to App via
// callbacks — App owns the navigation, this component just owns the
// "in-flight" visual and the phrase cycler.
export default function Scanning({ medications, allergies, onDone, onError }) {
  const [phraseIdx, setPhraseIdx] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => setPhraseIdx((i) => (i + 1) % PHRASES.length), 1100);
    let cancelled = false;

    (async () => {
      try {
        const data = await api('/api/self-check', {
          method: 'POST',
          body: JSON.stringify({ medications, allergies }),
        });
        if (!cancelled) onDone(data);
      } catch (err) {
        if (!cancelled) onError(err.message);
      }
    })();

    return () => {
      cancelled = true;
      clearInterval(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <main className="flex-1 w-full max-w-3xl mx-auto px-6 py-10">
      <div className="reveal max-w-lg mx-auto text-center py-16">
        <div className="scan-track card card-shadow rounded-2xl p-10 mb-6">
          <div className="scan-bar" />
          <p className="font-display text-[22px] mb-2" style={{ color: 'var(--primary)' }}>Reading the evidence</p>
          <p className="text-[13px]" style={{ color: 'var(--ink-soft)' }}>{PHRASES[phraseIdx]}</p>
        </div>
        <p className="text-[12px]" style={{ color: 'var(--ink-faint)' }}>
          This runs the same deterministic rule engine your pharmacist's console uses.
        </p>
      </div>
    </main>
  );
}
