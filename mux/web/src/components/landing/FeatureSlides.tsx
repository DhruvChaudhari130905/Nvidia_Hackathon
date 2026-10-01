'use client';

import React, { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { ArrowRight, ChevronDown, ChevronLeft, ChevronRight } from 'lucide-react';
import { prefersReducedMotion } from '@/components/shell';
import { GitHubVisual, LiveSyncVisual, SandboxVisual, VotingVisual } from './FeatureVisuals';

// Pinned "sliding pages" feature showcase: while the section is pinned, scrolling down slides
// full-width feature pages horizontally. Falls back to stacked pages on small screens / reduced motion.

const SLIDES = [
  {
    eyebrow: 'Live Sync Engine',
    title: 'Everyone in the same file, at the same time.',
    body: 'Multi-cursor editing, the agent feed and room chat stay in lockstep for every person in the room. No refresh, no merge dance.',
    points: ['Sub-second sync across editors', 'See who is typing where', 'Agent edits stream in live'],
    link: 'Explore architecture',
    href: '/docs#rooms',
    glow: 'from-primary/25',
    Visual: LiveSyncVisual,
  },
  {
    eyebrow: 'AI Copilot & Voting',
    title: 'When the room disagrees, the room decides.',
    body: 'The coordinator spots clashing requests, opens a vote, and keeps the coder busy on everything else until it closes.',
    points: ['Domain owners count 2×', 'Owner override when you need it', 'Decisions pinned to the room log'],
    link: 'View agent workflows',
    href: '/docs#conflicts',
    glow: 'from-[#f85149]/20',
    Visual: VotingVisual,
  },
  {
    eyebrow: 'Instant Sandboxes',
    title: 'From prompt to running preview in seconds.',
    body: 'Every room boots its own sandbox. Installs, builds and the live preview happen while the conversation continues.',
    points: ['Node, React and Python runtimes', 'Builds on every task boundary', 'Checkpoints you can rewind'],
    link: 'Check runtimes',
    href: '/sandbox',
    glow: 'from-secondary/25',
    Visual: SandboxVisual,
  },
  {
    eyebrow: 'GitHub Export',
    title: 'Ship it. One click to a real repository.',
    body: 'Export the room to GitHub with the work intact, so the prototype your team built together becomes the start of the real thing.',
    points: ['New public or private repo', 'Commits from the room history', 'Checks run before you merge'],
    link: 'Read integration guide',
    href: '/docs#export',
    glow: 'from-[#a371f7]/25',
    Visual: GitHubVisual,
  },
];

const N = SLIDES.length;

export function FeatureSlides() {
  const sectionRef = useRef<HTMLElement>(null);
  const [pinned, setPinned] = useState(false); // horizontal mode (desktop, motion allowed)
  const [position, setPosition] = useState(0); // 0..N-1, fractional while sliding

  useEffect(() => {
    const mq = window.matchMedia('(min-width: 768px)');
    const update = () => setPinned(mq.matches && !prefersReducedMotion());
    update();
    mq.addEventListener('change', update);
    return () => mq.removeEventListener('change', update);
  }, []);

  useEffect(() => {
    if (!pinned) return;
    let frame = 0;
    const onScroll = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const el = sectionRef.current;
        if (!el) return;
        const travel = el.offsetHeight - window.innerHeight;
        const p = Math.min(1, Math.max(0, -el.getBoundingClientRect().top / travel));
        setPosition(p * (N - 1));
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
  }, [pinned]);

  const active = Math.round(position);

  const goTo = (i: number) => {
    const el = sectionRef.current;
    if (!el) return;
    const target = Math.max(0, Math.min(N - 1, i));
    if (!pinned) {
      document.getElementById(`feature-${target}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      return;
    }
    const travel = el.offsetHeight - window.innerHeight;
    const top = el.getBoundingClientRect().top + window.scrollY + (target / (N - 1)) * travel;
    window.scrollTo({ top, behavior: 'smooth' });
  };

  const nav = (
    <div className="flex items-center gap-space-md">
      <div className="flex flex-1 gap-1 overflow-x-auto" role="tablist" aria-label="Features">
        {SLIDES.map((s, i) => (
          <button
            key={s.eyebrow}
            type="button"
            role="tab"
            aria-selected={active === i}
            onClick={() => goTo(i)}
            className={`group relative flex-none rounded-full px-space-md py-space-sm font-code text-code-sm transition-colors ${
              active === i ? 'text-on-surface' : 'text-outline hover:text-on-surface'
            }`}
          >
            <span className={`absolute inset-0 rounded-full bg-white/[0.06] transition-all duration-300 ${active === i ? 'scale-100 opacity-100' : 'scale-90 opacity-0'}`} />
            <span className="relative">
              <span className={active === i ? 'text-secondary' : ''}>0{i + 1}</span> {s.eyebrow}
            </span>
          </button>
        ))}
      </div>
      <div className="hidden items-center gap-1 md:flex">
        <button type="button" onClick={() => goTo(active - 1)} disabled={active === 0} className="grid h-9 w-9 place-items-center rounded-full text-on-surface-variant transition-all hover:bg-white/10 hover:text-on-surface disabled:opacity-30" aria-label="Previous feature">
          <ChevronLeft className="h-5 w-5" />
        </button>
        <button type="button" onClick={() => goTo(active + 1)} disabled={active === N - 1} className="grid h-9 w-9 place-items-center rounded-full text-on-surface-variant transition-all hover:bg-white/10 hover:text-on-surface disabled:opacity-30" aria-label="Next feature">
          <ChevronRight className="h-5 w-5" />
        </button>
      </div>
    </div>
  );

  const renderSlide = (s: (typeof SLIDES)[number], i: number) => {
    // Distance from the centered page drives the parallax on the text and the demo
    const offset = pinned ? i - position : 0;
    const dist = Math.min(1, Math.abs(offset));
    const Visual = s.Visual;
    return (
      <div
        key={s.eyebrow}
        id={`feature-${i}`}
        className={`relative flex items-center ${pinned ? 'h-full flex-none' : 'min-h-[80vh] py-20'}`}
        style={pinned ? { width: `${100 / N}%` } : undefined}
        aria-hidden={pinned && active !== i ? true : undefined}
      >
        <div className={`pointer-events-none absolute left-1/2 top-1/2 h-[70%] w-[60%] -translate-x-1/2 -translate-y-1/2 rounded-full bg-gradient-to-br ${s.glow} to-transparent blur-3xl`} style={{ opacity: 1 - dist * 0.8 }} />
        <div className="relative mx-auto grid w-full max-w-6xl grid-cols-1 items-center gap-12 px-gutter md:grid-cols-2 md:px-space-xl">
          <div style={pinned ? { transform: `translateX(${offset * -60}px)`, opacity: 1 - dist * 0.7 } : undefined}>
            <div className="mb-space-md flex items-baseline gap-space-md">
              <span className="font-headline text-6xl font-bold text-transparent [-webkit-text-stroke:1px_rgba(139,148,158,0.45)] md:text-7xl">0{i + 1}</span>
              <span className="font-code text-label-md uppercase tracking-[0.2em] text-secondary">{s.eyebrow}</span>
            </div>
            <h3 className="mb-space-md font-headline text-3xl font-bold leading-tight tracking-tight text-on-surface md:text-4xl">{s.title}</h3>
            <p className="mb-space-lg max-w-md text-body-lg text-on-surface-variant">{s.body}</p>
            <ul className="mb-space-xl space-y-space-sm">
              {s.points.map((p, k) => (
                <li
                  key={p}
                  className="flex items-center gap-space-sm text-body-md text-on-surface transition-all duration-500"
                  style={pinned ? { transitionDelay: `${k * 80}ms`, opacity: active === i ? 1 : 0, transform: active === i ? 'none' : 'translateX(-12px)' } : undefined}
                >
                  <span className="h-1.5 w-1.5 rounded-full bg-gradient-to-r from-primary to-secondary" />
                  {p}
                </li>
              ))}
            </ul>
            <Link href={s.href} className="group inline-flex items-center gap-space-sm font-code text-code-md text-primary">
              <span className="border-b border-primary/30 pb-0.5 transition-colors group-hover:border-primary">{s.link}</span>
              <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" />
            </Link>
          </div>
          <div
            className="flex justify-center"
            style={pinned ? { transform: `translateX(${offset * 120}px) scale(${1 - dist * 0.12}) rotate(${offset * 2}deg)`, opacity: 1 - dist * 0.6 } : undefined}
          >
            <Visual active={pinned ? active === i : true} />
          </div>
        </div>
      </div>
    );
  };

  if (!pinned) {
    return (
      <section ref={sectionRef} className="relative">
        <div className="sticky top-16 z-20 border-b border-white/5 bg-surface/80 px-gutter py-space-sm backdrop-blur-xl">{nav}</div>
        {SLIDES.map(renderSlide)}
      </section>
    );
  }

  return (
    <section ref={sectionRef} className="relative" style={{ height: `${N * 100}vh` }}>
      <div className="sticky top-0 flex h-screen flex-col overflow-hidden pt-16">
        <div className="relative z-10 mx-auto w-full max-w-6xl px-space-xl pt-space-lg">
          {nav}
          <div className="mt-space-sm h-px w-full bg-white/5">
            <div className="h-full origin-left bg-gradient-to-r from-primary to-secondary shadow-[0_0_10px_rgba(6,182,212,0.7)]" style={{ transform: `scaleX(${position / (N - 1)})` }} />
          </div>
        </div>
        <div className="relative flex-1">
          <div
            className="absolute inset-y-0 left-0 flex will-change-transform"
            style={{ width: `${N * 100}%`, transform: `translateX(-${(position / N) * 100}%)` }}
          >
            {SLIDES.map(renderSlide)}
          </div>
        </div>
        <div
          className="pointer-events-none absolute bottom-6 left-1/2 flex -translate-x-1/2 flex-col items-center gap-1 font-code text-code-sm text-outline transition-opacity duration-500"
          style={{ opacity: position < 0.15 ? 1 : 0 }}
        >
          keep scrolling
          <ChevronDown className="h-4 w-4 animate-bounce" />
        </div>
      </div>
    </section>
  );
}
