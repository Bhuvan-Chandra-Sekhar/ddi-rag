import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api, getUser, mdLite, setConsoleSession, setToken, setUser, token } from '../api.js';

const jsonResponse = (body, init = {}) => ({
  ok: init.ok ?? true,
  status: init.status ?? 200,
  json: async () => body,
});

// A fetch that never answers on its own but, like the real one, rejects
// with AbortError the moment its signal fires.
const hangingFetch = () =>
  vi.fn(
    (_url, init) =>
      new Promise((_resolve, reject) => {
        init.signal.addEventListener('abort', () => {
          reject(Object.assign(new Error('The operation was aborted.'), { name: 'AbortError' }));
        });
      })
  );

describe('session storage', () => {
  it('stores and removes the authentication token', () => {
    setToken('abc');
    expect(token()).toBe('abc');
    setToken(null);
    expect(token()).toBeNull();
  });

  it('treats an empty token as signed out', () => {
    setToken('abc');
    setToken('');
    expect(token()).toBeNull();
  });

  it('stores the clinical console session under the console\'s own keys and leaves the patient session alone', () => {
    setConsoleSession('staff-token', { role: 'pharmacist' });
    expect(sessionStorage.getItem('cc_token')).toBe('staff-token');
    expect(JSON.parse(sessionStorage.getItem('cc_user'))).toEqual({ role: 'pharmacist' });
    expect(token()).toBeNull();
    expect(getUser()).toBeNull();
  });

  it('stores a user and safely handles malformed stored JSON', () => {
    setUser({ full_name: 'Alex' });
    expect(getUser()).toEqual({ full_name: 'Alex' });
    sessionStorage.setItem('medtrust_user', '{broken');
    expect(getUser()).toBeNull();
  });
});

describe('api() request', () => {
  beforeEach(() => vi.stubGlobal('fetch', vi.fn()));

  it('sends JSON and authentication headers to the same origin', async () => {
    setToken('secret');
    fetch.mockResolvedValue(jsonResponse({ ok: true }));
    await expect(api('/api/test', { method: 'POST', body: '{}' })).resolves.toEqual({ ok: true });
    expect(fetch).toHaveBeenCalledWith(`${window.location.origin}/api/test`, expect.objectContaining({
      method: 'POST',
      headers: expect.objectContaining({ 'Content-Type': 'application/json', Authorization: 'Bearer secret' }),
    }));
  });

  it('sends no Authorization header when signed out', async () => {
    fetch.mockResolvedValue(jsonResponse({}));
    await api('/api/test');
    expect(fetch.mock.calls[0][1].headers).not.toHaveProperty('Authorization');
  });

  it('sends no Authorization header after an empty token is set', async () => {
    setToken('');
    fetch.mockResolvedValue(jsonResponse({}));
    await api('/api/test');
    expect(fetch.mock.calls[0][1].headers).not.toHaveProperty('Authorization');
  });

  it('merges caller headers with the defaults instead of replacing them', async () => {
    setToken('secret');
    fetch.mockResolvedValue(jsonResponse({}));
    await api('/api/test', { headers: { 'X-Trace': 'abc' } });
    expect(fetch.mock.calls[0][1].headers).toEqual({
      'Content-Type': 'application/json',
      Authorization: 'Bearer secret',
      'X-Trace': 'abc',
    });
  });

  it('returns an empty object for 204 No Content without reading a body', async () => {
    const json = vi.fn();
    fetch.mockResolvedValue({ ok: true, status: 204, json });
    await expect(api('/api/test')).resolves.toEqual({});
    expect(json).not.toHaveBeenCalled();
  });
});

describe('api() errors', () => {
  beforeEach(() => vi.stubGlobal('fetch', vi.fn()));

  it('uses the server error and falls back to the HTTP status', async () => {
    fetch.mockResolvedValueOnce(jsonResponse({ error: 'Invalid drug' }, { ok: false, status: 422 }));
    await expect(api('/bad')).rejects.toThrow('Invalid drug');
    fetch.mockResolvedValueOnce({ ok: false, status: 503, json: async () => { throw new Error('not json'); } });
    await expect(api('/down')).rejects.toThrow('Request failed (503)');
  });

  it('shows the human message, not the machine code, when the server sends both', async () => {
    // This is the real shape of the backend's 503s, e.g. the kill switch.
    fetch.mockResolvedValue(jsonResponse(
      { error: 'temporarily_unavailable', message: 'This feature is temporarily disabled for maintenance.' },
      { ok: false, status: 503 }
    ));
    const failure = await api('/api/self-check').catch((err) => err);
    expect(failure.message).toBe('This feature is temporarily disabled for maintenance.');
    expect(failure.message).not.toContain('temporarily_unavailable');
  });

  it('uses message alone when there is no error field', async () => {
    fetch.mockResolvedValue(jsonResponse({ message: 'Only a message' }, { ok: false, status: 400 }));
    await expect(api('/x')).rejects.toThrow('Only a message');
  });

  it('rejects a successful response whose body is not valid JSON', async () => {
    // Used to resolve to {} and render as a result with no findings.
    fetch.mockResolvedValue({ ok: true, status: 200, json: async () => { throw new SyntaxError('Unexpected token <'); } });
    await expect(api('/api/self-check')).rejects.toThrow(/unreadable response/i);
  });

  it('turns a network failure into a readable message', async () => {
    fetch.mockRejectedValue(new TypeError('Failed to fetch'));
    const failure = await api('/x').catch((err) => err);
    expect(failure.message).toMatch(/could not reach the server/i);
    expect(failure.message).not.toContain('Failed to fetch');
  });

  it('rethrows a caller-initiated abort as an AbortError, not a network error', async () => {
    vi.stubGlobal('fetch', hangingFetch());
    const controller = new AbortController();
    const pending = api('/x', { signal: controller.signal });
    controller.abort();
    await expect(pending).rejects.toMatchObject({ name: 'AbortError' });
  });

  it('does not start a request when the caller signal is already aborted', async () => {
    const fetchSpy = hangingFetch();
    vi.stubGlobal('fetch', fetchSpy);
    const controller = new AbortController();
    controller.abort();
    await expect(api('/x', { signal: controller.signal })).rejects.toMatchObject({ name: 'AbortError' });
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});

describe('api() timeout', () => {
  it('gives up on a request that never resolves and says so', async () => {
    vi.useFakeTimers();
    vi.stubGlobal('fetch', hangingFetch());
    const outcome = expect(api('/slow')).rejects.toThrow(/timed out/i);
    await vi.advanceTimersByTimeAsync(45000);
    await outcome;
  });

  it('honours a caller-specified timeout', async () => {
    vi.useFakeTimers();
    vi.stubGlobal('fetch', hangingFetch());
    const outcome = expect(api('/slow', { timeoutMs: 1000 })).rejects.toThrow(/timed out/i);
    await vi.advanceTimersByTimeAsync(1000);
    await outcome;
  });

  it('leaves no timer running after a request completes', async () => {
    vi.useFakeTimers();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ ok: true })));
    await api('/x');
    expect(vi.getTimerCount()).toBe(0);
  });
});

describe('mdLite', () => {
  it('escapes untrusted explanation HTML while allowing lightweight formatting', () => {
    const html = mdLite('<script>alert(1)</script>\n\n**Important**');
    expect(html).not.toContain('<script>');
    expect(html).toContain('&lt;script&gt;');
    expect(html).toContain('<strong>Important</strong>');
    expect(html.match(/<p/g)).toHaveLength(2);
  });

  it('formats several bold sections independently', () => {
    expect(mdLite('**One** and **Two**')).toBe('<strong>One</strong> and <strong>Two</strong>');
  });

  it('neutralises attribute-injection and event-handler payloads', () => {
    const html = mdLite(`"><img src=x onerror="alert(1)"> '--' <a href="javascript:alert(1)">x</a>`);
    expect(html).not.toMatch(/<img|<a /);
    expect(html).toContain('&quot;');
    expect(html).toContain('&#39;');
    expect(html).toContain('&lt;img');
  });

  it('escapes entities exactly once rather than double-encoding', () => {
    expect(mdLite('Tom & Jerry <3')).toBe('Tom &amp; Jerry &lt;3');
  });

  it('keeps markup inside bold text escaped', () => {
    expect(mdLite('**<b>x</b>**')).toBe('<strong>&lt;b&gt;x&lt;/b&gt;</strong>');
  });

  it('turns null and undefined into empty output', () => {
    expect(mdLite(null)).toBe('');
    expect(mdLite(undefined)).toBe('');
  });

  it('handles a very long explanation without losing or reordering content', () => {
    const paragraphs = Array.from({ length: 400 }, (_, i) => `Paragraph ${i} ${'word '.repeat(40)}`.trim());
    const html = mdLite(paragraphs.join('\n\n'));
    expect(html.match(/<p /g)).toHaveLength(400);
    expect(html.indexOf('Paragraph 0 ')).toBeLessThan(html.indexOf('Paragraph 399 '));
  });
});

// These two run in order. The first plants a global stub and a mock
// implementation; the second proves setup.js removed both.
describe('test isolation', () => {
  it('plants a fetch stub and a mock implementation', () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ planted: true }));
    expect(vi.isMockFunction(globalThis.fetch)).toBe(true);
    setToken('leaky-token');
  });

  it('starts the next test with real globals and clean storage', () => {
    expect(vi.isMockFunction(globalThis.fetch)).toBe(false);
    expect(token()).toBeNull();
  });
});
