// Ported from shell()'s header — now driven by `view`/`user` props and a
// single onNav callback instead of a delegated click listener over
// data-nav attributes.
export default function Header({ view, user, onNav, onSignOut }) {
  const linkStyle = (active) => ({
    background: active ? 'var(--primary)' : 'transparent',
    color: active ? '#fff' : 'var(--ink-soft)',
  });

  return (
    <header className="border-b" style={{ borderColor: 'var(--line)', background: 'var(--paper)' }}>
      <div className="max-w-3xl mx-auto px-6 py-5 flex items-center justify-between">
        <button onClick={() => onNav('home')} className="flex items-center gap-2.5 group">
          <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: 'var(--primary)' }} />
          <span className="text-[15px]" style={{ color: 'var(--ink)', fontWeight: 400, letterSpacing: '-0.02em' }}>
            MedTrust Connect
          </span>
        </button>
        <nav className="flex items-center gap-1 label-tag">
          <button onClick={() => onNav('checker')} className="px-4 py-2 rounded-full transition-colors" style={linkStyle(view === 'checker')}>
            Quick check
          </button>
          {user ? (
            <>
              <button onClick={() => onNav('dashboard')} className="px-4 py-2 rounded-full transition-colors" style={linkStyle(view === 'dashboard')}>
                My prescriptions
              </button>
              <button onClick={onSignOut} className="ml-2 px-4 py-2 rounded-full border" style={{ borderColor: 'var(--line)', color: 'var(--ink-soft)' }}>
                Sign out
              </button>
            </>
          ) : (
            <button onClick={() => onNav('auth')} className="ml-2 px-5 py-2 rounded-full" style={{ background: 'var(--primary)', color: '#fff' }}>
              Sign in
            </button>
          )}
        </nav>
      </div>
    </header>
  );
}
