import { useRef, useState } from 'react';
import CheckingField from '../components/CheckingField.jsx';
import TagInput from '../components/TagInput.jsx';
import { MAX_MEDS_TOTAL } from '../meta.js';

// Ported from renderChecker(). `draft` is lifted to App (like the
// original's module-level _draft) since Results' "check another"/"start
// over" actions need to mutate the same state this screen reads.
export default function Checker({ draft, setDraft, onSubmit }) {
  const [error, setError] = useState('');
  const checkingRef = useRef(null);
  const currentRef = useRef(null);
  const allergyRef = useRef(null);

  const totalMedsCanAdd = () => (draft.checking ? 1 : 0) + draft.current.length < MAX_MEDS_TOTAL;

  const handleSubmit = (e) => {
    e.preventDefault();
    // Commit any text still sitting in an input the user didn't press
    // Enter/Add on — same intent as the original's leftover-DOM-value read.
    checkingRef.current?.flush();
    currentRef.current?.flush();
    allergyRef.current?.flush();

    if (!draft.checking && !draft.current.length) {
      setError('Add at least one drug to check.');
      return;
    }
    setError('');
    onSubmit();
  };

  return (
    <main className="flex-1 w-full max-w-3xl mx-auto px-6 py-10">
      <div className="reveal">
        <p className="label-tag mb-4" style={{ color: 'var(--accent)' }}>Quick check · no account needed</p>
        <h1 className="font-display text-heading-sm mb-4" style={{ color: 'var(--ink)' }}>What are you checking?</h1>
        <p className="text-prose mb-10" style={{ color: 'var(--ink-soft)', maxWidth: '34rem' }}>
          Tell us the drug or prescription you want checked, and what else you're already
          taking. Nothing here is sent to a care team or saved to an account — it stays in
          this browser tab, and disappears when you leave.
        </p>

        <form onSubmit={handleSubmit} className="card card-shadow rounded-2xl p-6 sm:p-8 space-y-7">
          <CheckingField
            ref={checkingRef}
            value={draft.checking}
            onChange={(v) => setDraft((d) => ({ ...d, checking: v }))}
          />
          <TagInput
            ref={currentRef}
            label="What else are you currently taking? — your history"
            placeholder="e.g. warfarin"
            items={draft.current}
            canAdd={totalMedsCanAdd}
            onChange={(items) => setDraft((d) => ({ ...d, current: items }))}
          />
          <TagInput
            ref={allergyRef}
            label="Any known allergies or past bad reactions?"
            placeholder="e.g. penicillin"
            items={draft.allergies}
            canAdd={() => draft.allergies.length < MAX_MEDS_TOTAL}
            onChange={(items) => setDraft((d) => ({ ...d, allergies: items }))}
          />
          <div>
            <label className="label-tag block mb-2" style={{ color: 'var(--ink)' }}>
              Anything else about your history you'd like to mention?{' '}
              <span className="normal-case" style={{ color: 'var(--ink-faint)', fontWeight: 400, letterSpacing: 'normal' }}>
                (optional)
              </span>
            </label>
            <textarea
              rows={3}
              maxLength={600}
              placeholder="Past reactions, other conditions, how you're feeling — anything that might matter here. This isn't saved anywhere; it's just used to help explain your results."
              value={draft.notes}
              onChange={(e) => setDraft((d) => ({ ...d, notes: e.target.value }))}
              className="field w-full border rounded-lg px-3.5 py-2.5 text-[13.5px]"
              style={{ borderColor: 'var(--line)' }}
            />
          </div>

          {error && (
            <div className="text-[13px] font-medium" style={{ color: 'var(--critical)' }}>{error}</div>
          )}

          <div className="flex items-center justify-between pt-1">
            <p className="text-[11.5px] max-w-xs leading-relaxed" style={{ color: 'var(--ink-faint)' }}>
              Not reviewed by a pharmacist. Not a substitute for professional medical advice.
            </p>
            <button type="submit" className="label-tag text-white px-6 py-3.5 rounded-full whitespace-nowrap" style={{ background: 'var(--primary)' }}>
              Check now →
            </button>
          </div>
        </form>
      </div>
    </main>
  );
}
