import HeroConstellation from '../components/HeroConstellation.jsx';

const FEATURES = [
  { n: '01', title: 'No sign-up required', body: "Type your medications and go — nothing is saved to an account, so nothing about you has to be." },
  { n: '02', title: 'You bring the history', body: "Since nothing's stored between visits, just type any allergies or past reactions in each time — takes a few seconds." },
  { n: '03', title: 'Honest about limits', body: 'Unreviewed findings are always labeled as such — we never call something safe just because we don’t know.' },
];

// Ported from renderHome().
export default function Home({ user, onNav }) {
  return (
    <main className="flex-1 w-full max-w-3xl mx-auto px-6 py-10">
      <div className="reveal grid lg:grid-cols-[1fr_260px] gap-10 lg:gap-14 items-center mb-16">
        <div>
          <p className="label-tag mb-5" style={{ color: 'var(--accent)' }}>Medication safety, in plain language</p>
          <h1 className="font-display text-display mb-6" style={{ color: 'var(--ink)' }}>
            Know what's in
            <br />
            your medicine cabinet.
          </h1>
          <p className="text-prose max-w-lg mb-10" style={{ color: 'var(--ink-soft)' }}>
            Type in what you're taking — no account needed — and see what our FDA-grounded
            interaction checker finds. If you already have prescriptions on file with a care
            team, sign in to see what your pharmacist has reviewed.
          </p>
          <div className="flex flex-wrap gap-3">
            <button onClick={() => onNav('checker')} className="label-tag text-white px-6 py-3.5 rounded-full" style={{ background: 'var(--primary)' }}>
              Check my medications →
            </button>
            {user ? (
              <button onClick={() => onNav('dashboard')} className="label-tag px-6 py-3.5 rounded-full" style={{ color: 'var(--ink-soft)' }}>
                Go to my prescriptions
              </button>
            ) : (
              <button onClick={() => onNav('auth')} className="label-tag px-6 py-3.5 rounded-full" style={{ color: 'var(--ink-soft)' }}>
                Sign in instead
              </button>
            )}
          </div>
        </div>
        <HeroConstellation />
      </div>

      <div className="reveal">
        <div className="grid sm:grid-cols-3 gap-x-8 gap-y-10">
          {FEATURES.map((f) => (
            <div key={f.n}>
              <p className="font-display text-heading-2xs mb-3" style={{ color: 'var(--primary)' }}>{f.n}</p>
              <p className="label-tag mb-2" style={{ color: 'var(--ink)' }}>{f.title}</p>
              <p className="text-[14px] leading-relaxed" style={{ color: 'var(--ink-soft)', fontWeight: 300 }}>{f.body}</p>
            </div>
          ))}
        </div>
      </div>
    </main>
  );
}
