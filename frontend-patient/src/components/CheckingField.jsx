import { forwardRef, useId, useImperativeHandle, useState } from 'react';

// "Checking" is deliberately one drug at a time, not a tag list like the
// other fields — it represents a single question ("does THIS interact with
// what I'm already on?"). Once one is set, the input hides in favor of a
// single chip; removing that chip is the only way back to typing a new one.
const CheckingField = forwardRef(function CheckingField({ value, onChange }, ref) {
  const [draft, setDraft] = useState('');
  const inputId = useId();
  const hasDrug = Boolean(value);

  const commit = () => {
    const v = draft.trim();
    if (v && !hasDrug) {
      onChange(v);
      setDraft('');
    }
    return value || v;
  };

  useImperativeHandle(ref, () => ({ flush: commit }));

  return (
    <div>
      <label htmlFor={inputId} className="field-label block mb-2" style={{ color: 'var(--ink-soft)' }}>
        Medication to check
      </label>
      {hasDrug ? (
        <>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              title={`Remove ${value}`}
              aria-label={`Remove ${value}`}
              onClick={() => onChange('')}
              className="chip chip-remove inline-flex items-center gap-1.5 text-[12.5px] font-medium pl-3 pr-2.5 py-1 rounded-full"
            >
              {value}
              <span className="text-[15px] leading-none" aria-hidden="true">×</span>
            </button>
          </div>
          <p className="text-[11px] mt-1.5" style={{ color: 'var(--ink-faint)' }}>
            One at a time — remove this to check a different drug instead.
          </p>
        </>
      ) : (
        <div className="flex gap-2">
          <input
            id={inputId}
            type="text"
            autoComplete="off"
            placeholder="e.g. aspirin — one medication"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ',') {
                e.preventDefault();
                commit();
              }
            }}
            className="field min-w-0 flex-1 border rounded-lg px-3.5 py-2.5 text-[15px]"
            style={{ borderColor: 'var(--line)' }}
          />
          <button
            type="button"
            onClick={commit}
            className="px-4 rounded-lg border text-[13px] font-semibold"
            style={{ borderColor: 'var(--line)', color: 'var(--primary)' }}
          >
            Add
          </button>
        </div>
      )}
    </div>
  );
});

export default CheckingField;
