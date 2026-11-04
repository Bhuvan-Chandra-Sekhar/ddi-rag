import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import CheckingField from '../components/CheckingField.jsx';
import TagInput from '../components/TagInput.jsx';
import Checker from '../screens/Checker.jsx';
import { MAX_MEDS_TOTAL } from '../meta.js';

const empty = { checking: '', current: [], allergies: [], notes: '' };

// Real state, the way App holds it, instead of a vi.fn() that only records
// that it was called. `latest.current` is always the draft the app would
// hold right now.
function Harness({ initial = empty, onSubmit = vi.fn(), latest }) {
  const [draft, setDraft] = useState(initial);
  latest.current = draft;
  return <Checker draft={draft} setDraft={setDraft} onSubmit={onSubmit} />;
}
const renderChecker = (initial = empty, onSubmit = vi.fn()) => {
  const latest = { current: initial };
  render(<Harness initial={initial} onSubmit={onSubmit} latest={latest} />);
  return { latest, onSubmit };
};

const medsField = () => screen.getByLabelText('Current medications');
const allergyField = () => screen.getByLabelText('Known allergies or past reactions');
const removeButtons = () => screen.queryAllByRole('button', { name: /^Remove / });
const addTo = async (user, field, names) => {
  for (const name of names) await user.type(field, `${name}{Enter}`);
};
const names = (count, prefix = 'drug') => Array.from({ length: count }, (_, i) => `${prefix}${i + 1}`);

describe('medication inputs', () => {
  it('adds a trimmed tag with Enter and removes it accessibly', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const { rerender } = render(<TagInput label="Current medications" placeholder="Drug" items={[]} onChange={onChange} />);
    await user.type(screen.getByLabelText('Current medications'), '  warfarin{Enter}');
    expect(onChange).toHaveBeenCalledWith(['warfarin']);
    rerender(<TagInput label="Current medications" placeholder="Drug" items={['warfarin']} onChange={onChange} />);
    await user.click(screen.getByRole('button', { name: 'Remove warfarin' }));
    expect(onChange).toHaveBeenLastCalledWith([]);
  });

  it('adds with a comma and with the Add button, and ignores blank input', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<TagInput label="Current medications" placeholder="Drug" items={[]} onChange={onChange} />);
    await user.type(screen.getByLabelText('Current medications'), 'aspirin,');
    expect(onChange).toHaveBeenLastCalledWith(['aspirin']);
    await user.type(screen.getByLabelText('Current medications'), 'ibuprofen');
    await user.click(screen.getByRole('button', { name: 'Add' }));
    expect(onChange).toHaveBeenLastCalledWith(['ibuprofen']);
    onChange.mockClear();
    await user.type(screen.getByLabelText('Current medications'), '   {Enter}');
    expect(onChange).not.toHaveBeenCalled();
  });

  it('does not add a tag when the limit refuses it, and says why', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<TagInput label="Current medications" placeholder="Drug" items={[]} onChange={onChange} canAdd={() => false} limitMessage="List is full." />);
    await user.type(screen.getByLabelText('Current medications'), 'aspirin');
    await user.click(screen.getByRole('button', { name: 'Add' }));
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByRole('status')).toHaveTextContent('List is full.');
  });

  it('clears the limit message once the person edits the field or removes an item', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<TagInput label="Meds" placeholder="Drug" items={['warfarin']} onChange={onChange} canAdd={() => false} />);
    await user.type(screen.getByLabelText('Meds'), 'aspirin{Enter}');
    expect(screen.getByRole('status')).toBeInTheDocument();
    await user.type(screen.getByLabelText('Meds'), 'x');
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    await user.type(screen.getByLabelText('Meds'), '{Enter}');
    expect(screen.getByRole('status')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Remove warfarin' }));
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });

  it('allows only one medication in the checking field until removed', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const { rerender } = render(<CheckingField value="" onChange={onChange} />);
    await user.type(screen.getByLabelText('Medication to check'), 'aspirin,');
    expect(onChange).toHaveBeenCalledWith('aspirin');
    rerender(<CheckingField value="aspirin" onChange={onChange} />);
    expect(screen.queryByLabelText('Medication to check')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Remove aspirin' }));
    expect(onChange).toHaveBeenLastCalledWith('');
  });
});

describe('quick check form', () => {
  it('blocks an empty submission with an alert', async () => {
    const user = userEvent.setup();
    const { onSubmit } = renderChecker();
    await user.click(screen.getByRole('button', { name: /check now/i }));
    expect(screen.getByRole('alert')).toHaveTextContent('Add at least one drug to check.');
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('flushes uncommitted text from every field before submitting', async () => {
    const user = userEvent.setup();
    const { latest, onSubmit } = renderChecker();
    await user.type(screen.getByLabelText('Medication to check'), 'aspirin');
    await user.type(medsField(), 'warfarin');
    await user.type(allergyField(), 'penicillin');
    await user.click(screen.getByRole('button', { name: /check now/i }));
    expect(latest.current).toMatchObject({ checking: 'aspirin', current: ['warfarin'], allergies: ['penicillin'] });
    expect(onSubmit).toHaveBeenCalledOnce();
  });

  it('saves the optional context into the notes field and nothing else', async () => {
    const user = userEvent.setup();
    const { latest } = renderChecker();
    await user.click(screen.getByText(/add context/i));
    await user.type(screen.getByLabelText('Additional context'), 'Previous rash');
    expect(latest.current).toEqual({ ...empty, notes: 'Previous rash' });
    expect(screen.getByLabelText('Additional context')).toHaveValue('Previous rash');
  });

  it('keeps the saved notes through a submission and caps their length', async () => {
    const user = userEvent.setup();
    const { latest, onSubmit } = renderChecker();
    await user.type(screen.getByLabelText('Medication to check'), 'aspirin{Enter}');
    await user.click(screen.getByText(/add context/i));
    await user.type(screen.getByLabelText('Additional context'), 'Previous rash');
    await user.click(screen.getByRole('button', { name: /check now/i }));
    expect(onSubmit).toHaveBeenCalledOnce();
    expect(latest.current).toMatchObject({ checking: 'aspirin', notes: 'Previous rash' });
    expect(screen.getByLabelText('Additional context')).toHaveAttribute('maxlength', '600');
  });

  it('keeps the safety disclaimer visible', () => {
    renderChecker();
    expect(screen.getByText(/not reviewed by a pharmacist/i)).toBeInTheDocument();
  });
});

describe('medication limit through the real form', () => {
  it('uses a limit of eight', () => {
    expect(MAX_MEDS_TOTAL).toBe(8);
  });

  it('accepts exactly eight current medications without complaint', async () => {
    const user = userEvent.setup();
    const { latest } = renderChecker();
    await addTo(user, medsField(), names(8));
    expect(latest.current.current).toHaveLength(8);
    expect(removeButtons()).toHaveLength(8);
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });

  it('rejects a ninth medication and tells the person why', async () => {
    const user = userEvent.setup();
    const { latest } = renderChecker();
    await addTo(user, medsField(), names(9));
    expect(latest.current.current).toEqual(names(8));
    expect(removeButtons()).toHaveLength(8);
    expect(screen.getByRole('status')).toHaveTextContent(/up to 8 medications/i);
  });

  it('lets another be added after one is removed', async () => {
    const user = userEvent.setup();
    const { latest } = renderChecker();
    await addTo(user, medsField(), names(9));
    // The refused ninth entry stays in the field rather than being lost.
    expect(medsField()).toHaveValue('drug9');
    await user.click(screen.getByRole('button', { name: 'Remove drug1' }));
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    await user.clear(medsField());
    await user.type(medsField(), 'newdrug{Enter}');
    expect(latest.current.current).toHaveLength(8);
    expect(latest.current.current).toContain('newdrug');
    expect(latest.current.current).not.toContain('drug1');
  });

  it('counts the "checking" medication toward the same limit', async () => {
    const user = userEvent.setup();
    const { latest } = renderChecker({ ...empty, checking: 'aspirin' });
    await addTo(user, medsField(), names(8));
    expect(latest.current.checking).toBe('aspirin');
    expect(latest.current.current).toEqual(names(7)); // 1 + 7 = 8
    expect(screen.getByRole('status')).toHaveTextContent(/up to 8 medications/i);
  });

  it('limits allergies separately from medications', async () => {
    const user = userEvent.setup();
    const { latest } = renderChecker();
    await addTo(user, medsField(), names(8));
    await addTo(user, allergyField(), names(8, 'allergy'));
    expect(latest.current.current).toHaveLength(8);
    expect(latest.current.allergies).toHaveLength(8);
    await user.type(allergyField(), 'allergy9{Enter}');
    expect(latest.current.allergies).toHaveLength(8);
    expect(screen.getByRole('status')).toHaveTextContent(/up to 8 allergies/i);
  });

  it('does not exceed the limit, and does not silently drop text, when a full list is submitted with an uncommitted entry', async () => {
    const user = userEvent.setup();
    const { latest, onSubmit } = renderChecker({ ...empty, current: names(8) });
    await user.type(medsField(), 'ninth');
    await user.click(screen.getByRole('button', { name: /check now/i }));
    expect(latest.current.current).toEqual(names(8));
    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByRole('alert')).toHaveTextContent(/was not added because the list is full/i);
  });

  it('submits normally once the refused entry is cleared away', async () => {
    const user = userEvent.setup();
    const { onSubmit } = renderChecker({ ...empty, current: names(8) });
    await user.type(medsField(), 'ninth');
    await user.click(screen.getByRole('button', { name: /check now/i }));
    expect(onSubmit).not.toHaveBeenCalled();
    await user.clear(medsField());
    await user.click(screen.getByRole('button', { name: /check now/i }));
    expect(onSubmit).toHaveBeenCalledOnce();
  });
});
