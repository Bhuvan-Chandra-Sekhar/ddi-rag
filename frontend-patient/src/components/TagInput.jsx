import { forwardRef, useId, useImperativeHandle, useState } from 'react';

// Controlled version of the old tagInputHtml()/wireTagInput() pair — same
// behavior (Enter or comma commits, click removes, whole pill is the
// click target), just driven by React state instead of manual DOM
// rebuilds on every change. Exposes flush() via ref so the form's submit
// handler can commit text a user typed but never pressed Enter/Add on —
// the original read straight from the DOM input for this; refs are the
// React equivalent of that same "grab whatever's still sitting there".
const TagInput = forwardRef(function TagInput({ label, placeholder, items, onChange, canAdd = () => true }, ref) {
  const [draft, setDraft] = useState('');
  const inputId = useId();

  const commit = () => {
    const v = draft.trim();
    if (v && canAdd()) {
      onChange([...items, v]);
      setDraft('');
      return [...items, v];
    }
    return items;
  };

  useImperativeHandle(ref, () => ({ flush: commit }));

  return (
    <div>
      <label htmlFor={inputId} className="field-label block mb-2" style={{ color: 'var(--ink-soft)' }}>
        {label}
      </label>
      <div className="flex gap-2 mb-2">
        <input
          id={inputId}
          type="text"
          autoComplete="off"
          placeholder={placeholder}
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
      <div className="flex flex-wrap gap-2 min-h-[2px]">
        {items.map((v, i) => (
          <button
            key={`${v}-${i}`}
            type="button"
            title={`Remove ${v}`}
            aria-label={`Remove ${v}`}
            onClick={() => onChange(items.filter((_, idx) => idx !== i))}
            className="chip chip-remove inline-flex items-center gap-1.5 text-[12.5px] font-medium pl-3 pr-2.5 py-1 rounded-full"
          >
            {v}
            <span className="text-[15px] leading-none" aria-hidden="true">×</span>
          </button>
        ))}
      </div>
    </div>
  );
});

export default TagInput;
