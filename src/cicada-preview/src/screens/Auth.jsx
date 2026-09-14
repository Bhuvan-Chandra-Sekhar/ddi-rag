import { useEffect, useState } from 'react';
import { api, setToken, setUser } from '../api.js';

function LoginForm({ onError, onSuccess, mode }) {
  const [submitting, setSubmitting] = useState(false);
  const [fields, setFields] = useState({ email: '', password: '' });

  const handleSubmit = async (e) => {
    e.preventDefault();
    onError('');
    setSubmitting(true);
    try {
      const data = await api('/api/auth/login', { method: 'POST', body: JSON.stringify(fields) });
      if (mode === 'clinician' && !['pharmacist', 'prescriber', 'safety_officer', 'administrator'].includes(data.user?.role)) {
        throw new Error('This account does not have clinical console access.');
      }
      setToken(data.access_token);
      setUser(data.user);
      onSuccess(data.user);
    } catch (err) {
      onError(err.message);
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label htmlFor="login-email" className="field-label block mb-1.5" style={{ color: 'var(--ink-soft)' }}>Email</label>
        <input
          id="login-email" type="email" required placeholder="you@example.com"
          value={fields.email} onChange={(e) => setFields((f) => ({ ...f, email: e.target.value }))}
          className="field w-full border rounded-lg px-3.5 py-2.5 text-sm" style={{ borderColor: 'var(--line)' }}
        />
      </div>
      <div>
        <label htmlFor="login-password" className="field-label block mb-1.5" style={{ color: 'var(--ink-soft)' }}>Password</label>
        <input
          id="login-password" type="password" required placeholder="••••••••"
          value={fields.password} onChange={(e) => setFields((f) => ({ ...f, password: e.target.value }))}
          className="field w-full border rounded-lg px-3.5 py-2.5 text-sm" style={{ borderColor: 'var(--line)' }}
        />
      </div>
      <button type="submit" disabled={submitting} className="btn-primary label-tag w-full text-white py-3 rounded-full mt-2">
        {submitting ? 'Signing in…' : 'Sign in'}
      </button>
    </form>
  );
}

function RegisterForm({ onError, onSuccess }) {
  const [submitting, setSubmitting] = useState(false);
  const [orgs, setOrgs] = useState(null);
  const [fields, setFields] = useState({ first_name: '', last_name: '', organization_id: '', email: '', password: '' });

  useEffect(() => {
    api('/v1/organizations')
      .then((data) => {
        const available = data.organizations || [];
        setOrgs(available);
        if (available.length) setFields((current) => ({ ...current, organization_id: current.organization_id || String(available[0].id) }));
      })
      .catch(() => setOrgs([]));
  }, []);

  if (orgs === null) {
    return <p className="text-caption" style={{ color: 'var(--ink-faint)' }}>Loading care organizations…</p>;
  }

  const handleSubmit = async (e) => {
    e.preventDefault();
    onError('');
    setSubmitting(true);
    try {
      await api('/api/auth/register', {
        method: 'POST',
        body: JSON.stringify({
          email: fields.email, password: fields.password,
          first_name: fields.first_name, last_name: fields.last_name,
          full_name: `${fields.first_name} ${fields.last_name}`,
          organization_id: fields.organization_id,
        }),
      });
      const data = await api('/api/auth/login', { method: 'POST', body: JSON.stringify({ email: fields.email, password: fields.password }) });
      setToken(data.access_token);
      setUser(data.user);
      onSuccess(data.user);
    } catch (err) {
      onError(err.message);
      setSubmitting(false);
    }
  };

  const set = (key) => (e) => setFields((f) => ({ ...f, [key]: e.target.value }));

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label htmlFor="register-first-name" className="field-label block mb-1.5" style={{ color: 'var(--ink-soft)' }}>First name</label>
          <input id="register-first-name" type="text" required value={fields.first_name} onChange={set('first_name')} className="field w-full border rounded-lg px-3.5 py-2.5 text-sm" style={{ borderColor: 'var(--line)' }} />
        </div>
        <div>
          <label htmlFor="register-last-name" className="field-label block mb-1.5" style={{ color: 'var(--ink-soft)' }}>Last name</label>
          <input id="register-last-name" type="text" required value={fields.last_name} onChange={set('last_name')} className="field w-full border rounded-lg px-3.5 py-2.5 text-sm" style={{ borderColor: 'var(--line)' }} />
        </div>
      </div>
      <div>
        <label htmlFor="register-organization" className="field-label block mb-1.5" style={{ color: 'var(--ink-soft)' }}>Care organization</label>
        <select id="register-organization" required value={fields.organization_id} onChange={set('organization_id')} className="field w-full border rounded-lg px-3.5 py-2.5 text-sm" style={{ borderColor: 'var(--line)' }}>
          {orgs.length ? orgs.map((o) => <option key={o.id} value={o.id}>{o.name}</option>) : <option value="">No organizations available yet</option>}
        </select>
        {!orgs.length && <p className="text-caption mt-2" style={{ color: 'var(--ink-soft)' }}>Account creation is unavailable until a care organization is connected.</p>}
      </div>
      <div>
        <label htmlFor="register-email" className="field-label block mb-1.5" style={{ color: 'var(--ink-soft)' }}>Email</label>
        <input id="register-email" type="email" required placeholder="you@example.com" value={fields.email} onChange={set('email')} className="field w-full border rounded-lg px-3.5 py-2.5 text-sm" style={{ borderColor: 'var(--line)' }} />
      </div>
      <div>
        <label htmlFor="register-password" className="field-label block mb-1.5" style={{ color: 'var(--ink-soft)' }}>Password</label>
        <input id="register-password" type="password" required minLength={8} placeholder="At least 8 characters" value={fields.password} onChange={set('password')} className="field w-full border rounded-lg px-3.5 py-2.5 text-sm" style={{ borderColor: 'var(--line)' }} />
      </div>
      <button type="submit" disabled={submitting || !orgs.length} className="btn-primary label-tag w-full text-white py-3 rounded-full mt-2">
        {submitting ? 'Creating account…' : 'Create account'}
      </button>
    </form>
  );
}

// Ported from renderAuth() — existing login/register flow, reskinned.
export default function Auth({ onAuthenticated, onSkip, mode = 'patient' }) {
  const [tab, setTab] = useState('login');
  const [error, setError] = useState('');

  return (
    <main className="flex-1 w-full max-w-3xl mx-auto px-6 py-10">
      <div className="reveal max-w-sm mx-auto">
        <p className="label-tag mb-3" style={{ color: 'var(--accent)' }}>{mode === 'clinician' ? 'Clinical console' : 'Patient account'}</p>
        <h1 className="font-display text-subheading mb-6" style={{ color: 'var(--ink)' }}>Welcome back</h1>
        <div className="flex gap-1 p-1 rounded-full mb-7 text-[13px] font-medium" style={{ background: 'var(--line-soft)' }}>
          <button
            onClick={() => { setError(''); setTab('login'); }}
            className="flex-1 py-2 rounded-full transition-colors"
            style={{ background: tab === 'login' ? 'var(--paper-raised)' : 'transparent', color: tab === 'login' ? 'var(--ink)' : 'var(--ink-soft)' }}
          >
            Sign in
          </button>
          {mode !== 'clinician' && <button
            onClick={() => { setError(''); setTab('register'); }}
            className="flex-1 py-2 rounded-full transition-colors"
            style={{ background: tab === 'register' ? 'var(--paper-raised)' : 'transparent', color: tab === 'register' ? 'var(--ink)' : 'var(--ink-soft)' }}
          >
            Create account
          </button>}
        </div>

        {tab === 'login' ? (
          <LoginForm onError={setError} onSuccess={onAuthenticated} mode={mode} />
        ) : (
          <RegisterForm onError={setError} onSuccess={onAuthenticated} />
        )}

        {error && <p role="alert" className="text-sm mt-4" style={{ color: 'var(--critical)' }}>{error}</p>}

        <p className="text-[12px] mt-8 text-center" style={{ color: 'var(--ink-faint)' }}>
          Don't have prescriptions on file yet?{' '}
          <button onClick={onSkip} className="underline underline-link font-semibold" style={{ color: 'var(--primary)' }}>
            Try the quick check instead
          </button>
        </p>
      </div>
    </main>
  );
}
