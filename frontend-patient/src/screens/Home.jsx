import HeroConstellation from '../components/HeroConstellation.jsx';

export default function Home({ user, onNav }) {
  return (
    <main className="home-page flex-1">
      <section className="home-hero">
        <div className="hero-copy">
          <p className="label-tag hero-enter" style={{ color: 'var(--accent)' }}>A little clarity. A better conversation.</p>
          <h1 className="hero-title hero-enter">Your medications.<br />Better understood.</h1>
          <p className="text-prose hero-enter hero-description">Check a new medication against what you already take. Understand potential interactions, and know what to discuss with your care team.</p>
          <div className="hero-actions hero-enter">
            <button onClick={() => onNav('checker')} className="btn-primary label-tag text-white px-6 py-4 rounded-full">Check my medications <span aria-hidden="true">↗</span></button>
            <span className="text-caption" style={{ color: 'var(--ink-soft)' }}>No account needed</span>
          </div>
        </div>
        <HeroConstellation />
        <a className="hero-scroll label-tag" href="#how-it-works">Explore the process <span aria-hidden="true">↓</span></a>
      </section>
      <section id="how-it-works" className="home-editorial">
        <div><p className="label-tag mb-6" style={{ color: 'var(--accent)' }}>From questions to context</p><h2 className="text-heading">Make sense of<br />what goes together.</h2></div>
        <div className="home-steps">
          {[
            ['01', 'Bring your medication list.', 'Add the medication you want to check, what you already take, and any known allergies.'],
            ['02', 'See what the evidence says.', 'Review potential interactions and allergy conflicts, with source details and clear labels for unreviewed findings.'],
            ['03', 'Take the next step together.', 'Use the results to start a conversation with your pharmacist. Missing evidence does not mean a combination is safe.'],
          ].map(([number, title, body]) => <article className="home-step" key={number}><span className="label-tag" style={{ color: 'var(--primary)' }}>{number}</span><div><h3 className="text-heading-2xs mb-3">{title}</h3><p className="text-prose" style={{ color: 'var(--ink-soft)' }}>{body}</p></div></article>)}
        </div>
      </section>
      <section className="home-editorial home-care">
        <h2 className="text-heading">Your care team.<br />Your next chapter.</h2>
        <div><p className="text-prose mb-6" style={{ color: 'var(--ink-soft)' }}>Already connected to a care team? See your prescriptions and the updates your pharmacist has reviewed.</p><button className="text-link label-tag" onClick={() => onNav(user ? 'dashboard' : 'auth')}>{user ? 'My prescriptions' : 'Sign in to your account'} <span aria-hidden="true">↗</span></button></div>
      </section>
    </main>
  );
}
