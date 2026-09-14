// Session + API layer — ported 1:1 from static/patient/index.html's
// token()/setToken()/getUser()/setUser()/api() functions. Same
// sessionStorage keys, so a user's existing session from the old app
// still works if they load this one in the same browser.
const API = window.location.origin;

export function token() {
  return sessionStorage.getItem('medtrust_token');
}
export function setToken(t) {
  t ? sessionStorage.setItem('medtrust_token', t) : sessionStorage.removeItem('medtrust_token');
}
export function setUser(u) {
  sessionStorage.setItem('medtrust_user', JSON.stringify(u));
}
export function getUser() {
  try {
    return JSON.parse(sessionStorage.getItem('medtrust_user'));
  } catch {
    return null;
  }
}

export async function api(path, opts = {}) {
  const headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
  if (token()) headers['Authorization'] = `Bearer ${token()}`;
  const res = await fetch(`${API}${path}`, { ...opts, headers });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
  return data;
}

// The LLM-generated explanation text sometimes comes back with markdown
// (**bold**, blank-line paragraphs) even though nothing renders it — this
// turns that into real HTML for use with dangerouslySetInnerHTML. Input is
// escaped first, so only the tags this function inserts itself are real.
function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
export function mdLite(raw) {
  const bolded = esc(raw).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  const paras = bolded.split(/\n\s*\n/).map((p) => p.trim()).filter(Boolean);
  if (paras.length > 1) return paras.map((p) => `<p class="mb-2.5 last:mb-0">${p.replace(/\n/g, '<br/>')}</p>`).join('');
  return bolded.replace(/\n/g, '<br/>');
}
