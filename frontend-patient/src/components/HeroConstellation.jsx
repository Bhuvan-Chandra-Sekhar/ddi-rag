import { useEffect, useRef } from 'react';

// Same particle system as the vanilla version — the one real difference:
// cleanup is now a normal useEffect return function instead of a manual
// "is my canvas still in the DOM?" check on every frame. That check
// existed only because the old app had no lifecycle hooks to hang a
// teardown on; React gives us that for free.
const PALETTE = [
  '#8052ff', '#8052ff', '#9c78ff',
  '#ffb829', '#ffb829',
  '#15846e', '#3ecf8e',
  '#ff5c7a', '#ff8a3d', '#6fc8ff', '#b892ff', '#ffffff',
];

function shapeRadius(angle) {
  return 1
    + 0.16 * Math.sin(angle * 3 + 1.3)
    + 0.10 * Math.sin(angle * 5 - 0.7)
    + 0.07 * Math.sin(angle * 8 + 2.1);
}

function seedParticles() {
  const particles = [];
  const dense = 900;
  const ambient = 260;
  for (let i = 0; i < dense; i++) {
    const angle = Math.random() * Math.PI * 2;
    const r = (0.15 + 0.85 * Math.pow(Math.random(), 0.55)) * shapeRadius(angle);
    particles.push({
      angle, baseR: r,
      size: 1 + Math.random() * 2.4,
      rot: Math.random() * Math.PI * 2,
      rotSpeed: (Math.random() - 0.5) * 0.4,
      phase: Math.random() * Math.PI * 2,
      speed: 0.15 + Math.random() * 0.25,
      drift: 0.015 + Math.random() * 0.02,
      color: PALETTE[(Math.random() * PALETTE.length) | 0],
      alpha: 0.55 + Math.random() * 0.45,
    });
  }
  for (let i = 0; i < ambient; i++) {
    const angle = Math.random() * Math.PI * 2;
    const r = (1.05 + Math.random() * 0.9) * shapeRadius(angle);
    particles.push({
      angle, baseR: r,
      size: 0.8 + Math.random() * 1.6,
      rot: Math.random() * Math.PI * 2,
      rotSpeed: (Math.random() - 0.5) * 0.2,
      phase: Math.random() * Math.PI * 2,
      speed: 0.08 + Math.random() * 0.15,
      drift: 0.01 + Math.random() * 0.015,
      color: PALETTE[(Math.random() * PALETTE.length) | 0],
      alpha: 0.12 + Math.random() * 0.22,
    });
  }
  return particles;
}

function drawTriangle(ctx, cx, cy, size, rot, color, alpha) {
  ctx.save();
  ctx.translate(cx, cy);
  ctx.rotate(rot);
  ctx.beginPath();
  for (let i = 0; i < 3; i++) {
    const a = (Math.PI * 2 / 3) * i - Math.PI / 2;
    const x = Math.cos(a) * size, y = Math.sin(a) * size;
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  }
  ctx.closePath();
  ctx.globalAlpha = alpha;
  ctx.strokeStyle = color;
  ctx.lineWidth = 1;
  ctx.stroke();
  ctx.restore();
}

export default function HeroConstellation() {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    let particles = seedParticles();
    let w = 0, h = 0, dpr = 1;
    let raf = null;
    const start = performance.now();

    function resize() {
      const rect = canvas.getBoundingClientRect();
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      w = rect.width; h = rect.height;
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }

    function frame(now) {
      const t = (now - start) / 1000;
      ctx.clearRect(0, 0, w, h);
      const cx = w / 2, cy = h / 2;
      const maxR = Math.min(w, h) / 2;
      for (const p of particles) {
        const wobble = Math.sin(t * p.speed + p.phase) * p.drift;
        const r = (p.baseR + wobble) * maxR;
        const a = p.angle + t * 0.02 * (p.baseR < 1 ? 1 : 0.4);
        const x = cx + Math.cos(a) * r;
        const y = cy + Math.sin(a) * r * 0.92;
        const rot = p.rot + t * p.rotSpeed;
        drawTriangle(ctx, x, y, p.size, rot, p.color, p.alpha);
      }
      raf = requestAnimationFrame(frame);
    }

    resize();
    if (reduceMotion) {
      frame(start);
    } else {
      raf = requestAnimationFrame(frame);
    }

    window.addEventListener('resize', resize, { passive: true });

    // The whole payoff of doing this in React: teardown is guaranteed by
    // the framework when this component unmounts (navigating away from
    // Home), not by a hand-rolled "am I still attached?" poll every frame.
    return () => {
      if (raf) cancelAnimationFrame(raf);
      window.removeEventListener('resize', resize);
    };
  }, []);

  return (
    <div className="hero-visual">
      <canvas id="hero-canvas" ref={canvasRef} aria-hidden="true" />
    </div>
  );
}
