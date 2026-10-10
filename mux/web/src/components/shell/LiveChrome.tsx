'use client';

import React, { useEffect, useRef, useState } from 'react';
import { prefersReducedMotion } from './Motion';

// Live layer shared by every site screen: a scroll progress bar, the visitor's own "You" cursor,
// the page-wide spotlight tracker for cards, and the roaming teammate cursors.

// A "You" tag that trails the visitor's pointer, like their cursor in a shared room.
// Fine pointers only; the native cursor stays visible.
export function YouCursor() {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el || prefersReducedMotion() || !window.matchMedia('(pointer: fine)').matches) return;
    const pos = { x: -100, y: -100, tx: -100, ty: -100 };
    let frame = 0;
    let shown = false;

    const loop = () => {
      pos.x += (pos.tx - pos.x) * 0.2;
      pos.y += (pos.ty - pos.y) * 0.2;
      el.style.transform = `translate3d(${pos.x}px, ${pos.y}px, 0)`;
      frame = Math.abs(pos.tx - pos.x) + Math.abs(pos.ty - pos.y) > 0.3 ? requestAnimationFrame(loop) : 0;
    };
    const onMove = (e: PointerEvent) => {
      pos.tx = e.clientX + 16;
      pos.ty = e.clientY + 20;
      if (!shown) {
        pos.x = pos.tx;
        pos.y = pos.ty;
        shown = true;
      }
      // Fade out over interactive things so the tag never sits on top of what you're pointing at
      const target = e.target as Element | null;
      el.dataset.hidden = target?.closest('a, button, input, textarea, [role="tab"]') ? 'true' : 'false';
      if (!frame) frame = requestAnimationFrame(loop);
    };
    const onLeave = () => { el.dataset.hidden = 'true'; };

    window.addEventListener('pointermove', onMove, { passive: true });
    document.documentElement.addEventListener('pointerleave', onLeave);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener('pointermove', onMove);
      document.documentElement.removeEventListener('pointerleave', onLeave);
    };
  }, []);

  return (
    <div ref={ref} data-hidden="true" className="you-cursor pointer-events-none fixed left-0 top-0 z-[70] hidden md:block" aria-hidden="true">
      <span className="rounded-md bg-on-surface px-1.5 py-0.5 font-display text-[11px] font-semibold text-surface shadow-lg">You</span>
    </div>
  );
}

// Thin gradient bar at the very top that fills as the page scrolls
export function ScrollProgress() {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    let frame = 0;
    const onScroll = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const max = document.documentElement.scrollHeight - window.innerHeight;
        if (ref.current) ref.current.style.transform = `scaleX(${max > 0 ? window.scrollY / max : 0})`;
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
  return (
    <div className="pointer-events-none fixed inset-x-0 top-0 z-[60] h-[2px]" aria-hidden="true">
      <div ref={ref} className="h-full origin-left bg-gradient-to-r from-primary via-secondary to-[#a371f7] shadow-[0_0_12px_rgba(6,182,212,0.8)]" style={{ transform: 'scaleX(0)' }} />
    </div>
  );
}

// One page-wide listener that feeds --mx / --my to whichever .spotlight card is under the pointer,
// so every card gets the cursor-following glow without its own handler
export function SpotlightTracker() {
  useEffect(() => {
    if (!window.matchMedia('(pointer: fine)').matches) return;
    let frame = 0;
    let last: PointerEvent | null = null;
    const apply = () => {
      frame = 0;
      const e = last;
      const card = (e?.target as Element | null)?.closest<HTMLElement>('.spotlight');
      if (!e || !card) return;
      const r = card.getBoundingClientRect();
      card.style.setProperty('--mx', `${e.clientX - r.left}px`);
      card.style.setProperty('--my', `${e.clientY - r.top}px`);
    };
    const onMove = (e: PointerEvent) => {
      last = e;
      if (!frame) frame = requestAnimationFrame(apply);
    };
    window.addEventListener('pointermove', onMove, { passive: true });
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener('pointermove', onMove);
    };
  }, []);
  return null;
}

export const PRESENCE = [
  { name: 'Dan', color: '#3b82f6', start: [72, 6] },
  { name: 'Priya', color: '#06b6d4', start: [86, 52] },
  { name: 'Maya', color: '#a371f7', start: [60, 70] },
] as const;

const DEFAULT_CHATTER = ['make the CTA pop', 'vote: cyan', 'ship it', 'rewind to v4?', 'love this', 'add a login page', 'merged ✓'];

interface RoomCursorsProps {
  // Roam the whole stage instead of keeping to the right of a left-aligned headline
  spread?: boolean;
  chatter?: string[];
  className?: string;
}

// Teammate cursors that glide between points on the stage with spring physics and
// occasionally "say" something. Pure transforms on refs; React only renders the bubbles.
export function RoomCursors({ spread = false, chatter = DEFAULT_CHATTER, className = 'z-20' }: RoomCursorsProps) {
  const stageRef = useRef<HTMLDivElement>(null);
  const cursorRefs = useRef<(HTMLDivElement | null)[]>([]);
  const [bubbles, setBubbles] = useState<(string | null)[]>(PRESENCE.map(() => null));

  useEffect(() => {
    const stage = stageRef.current;
    if (!stage || prefersReducedMotion()) return;

    const bodies = PRESENCE.map(p => ({
      x: p.start[0] as number, y: p.start[1] as number, vx: 0, vy: 0, tx: p.start[0] as number, ty: p.start[1] as number, next: performance.now() + 600 + Math.random() * 1800,
    }));
    const bubbleTimers: ReturnType<typeof setTimeout>[] = [];
    let frame = 0;
    let running = false;
    let last = performance.now();

    const pickTarget = (i: number, now: number) => {
      const b = bodies[i];
      // Keep to the right of the headline on desktop; on phones, stay in the strip above the CTAs' right edge
      const wide = stage.clientWidth > 900;
      if (spread) {
        b.tx = 4 + Math.random() * 88;
        b.ty = 6 + Math.random() * 84;
      } else {
        b.tx = wide ? 50 + Math.random() * 46 : 55 + Math.random() * 30;
        b.ty = wide ? 6 + Math.random() * 86 : 2 + Math.random() * 12;
      }
      b.next = now + 2200 + Math.random() * 2600;
      if (Math.random() < 0.35) {
        const line = chatter[Math.floor(Math.random() * chatter.length)];
        bubbleTimers.push(setTimeout(() => {
          setBubbles(prev => prev.map((v, k) => (k === i ? line : v)));
          bubbleTimers.push(setTimeout(() => setBubbles(prev => prev.map((v, k) => (k === i ? null : v))), 2200));
        }, 900));
      }
    };

    const step = (now: number) => {
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      const w = stage.clientWidth;
      const h = stage.clientHeight;
      bodies.forEach((b, i) => {
        if (now > b.next) pickTarget(i, now);
        // Critically-damped-ish spring toward the target, in percent space
        const k = 9;
        const damp = 5.2;
        b.vx += ((b.tx - b.x) * k - b.vx * damp) * dt;
        b.vy += ((b.ty - b.y) * k - b.vy * damp) * dt;
        b.x += b.vx * dt;
        b.y += b.vy * dt;
        const el = cursorRefs.current[i];
        // left/top hold the start position, so the transform is the offset from it
        const [sx, sy] = PRESENCE[i].start;
        if (el) el.style.transform = `translate3d(${((b.x - sx) / 100) * w}px, ${((b.y - sy) / 100) * h}px, 0) rotate(${Math.max(-12, Math.min(12, b.vx * 0.6))}deg)`;
      });
      frame = requestAnimationFrame(step);
    };

    const start = () => {
      if (running) return;
      running = true;
      last = performance.now();
      frame = requestAnimationFrame(step);
    };
    const stop = () => {
      running = false;
      cancelAnimationFrame(frame);
    };
    const visibility = new IntersectionObserver(([entry]) => (entry.isIntersecting && !document.hidden ? start() : stop()));
    visibility.observe(stage);
    const onVis = () => (document.hidden ? stop() : start());
    document.addEventListener('visibilitychange', onVis);

    return () => {
      stop();
      visibility.disconnect();
      document.removeEventListener('visibilitychange', onVis);
      bubbleTimers.forEach(clearTimeout);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [spread]);

  return (
    <div ref={stageRef} className={`pointer-events-none absolute inset-0 ${className}`} aria-hidden="true">
      {PRESENCE.map((p, i) => (
        <div
          key={p.name}
          ref={el => { cursorRefs.current[i] = el; }}
          className={`room-cursor absolute will-change-transform ${i === 2 ? 'hidden sm:flex' : 'flex'}`}
          style={{ left: `${p.start[0]}%`, top: `${p.start[1]}%`, ['--c' as string]: p.color }}
        >
          <svg width="18" height="20" viewBox="0 0 18 20" className="drop-shadow-[0_2px_6px_rgba(0,0,0,0.5)]">
            <path d="M1 1l15 7.5-6.6 1.8L6.6 18z" fill={p.color} stroke="white" strokeWidth="1.4" strokeLinejoin="round" />
          </svg>
          <div className="ml-3 -mt-0.5 flex flex-col items-start gap-1">
            <span className="rounded-md px-1.5 py-0.5 font-display text-[11px] font-semibold text-white shadow-lg" style={{ background: p.color }}>
              {p.name}
            </span>
            {bubbles[i] && (
              <span
                key={bubbles[i]}
                className="bubble-in hidden whitespace-nowrap sm:inline rounded-xl rounded-tl-sm border border-white/10 bg-surface-container/95 px-2.5 py-1 font-display text-xs text-on-surface shadow-xl backdrop-blur"
              >
                {bubbles[i]}
              </span>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
