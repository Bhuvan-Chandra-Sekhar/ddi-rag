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
    const nextDraft = {
      ...draft,
      checking: checkingRef.current?.flush() ?? draft.checking,
      current: currentRef.current?.flush() ?? draft.current,
      allergies: allergyRef.current?.flush() ?? draft.allergies,
    };
    setDraft(nextDraft);

    if ((nextDraft.checking ? 1 : 0) + nextDraft.current.length > MAX_MEDS_TOTAL) {
      setError(`Check up to ${MAX_MEDS_TOTAL} medications at a time. Remove one to continue.`);
      return;
    }
    if (!nextDraft.checking && !nextDraft.current.length) {
      setError('Add at least one drug to check.');
      return;
    }
    setError('');
    onSubmit();
  };

  return (
    <main className="flex-1 w-full max-w-3xl mx-auto px-6 py-16 sm:py-24">
      <div className="reveal">
        <p className="label-tag mb-4" style={{ color: 'var(--accent)' }}>Quick check · no account needed</p>
        <h1 className="font-display text-heading-sm mb-4" style={{ color: 'var(--ink)' }}>What are you checking?</h1>
        <p className="text-prose mb-10" style={{ color: 'var(--ink-soft)', maxWidth: '34rem' }}>
          Tell us the drug or prescription you want checked, and what else you're already
          taking. Your entries are sent for analysis, but this guest check is not saved
          to an account or sent to a care team.
        </p>

        <form onSubmit={handleSubmit} className="space-y-9">
          <CheckingField
            ref={checkingRef}
            value={draft.checking}
            onChange={(v) => setDraft((d) => ({ ...d, checking: v }))}
          />
          <TagInput
            ref={currentRef}
            label="Current medications"
            placeholder="e.g. warfarin"
            items={draft.current}
            canAdd={totalMedsCanAdd}
            onChange={(items) => setDraft((d) => ({ ...d, current: items }))}
          />
          <TagInput
            ref={allergyRef}
            label="Known allergies or past reactions"
            placeholder="e.g. penicillin"
            items={draft.allergies}
            canAdd={() => draft.allergies.length < MAX_MEDS_TOTAL}
            onChange={(items) => setDraft((d) => ({ ...d, allergies: items }))}
          />
          <details>
            <summary className="field-label cursor-pointer mb-4" style={{ color: 'var(--ink-soft)' }}>Add context · optional</summary>
            <label htmlFor="check-notes" className="sr-only">Additional context</label>
            <textarea
              id="check-notes"
              rows={3}
              maxLength={600}
              placeholder="Past reactions or other context to help explain your results. Avoid identifying details."
              value={draft.notes}
              onChange={(e) => setDraft((d) => ({ ...d, notes: e.target.value }))}
              className="field w-full border rounded-lg px-3.5 py-2.5 text-[13.5px]"
              style={{ borderColor: 'var(--line)' }}
            />
          </details>

          {error && (
            <div role="alert" className="text-[14px] font-medium" style={{ color: 'var(--critical)' }}>{error}</div>
          )}

          <div className="flex flex-col-reverse sm:flex-row items-start sm:items-center justify-between gap-6 pt-1">
            <p className="text-[13px] max-w-xs leading-relaxed" style={{ color: 'var(--ink-soft)' }}>
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
