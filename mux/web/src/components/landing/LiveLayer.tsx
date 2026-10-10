'use client';

import React, { useEffect, useRef, useState } from 'react';
import { prefersReducedMotion, useInView } from '@/components/shell';

// Live effects for the landing page: a scroll-driven 3D tilt for the room preview and a strip of
// ticking stats. (The scroll bar and "You" cursor live in the shell, on every screen.)

// Lays its child back in 3D and stands it up as it scrolls into view; a glare follows the pointer
export function TiltOnScroll({ children }: { children: React.ReactNode }) {
  const outer = useRef<HTMLDivElement>(null);
  const inner = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (prefersReducedMotion()) return;
    let frame = 0;
    const onScroll = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const el = outer.current;
        const card = inner.current;
        if (!el || !card) return;
        const r = el.getBoundingClientRect();
        const vh = window.innerHeight;
        // 0 while the top sits at the bottom of the viewport, 1 once it reaches 25% from the top
        const p = Math.min(1, Math.max(0, (vh - r.top) / (vh * 0.75)));
        const e = 1 - Math.pow(1 - p, 3);
        card.style.transform = `rotateX(${(1 - e) * 24}deg) scale(${0.9 + e * 0.1}) translateY(${(1 - e) * 40}px)`;
      });
    };
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener('scroll', onScroll);
      window.removeEventListener('resize', onScroll);
    };
  }, []);

  const onMove = (e: React.MouseEvent<HTMLDivElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    e.currentTarget.style.setProperty('--gx', `${((e.clientX - r.left) / r.width) * 100}%`);
    e.currentTarget.style.setProperty('--gy', `${((e.clientY - r.top) / r.height) * 100}%`);
  };

  return (
    <div ref={outer} className="tilt-stage w-full">
      <div ref={inner} onMouseMove={onMove} className="tilt-card relative w-full will-change-transform">
        {children}
        <div className="tilt-glare pointer-events-none absolute inset-0 rounded-2xl" aria-hidden="true" />
      </div>
    </div>
  );
}

// Strip of numbers that keep moving while you watch, plus a live latency sparkline
const SPARK_POINTS = 28;

function useLiveNumber(initial: number, every: number, step: (n: number) => number, enabled: boolean) {
  const [value, setValue] = useState(initial);
  const [bump, setBump] = useState(0);
  useEffect(() => {
    if (!enabled || prefersReducedMotion()) return;
    let timer: ReturnType<typeof setTimeout>;
    const tick = () => {
      setValue(step);
      setBump(b => b + 1);
      timer = setTimeout(tick, every * (0.6 + Math.random() * 0.8));
    };
    timer = setTimeout(tick, every);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, every]);
  return [value, bump] as const;
}

export function LiveStats() {
  const [ref, inView] = useInView<HTMLDivElement>();
  const [builds, buildsBump] = useLiveNumber(18204, 1400, n => n + 1 + Math.floor(Math.random() * 3), inView);
  const [rooms, roomsBump] = useLiveNumber(1284, 2100, n => Math.max(1200, n + Math.round((Math.random() - 0.4) * 6)), inView);
  const [votes, votesBump] = useLiveNumber(342, 3200, n => n + 1, inView);
  const [latency, setLatency] = useState<number[]>(() => Array.from({ length: SPARK_POINTS }, (_, i) => 190 + Math.round(Math.sin(i / 2) * 14)));

  useEffect(() => {
    if (!inView || prefersReducedMotion()) return;
    const id = setInterval(() => {
      setLatency(prev => {
        const last = prev[prev.length - 1];
        const next = Math.round(Math.min(240, Math.max(160, last + (Math.random() - 0.5) * 22)));
        return [...prev.slice(1), next];
      });
    }, 700);
    return () => clearInterval(id);
  }, [inView]);

  const min = 150;
  const max = 250;
  const path = latency
    .map((v, i) => `${i === 0 ? 'M' : 'L'}${(i / (SPARK_POINTS - 1)) * 100},${30 - ((v - min) / (max - min)) * 30}`)
    .join(' ');
  const now = latency[latency.length - 1];

  const stats = [
    { label: 'builds passed today', value: builds.toLocaleString('en-US'), bump: buildsBump, color: '#3b82f6' },
    { label: 'rooms open right now', value: rooms.toLocaleString('en-US'), bump: roomsBump, color: '#06b6d4' },
    { label: 'votes settled this hour', value: String(votes), bump: votesBump, color: '#a371f7' },
  ];

  return (
    <div ref={ref} className="mx-auto grid max-w-6xl grid-cols-2 gap-px overflow-hidden rounded-2xl border border-white/10 bg-white/10 md:grid-cols-4">
      {stats.map(s => (
        <div key={s.label} className="group relative bg-surface-container-lowest px-space-lg py-space-xl">
          <span key={s.bump} className="stat-flash pointer-events-none absolute inset-0" style={{ ['--c' as string]: s.color }} aria-hidden="true" />
          <p className="relative font-display text-3xl font-bold tabular-nums tracking-tight text-on-surface md:text-4xl">
            <span key={s.bump} className="stat-roll inline-block">{s.value}</span>
          </p>
          <p className="relative mt-1 flex items-center gap-2 font-display text-body-md text-on-surface-variant">
            <span className="h-1.5 w-1.5 rounded-full" style={{ background: s.color }} />
            {s.label}
          </p>
        </div>
      ))}
      <div className="relative bg-surface-container-lowest px-space-lg py-space-xl">
        <p className="font-display text-3xl font-bold tabular-nums tracking-tight text-on-surface md:text-4xl">
          {now}
          <span className="ml-1 text-lg font-medium text-on-surface-variant">ms</span>
        </p>
        <p className="mt-1 flex items-center gap-2 font-display text-body-md text-on-surface-variant">
          <span className="h-1.5 w-1.5 rounded-full bg-[#3fb950]" />
          sync latency, live
        </p>
        <svg viewBox="0 0 100 30" preserveAspectRatio="none" className="mt-space-sm h-8 w-full overflow-visible" aria-hidden="true">
          <defs>
            <linearGradient id="spark-fill" x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stopColor="#3fb950" stopOpacity="0.35" />
              <stop offset="100%" stopColor="#3fb950" stopOpacity="0" />
            </linearGradient>
          </defs>
          <path d={`${path} L100,30 L0,30 Z`} fill="url(#spark-fill)" />
          <path d={path} fill="none" stroke="#3fb950" strokeWidth="1.5" vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
        </svg>
      </div>
    </div>
  );
}
