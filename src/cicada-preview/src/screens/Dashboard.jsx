import { useEffect, useState } from 'react';
import { api, getUser } from '../api.js';
import { STATE_META } from '../meta.js';

function CaseCard({ c, i }) {
  const meta = STATE_META[c.state] || STATE_META.draft;
  const comm = (c.communications && c.communications[0]) || null;
  const body = comm
    ? comm.explanation
    : `We're working through your ${c.medication} prescription. This isn't a guarantee of safety or risk — it means your pharmacist hasn't finished reviewing it yet.`;
  const dateStr = c.created_at ? new Date(c.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }) : '';

  return (
    <div className="card card-shadow rounded-2xl p-5 reveal" style={{ animationDelay: `${i * 70}ms` }}>
      <div className="flex items-start justify-between gap-3 mb-3">
        <div>
          <p className="field-label mb-1" style={{ color: 'var(--ink-faint)' }}>{dateStr}</p>
          <h3 className="font-display text-heading-xs">{c.medication}</h3>
        </div>
        <span className="field-label inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full whitespace-nowrap" style={{ background: meta.bg, color: meta.fg }}>
          <span className="w-1.5 h-1.5 rounded-full" style={{ background: meta.dot }} />{meta.label}
        </span>
      </div>
      {c.has_findings && (
        c.interaction_review === 'pending' ? (
          <div className="flex items-center gap-1.5 mb-2.5 field-label" style={{ color: 'var(--critical)' }}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" style={{ flexShrink: 0 }}>
              <path d="M12 3.5 L22 20.5 L2 20.5 Z" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
              <path d="M12 9.5 V14.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
              <circle cx="12" cy="17.3" r="1.1" fill="currentColor" />
            </svg>
            Pending clinical review — your pharmacist flagged something not yet fully reviewed
          </div>
        ) : (
          <div className="flex items-center gap-1.5 mb-2.5 field-label" style={{ color: 'var(--safe)' }}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" style={{ flexShrink: 0 }}>
              <circle cx="12" cy="12" r="9.5" stroke="currentColor" strokeWidth="2" />
              <path d="M7.5 12.5 L10.5 15.5 L16.5 9" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            Reviewed — your pharmacist has confirmed this
          </div>
        )
      )}
      <p className="text-[13.5px] leading-relaxed" style={{ color: 'var(--ink-soft)' }}>{body}</p>
    </div>
  );
}

// Ported from renderDashboard(). onSessionExpired is called on a 401 so
// App can bounce back to Auth, same as the original's token-expiry check.
export default function Dashboard({ onSessionExpired }) {
  const user = getUser();
  const [state, setState] = useState({ status: 'loading', cases: [] });

  useEffect(() => {
    api('/v1/my/cases')
      .then((data) => setState({ status: 'ok', cases: data.cases || [] }))
      .catch((err) => {
        if (err.message.includes('401') || err.message.toLowerCase().includes('token')) {
          onSessionExpired();
        } else {
          setState({ status: 'error', message: err.message });
        }
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <main className="flex-1 w-full max-w-3xl mx-auto px-6 py-10">
      <div className="reveal">
        <p className="label-tag mb-2" style={{ color: 'var(--accent)' }}>Your care team</p>
        <h1 className="font-display text-subheading mb-1" style={{ color: 'var(--ink)' }}>
          Hi, {(user && user.full_name) || 'there'}
        </h1>
        <p className="text-caption mb-6" style={{ color: 'var(--ink-soft)' }}>
          Your prescriptions, and where each one stands with your care team.
        </p>
        <div className="space-y-3">
          {state.status === 'loading' && <p className="text-caption" style={{ color: 'var(--ink-faint)' }}>Loading…</p>}
          {state.status === 'error' && <p className="text-sm" style={{ color: 'var(--critical)' }}>{state.message}</p>}
          {state.status === 'ok' && state.cases.length === 0 && (
            <div className="card rounded-2xl p-8 text-center reveal" style={{ borderStyle: 'dashed' }}>
              <p className="text-sm font-semibold">No prescriptions on file yet</p>
              <p className="text-caption mt-1.5 max-w-xs mx-auto" style={{ color: 'var(--ink-faint)' }}>
                Once your prescriber sends a prescription to your pharmacy, it'll show up here after
                review. In the meantime, try the quick check.
              </p>
            </div>
          )}
          {state.status === 'ok' && state.cases.map((c, i) => <CaseCard key={c.id} c={c} i={i} />)}
        </div>
      </div>
    </main>
  );
}
