import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import CheckingField from '../components/CheckingField.jsx';
import TagInput from '../components/TagInput.jsx';
import Checker from '../screens/Checker.jsx';

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

  it('does not add a tag when the medication limit refuses it', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<TagInput label="Current medications" placeholder="Drug" items={[]} onChange={onChange} canAdd={() => false} />);
    await user.type(screen.getByLabelText('Current medications'), 'aspirin');
    await user.click(screen.getByRole('button', { name: 'Add' }));
    expect(onChange).not.toHaveBeenCalled();
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
  const empty = { checking: '', current: [], allergies: [], notes: '' };

  it('blocks an empty submission with an alert', async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<Checker draft={empty} setDraft={vi.fn()} onSubmit={onSubmit} />);
    await user.click(screen.getByRole('button', { name: /check now/i }));
    expect(screen.getByRole('alert')).toHaveTextContent('Add at least one drug to check.');
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('flushes uncommitted text before submitting', async () => {
    const user = userEvent.setup();
    const setDraft = vi.fn();
    const onSubmit = vi.fn();
    render(<Checker draft={empty} setDraft={setDraft} onSubmit={onSubmit} />);
    await user.type(screen.getByLabelText('Medication to check'), 'aspirin');
    await user.click(screen.getByRole('button', { name: /check now/i }));
    expect(setDraft).toHaveBeenCalledWith(expect.objectContaining({ checking: 'aspirin' }));
    expect(onSubmit).toHaveBeenCalledOnce();
  });

  it('captures optional context and preserves the safety disclaimer', async () => {
    const user = userEvent.setup();
    const setDraft = vi.fn((updater) => updater(empty));
    render(<Checker draft={empty} setDraft={setDraft} onSubmit={vi.fn()} />);
    await user.click(screen.getByText(/add context/i));
    await user.type(screen.getByLabelText('Additional context'), 'Previous rash');
    expect(setDraft).toHaveBeenCalled();
    expect(screen.getByText(/not reviewed by a pharmacist/i)).toBeInTheDocument();
  });
});
