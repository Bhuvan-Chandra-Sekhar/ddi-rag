export default function Header({ view, user, onNav, onSignOut }) {
  return (
    <header className="site-header">
      <div className="header-inner">
        <button onClick={() => onNav('home')} className="brand flex items-center gap-3" aria-label="MedTrust Connect home">
          <span className="brand-mark" aria-hidden="true" />
          <span className="text-[17px] tracking-tight whitespace-nowrap">MedTrust Connect</span>
        </button>
        <nav className="site-nav label-tag" aria-label="Main navigation">
          <button onClick={() => onNav('checker')} aria-current={view === 'checker' ? 'page' : undefined} style={{ color: view === 'checker' ? 'var(--ink)' : 'var(--ink-soft)' }}>Quick check</button>
          {user ? <><button onClick={() => onNav('dashboard')} style={{ color: 'var(--ink-soft)' }}>My prescriptions</button><button onClick={onSignOut} style={{ color: 'var(--ink-soft)' }}>Sign out ↗</button></> : <button onClick={() => onNav('auth')} style={{ color: 'var(--ink-soft)' }}>Sign in ↗</button>}
        </nav>
      </div>
    </header>
  );
}
