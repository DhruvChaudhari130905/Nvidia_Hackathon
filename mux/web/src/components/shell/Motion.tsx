'use client';

import React, { useEffect, useRef, useState } from 'react';

// Small motion primitives shared by every screen. All of them respect prefers-reduced-motion
// (via CSS in globals.css, or by skipping straight to the end state).

export function prefersReducedMotion(): boolean {
  return typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

// True once the element has scrolled into view (never flips back)
export function useInView<T extends Element>(rootMargin = '0px 0px -10% 0px') {
  const ref = useRef<T>(null);
  const [inView, setInView] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (typeof IntersectionObserver === 'undefined') {
      setInView(true);
      return;
    }
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setInView(true);
          observer.disconnect();
        }
      },
      { rootMargin },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [rootMargin]);

  return [ref, inView] as const;
}

interface RevealProps {
  children: React.ReactNode;
  className?: string;
  delay?: number; // ms
}

// Fades and lifts its children in the first time they scroll into view
export function Reveal({ children, className = '', delay = 0 }: RevealProps) {
  const [ref, inView] = useInView<HTMLDivElement>();
  return (
    <div ref={ref} className={`reveal ${inView ? 'in' : ''} ${className}`} style={{ transitionDelay: `${delay}ms` }}>
      {children}
    </div>
  );
}

interface CountUpProps {
  value: string | number; // e.g. "1.2M+", "99.9%", 38
  duration?: number; // ms
  className?: string;
}

// Counts from zero to the number inside `value` when it scrolls into view, keeping prefix/suffix
export function CountUp({ value, duration = 1400, className = '' }: CountUpProps) {
  const text = String(value);
  const match = text.match(/^([^\d]*)([\d.]+)(.*)$/);
  const [ref, inView] = useInView<HTMLSpanElement>();
  const [shown, setShown] = useState(match ? `${match[1]}0${match[3]}` : text);

  useEffect(() => {
    if (!match || !inView) return;
    const [, prefix, num, suffix] = match;
    const target = parseFloat(num);
    const decimals = num.includes('.') ? num.split('.')[1].length : 0;
    if (prefersReducedMotion()) {
      setShown(text);
      return;
    }
    let frame = 0;
    const start = performance.now();
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - t, 3);
      setShown(`${prefix}${(target * eased).toFixed(decimals)}${suffix}`);
      if (t < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inView, text, duration]);

  return (
    <span ref={ref} className={`tabular-nums ${className}`}>
      {shown}
    </span>
  );
}

type SpotlightProps = React.HTMLAttributes<HTMLDivElement> & { children: React.ReactNode };

// Card wrapper whose glow and border highlight follow the cursor
export function Spotlight({ children, className = '', ...rest }: SpotlightProps) {
  const handleMove = (e: React.MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    e.currentTarget.style.setProperty('--mx', `${e.clientX - rect.left}px`);
    e.currentTarget.style.setProperty('--my', `${e.clientY - rect.top}px`);
  };
  return (
    <div {...rest} onMouseMove={handleMove} className={`spotlight ${className}`}>
      {children}
    </div>
  );
}

// Re-renders every `ms` and returns the number of ticks since mount
export function useTicker(ms = 1000) {
  const [ticks, setTicks] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setTicks(t => t + 1), ms);
    return () => clearInterval(id);
  }, [ms]);
  return ticks;
}

export function formatClock(totalSeconds: number): string {
  const h = Math.floor(totalSeconds / 3600);
  const m = Math.floor((totalSeconds % 3600) / 60);
  const s = totalSeconds % 60;
  return [h, m, s].map(n => String(n).padStart(2, '0')).join(':');
}
