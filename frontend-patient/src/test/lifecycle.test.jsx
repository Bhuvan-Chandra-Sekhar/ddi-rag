import { describe, expect, it, vi } from 'vitest';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Scanning from '../screens/Scanning.jsx';
import Explanation from '../components/Explanation.jsx';
import DrugInfoPanel from '../components/DrugInfoPanel.jsx';
import { api } from '../api.js';

// api() is replaced so each test controls exactly when (and whether) a
// request settles. The real api() timeout and abort behaviour is covered
// in api.test.js and, end to end, in the Playwright suite.
vi.mock('../api.js', async (original) => ({ ...(await original()), api: vi.fn() }));

const deferred = () => {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
};
const inputs = { medications: ['aspirin'], allergies: [], notes: '' };

describe('Scanning', () => {
  it('ignores a result that arrives after it was unmounted', async () => {
    const request = deferred();
    api.mockReturnValue(request.promise);
    const onDone = vi.fn();
    const onError = vi.fn();
    const { unmount } = render(<Scanning medications={['aspirin']} allergies={[]} onDone={onDone} onError={onError} />);
    unmount();
    await act(async () => { request.resolve({ findings: [] }); });
    expect(onDone).not.toHaveBeenCalled();
    expect(onError).not.toHaveBeenCalled();
  });

  it('ignores an error that arrives after it was unmounted', async () => {
    const request = deferred();
    api.mockReturnValue(request.promise);
    const onError = vi.fn();
    const { unmount } = render(<Scanning medications={['aspirin']} allergies={[]} onDone={vi.fn()} onError={onError} />);
    unmount();
    await act(async () => { request.reject(new Error('late failure')); });
    expect(onError).not.toHaveBeenCalled();
  });

  it('cycles its status text and leaves no timer running once unmounted', async () => {
    vi.useFakeTimers();
    api.mockReturnValue(new Promise(() => {}));
    const { unmount } = render(<Scanning medications={['aspirin']} allergies={[]} onDone={vi.fn()} onError={vi.fn()} />);
    expect(screen.getByText('Resolving medication identities…')).toBeInTheDocument();
    await act(async () => { await vi.advanceTimersByTimeAsync(1100); });
    expect(screen.getByText('Cross-referencing known interactions…')).toBeInTheDocument();
    expect(vi.getTimerCount()).toBeGreaterThan(0);
    unmount();
    expect(vi.getTimerCount()).toBe(0);
  });

  it('stays on the scanning screen, without crashing or reporting anything, while a request never resolves', async () => {
    vi.useFakeTimers();
    api.mockReturnValue(new Promise(() => {}));
    const onDone = vi.fn();
    const onError = vi.fn();
    render(<Scanning medications={['aspirin']} allergies={[]} onDone={onDone} onError={onError} />);
    await act(async () => { await vi.advanceTimersByTimeAsync(60000); });
    expect(screen.getByText('Reading the evidence')).toBeInTheDocument();
    expect(onDone).not.toHaveBeenCalled();
    expect(onError).not.toHaveBeenCalled();
  });
});

describe('Explanation', () => {
  it('aborts its request and ignores the response when unmounted mid-flight', async () => {
    const request = deferred();
    let signal;
    api.mockImplementation((_path, opts) => { signal = opts.signal; return request.promise; });
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    const { unmount } = render(<Explanation findingIndex={1} inputs={inputs} />);
    expect(signal.aborted).toBe(false);
    unmount();
    expect(signal.aborted).toBe(true);
    await act(async () => { request.resolve({ explanation: 'too late', citations: [] }); });
    expect(errorSpy).not.toHaveBeenCalled();
  });

  it('shows a loading state, not a result or an error, while the request never resolves', () => {
    api.mockReturnValue(new Promise(() => {}));
    render(<Explanation findingIndex={1} inputs={inputs} />);
    expect(screen.getByText(/working out what this means for you/i)).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('does not show an error for a request it cancelled itself', async () => {
    api.mockImplementation((_path, opts) => new Promise((_resolve, reject) => {
      opts.signal.addEventListener('abort', () => reject(Object.assign(new Error('aborted'), { name: 'AbortError' })));
    }));
    const { unmount } = render(<Explanation findingIndex={1} inputs={inputs} />);
    unmount();
    expect(document.body.textContent).not.toMatch(/couldn't load/i);
  });

  it('sends exactly one retry however fast the Try again button is clicked', async () => {
    const user = userEvent.setup();
    api.mockRejectedValueOnce(new Error('Explanation unavailable'))
      .mockImplementation(() => new Promise(() => {}));
    render(<Explanation findingIndex={1} inputs={inputs} />);
    const retry = await screen.findByRole('button', { name: /try again/i });
    await user.dblClick(retry);
    expect(api).toHaveBeenCalledTimes(2);
  });

  it('shows the answer to the retry, not the failure it replaced', async () => {
    const user = userEvent.setup();
    api.mockRejectedValueOnce(new Error('Explanation unavailable'))
      .mockResolvedValueOnce({ explanation: 'Second time lucky', citations: [] });
    render(<Explanation findingIndex={1} inputs={inputs} />);
    await user.click(await screen.findByRole('button', { name: /try again/i }));
    expect(await screen.findByText('Second time lucky')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
});

describe('DrugInfoPanel', () => {
  const answer = (drug, text) => ({ detected_drugs: [drug], results: [{ answer: text }] });

  it('shows the newest drug when an older lookup finishes last', async () => {
    const first = deferred();
    const second = deferred();
    api.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
    const { rerender } = render(<DrugInfoPanel med={{ input: 'aspirin' }} />);
    rerender(<DrugInfoPanel med={{ input: 'warfarin' }} />);
    await act(async () => { second.resolve(answer('warfarin', 'Warfarin label')); });
    expect(await screen.findByText('Warfarin label')).toBeInTheDocument();
    await act(async () => { first.resolve(answer('aspirin', 'Aspirin label')); });
    expect(screen.getByText('Warfarin label')).toBeInTheDocument();
    expect(screen.queryByText('Aspirin label')).not.toBeInTheDocument();
  });

  it('aborts the superseded lookup instead of letting it run on', () => {
    const signals = [];
    api.mockImplementation((_path, opts) => { signals.push(opts.signal); return new Promise(() => {}); });
    const { rerender, unmount } = render(<DrugInfoPanel med={{ input: 'aspirin' }} />);
    rerender(<DrugInfoPanel med={{ input: 'warfarin' }} />);
    expect(signals[0].aborted).toBe(true);
    expect(signals[1].aborted).toBe(false);
    unmount();
    expect(signals[1].aborted).toBe(true);
  });

  it('ignores a failure from a lookup it already moved on from', async () => {
    const first = deferred();
    const second = deferred();
    api.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
    const { rerender } = render(<DrugInfoPanel med={{ input: 'aspirin' }} />);
    rerender(<DrugInfoPanel med={{ input: 'warfarin' }} />);
    await act(async () => { second.resolve(answer('warfarin', 'Warfarin label')); });
    await act(async () => { first.reject(new Error('stale failure')); });
    await waitFor(() => expect(screen.getByText('Warfarin label')).toBeInTheDocument());
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
});
