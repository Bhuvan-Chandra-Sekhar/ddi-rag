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
// The clinical console (ddi_rag/static/clinical/index.html) is a separate
// page with its own session keys. A clinician who signs in through this
// app's "Clinic portal" is redirected there, so the session has to be
// written where the console looks for it (it boots on `cc_token`), and
// not under the patient keys — a staff token under those would only make
// the patient dashboard fail on a later visit.
export function setConsoleSession(accessToken, user) {
  sessionStorage.setItem('cc_token', accessToken);
  sessionStorage.setItem('cc_user', JSON.stringify(user));
}
export function getUser() {
  try {
    return JSON.parse(sessionStorage.getItem('medtrust_user'));
  } catch {
    return null;
  }
}

const DEFAULT_TIMEOUT_MS = 45000;

// Callers may pass `signal` to cancel (an AbortError is re-thrown untouched
// so they can tell "I cancelled" from "it failed") and `timeoutMs` to
// override the default. Error text prefers the server's human `message`
// over its machine `error` code: the backend sends both for 503s
// ({"error": "temporarily_unavailable", "message": "..."}), and showing
// the code to a patient is a bug.
export async function api(path, opts = {}) {
  const { timeoutMs = DEFAULT_TIMEOUT_MS, signal: callerSignal, ...fetchOpts } = opts;
  if (callerSignal && callerSignal.aborted) {
    throw Object.assign(new Error('The request was cancelled.'), { name: 'AbortError' });
  }
  const headers = { 'Content-Type': 'application/json', ...(fetchOpts.headers || {}) };
  const t = token();
  if (t) headers['Authorization'] = `Bearer ${t}`;

  const controller = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => { timedOut = true; controller.abort(); }, timeoutMs);
  const onCallerAbort = () => controller.abort();
  if (callerSignal) callerSignal.addEventListener('abort', onCallerAbort, { once: true });

  try {
    let res;
    try {
      res = await fetch(`${API}${path}`, { ...fetchOpts, headers, signal: controller.signal });
    } catch (err) {
      if (timedOut) throw new Error('The request timed out. Please try again.');
      if (err && err.name === 'AbortError') throw err;
      throw new Error('Could not reach the server. Check your connection and try again.');
    }

    if (res.status === 204) return {};
    let data = null;
    try {
      data = await res.json();
    } catch {
      data = null;
    }
    if (!res.ok) throw new Error((data && (data.message || data.error)) || `Request failed (${res.status})`);
    // A 2xx with an unparseable body must not become an empty "success" —
    // callers would render it as a result with no findings.
    if (data === null) throw new Error('The server returned an unreadable response. Please try again.');
    return data;
  } finally {
    clearTimeout(timer);
    if (callerSignal) callerSignal.removeEventListener('abort', onCallerAbort);
  }
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
