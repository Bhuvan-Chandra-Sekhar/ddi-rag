import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api, getUser, mdLite, setToken, setUser, token } from '../api.js';

describe('session and API boundary', () => {
  beforeEach(() => vi.stubGlobal('fetch', vi.fn()));

  it('stores and removes the authentication token', () => {
    setToken('abc');
    expect(token()).toBe('abc');
    setToken(null);
    expect(token()).toBeNull();
  });

  it('stores a user and safely handles malformed stored JSON', () => {
    setUser({ full_name: 'Alex' });
    expect(getUser()).toEqual({ full_name: 'Alex' });
    sessionStorage.setItem('medtrust_user', '{broken');
    expect(getUser()).toBeNull();
  });

  it('sends JSON and authentication headers to the same origin', async () => {
    setToken('secret');
    fetch.mockResolvedValue({ ok: true, json: async () => ({ ok: true }) });
    await expect(api('/api/test', { method: 'POST', body: '{}' })).resolves.toEqual({ ok: true });
    expect(fetch).toHaveBeenCalledWith(`${window.location.origin}/api/test`, expect.objectContaining({
      method: 'POST',
      headers: expect.objectContaining({ 'Content-Type': 'application/json', Authorization: 'Bearer secret' }),
    }));
  });

  it('uses the server error and falls back to the HTTP status', async () => {
    fetch.mockResolvedValueOnce({ ok: false, status: 422, json: async () => ({ error: 'Invalid drug' }) });
    await expect(api('/bad')).rejects.toThrow('Invalid drug');
    fetch.mockResolvedValueOnce({ ok: false, status: 503, json: async () => { throw new Error('not json'); } });
    await expect(api('/down')).rejects.toThrow('Request failed (503)');
  });

  it('escapes untrusted explanation HTML while allowing lightweight formatting', () => {
    const html = mdLite('<script>alert(1)</script>\n\n**Important**');
    expect(html).not.toContain('<script>');
    expect(html).toContain('&lt;script&gt;');
    expect(html).toContain('<strong>Important</strong>');
    expect(html.match(/<p/g)).toHaveLength(2);
  });
});
