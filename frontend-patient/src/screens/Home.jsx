import { useEffect, useRef } from 'react';
import treeImage from '../assets/cicada-tree.png';

function LivingTree() {
  return <div className="living-tree" aria-hidden="true">
    <img className="living-tree-base" src={treeImage} alt="" />
    <img className="living-tree-crown" src={treeImage} alt="" />
    <svg className="tree-tendrils" viewBox="0 0 700 700" preserveAspectRatio="none">
      <path d="M291 370 C287 438 300 478 287 517 C274 542 271 498 266 470" />
      <path d="M394 352 C401 428 387 505 402 555 C417 598 420 530 425 487" />
      <path d="M474 388 C471 446 485 487 474 524 C461 552 456 510 454 482" />
    </svg>
    {Array.from({ length: 18 }, (_, i) => <i className="tree-leaf" style={{ '--i': i }} key={i} />)}
  </div>;
}

function Wings({ onNav }) {
  const options = [
    { label: 'Quick check', detail: 'Check medication interactions without an account', action: () => onNav('checker') },
    { label: 'Patient portal', detail: 'Sign in to prescriptions and care updates', action: () => onNav('auth') },
    { label: 'Clinic portal', detail: 'Sign in to the clinical console', action: () => onNav('clinician') },
  ];
  return <section className="journey-wings" id="choose-path" aria-labelledby="journey-choice-title">
    <p className="journey-kicker">THE NEXT CHAPTER</p>
    <h2 id="journey-choice-title">Choose your path</h2>
    <div className="butterfly-map">
      <div className="butterfly-options">
        {options.map((option, i) => <button key={option.label} className={`butterfly-option option-${i + 1}`} onClick={option.action}>
          <span className="option-number">0{i + 1}</span><span className="option-name">{option.label} ↗</span><span className="option-detail">{option.detail}</span>
        </button>)}
      </div>
    </div>
  </section>;
}

export default function Home({ onNav }) {
  const pageRef = useRef(null);
  useEffect(() => {
    const page = pageRef.current;
    if (!page) return;
    let frame = 0;
    const smooth = (start, end, value) => {
      const t = Math.min(1, Math.max(0, (value - start) / (end - start)));
      return t * t * (3 - 2 * t);
    };
    const update = () => {
      frame = 0;
      const top = page.getBoundingClientRect().top + window.scrollY;
      const progress = Math.max(0, (window.scrollY - top) / window.innerHeight);
      const set = (name, value) => page.style.setProperty(name, value.toFixed(3));
      set('--tree-gone', smooth(1.55, 2.05, progress));
      set('--tree-grow', smooth(.3, 1.5, progress));
      set('--symbol-visible', smooth(1.65, 2.05, progress));
      set('--wings-visible', smooth(2.2, 2.55, progress));
      set('--intro-wings', 1 - smooth(.5, 1.3, progress));
      page.classList.toggle('choices-ready', progress >= 2.48);
    };
    const onScroll = () => { if (!frame) frame = requestAnimationFrame(update); };
    update();
    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll, { passive: true });
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener('scroll', onScroll);
      window.removeEventListener('resize', onScroll);
    };
  }, []);
  return <main ref={pageRef} className="home-page cicada-journey flex-1">
    <div className="journey-stage" aria-hidden="true">
      <svg className="hero-wings" viewBox="0 0 1000 520"><g fill="none" stroke="currentColor" strokeWidth="1"><path d="M500 310 C404 186 272 137 104 199 C3 236 7 352 103 393 C227 449 375 366 500 310Z M500 310 C596 186 728 137 896 199 C997 236 993 352 897 393 C773 449 625 366 500 310Z"/><path d="M500 310 C389 342 279 400 310 468 C342 522 445 443 500 310Z M500 310 C611 342 721 400 690 468 C658 522 555 443 500 310Z"/><path d="M500 310 C366 235 251 209 62 269 M500 310 C353 314 215 331 59 361 M500 310 C634 235 749 209 938 269 M500 310 C647 314 785 331 941 361"/></g></svg>
      <LivingTree />
      <svg className="stage-symbol" viewBox="0 0 1000 600"><path className="branch-trunk" d="M500 600 V330"/><path className="branch-arm" d="M500 330 L150 160"/><path className="branch-arm" d="M500 330 L500 60"/><path className="branch-arm" d="M500 330 L850 160"/><circle className="branch-node" cx="150" cy="160" r="10"/><circle className="branch-node" cx="500" cy="60" r="10"/><circle className="branch-node" cx="850" cy="160" r="10"/></svg>
      <svg className="stage-butterfly" viewBox="0 0 1000 520">
        <g className="flapping-wing wing-left" fill="none" stroke="currentColor" strokeWidth="1.1">
          <path d="M500 320 C445 224 289 109 126 150 C27 179 21 292 90 340 C175 403 331 367 500 320Z" />
          <path d="M500 320 C381 333 238 376 263 450 C292 516 445 443 500 320Z" />
          <path d="M500 320 C402 226 302 194 134 189 M500 320 C360 294 224 301 64 296" />
        </g>
        <g className="flapping-wing wing-right" fill="none" stroke="currentColor" strokeWidth="1.1">
          <path d="M500 320 C555 224 711 109 874 150 C973 179 979 292 910 340 C825 403 669 367 500 320Z" />
          <path d="M500 320 C619 333 762 376 737 450 C708 516 555 443 500 320Z" />
          <path d="M500 320 C598 226 698 194 866 189 M500 320 C640 294 776 301 936 296" />
        </g>
        <circle cx="500" cy="320" r="31" fill="#b5a1bb"/><text x="500" y="329" textAnchor="middle" fill="white" fontSize="25" fontFamily="Inter, sans-serif">M</text>
      </svg>
    </div>
    <section className="journey-hero" aria-labelledby="journey-title">
      <div className="journey-hero-copy"><h1 id="journey-title">Uncovering what's safe<br /><span>to take together.</span></h1></div>
      <a className="journey-scroll" href="#how-it-works">Scroll to explore ↓</a>
    </section>
    <section className="journey-story" id="how-it-works" aria-labelledby="journey-story-title">
      <div className="journey-story-copy"><p className="journey-kicker">ABOUT THE APPLICATION</p><h2 id="journey-story-title">Your medications.<br />Better understood.</h2><p>Check a new medicine against what you already take. See potential interactions and allergy conflicts, then bring clear questions to your care team.</p><a href="#journey-symbol">Continue exploring ↓</a></div>
    </section>
    <section className="journey-symbol" id="journey-symbol" aria-label="From questions to understanding" />
    <Wings onNav={onNav} />
  </main>;
}
