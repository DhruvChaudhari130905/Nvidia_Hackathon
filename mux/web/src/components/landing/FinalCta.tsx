'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { PlusCircle, ArrowRight } from 'lucide-react';
import { Magnetic, prefersReducedMotion, Reveal, ShaderBackground, useTicker } from '@/components/shell';

// Closing call-to-action: full-bleed live wallpaper, a headline that types out what you could
// build, a live "building right now" counter, and buttons that lean toward the cursor.

const IDEAS = ['a booking app', 'a SaaS dashboard', 'an online store', 'a habit tracker', 'your next idea'];
const BUILDERS = [
  { initials: 'PR', color: '#f0a3c4' },
  { initials: 'DA', color: '#9ad0f5' },
  { initials: 'MA', color: '#c7e59a' },
  { initials: 'SA', color: '#d6c7ff' },
  { initials: 'JK', color: '#f5d38a' },
  { initials: 'LT', color: '#8ee3ef' },
];

// Types each idea out, holds it, deletes it, moves to the next
function useTypedIdea() {
  const [text, setText] = useState(IDEAS[0]);
  useEffect(() => {
    if (prefersReducedMotion()) return;
    let idea = 0;
    let chars = IDEAS[0].length;
    // Start fully typed, hold, then delete and move on
    let deleting = true;
    let hold = 22;
    const id = setInterval(() => {
      if (hold > 0) { hold--; return; }
      if (deleting) {
        chars--;
        if (chars === 0) { deleting = false; idea = (idea + 1) % IDEAS.length; }
      } else {
        chars++;
        if (chars === IDEAS[idea].length) { deleting = true; hold = 22; }
      }
      setText(IDEAS[idea].slice(0, chars));
    }, 70);
    return () => clearInterval(id);
  }, []);
  return text;
}

export function FinalCta() {
  const idea = useTypedIdea();
  const tick = useTicker(2200);
  // Gently drifting "live" number so the counter feels alive
  const building = 1284 + Math.round(Math.sin(tick * 0.9) * 9 + tick * 1.5);
  const avatarShift = tick % BUILDERS.length;

  return (
    <section className="relative overflow-hidden px-gutter py-32 text-center md:px-16 lg:px-24">
      <ShaderBackground interactive className="absolute inset-0 z-0 opacity-70" />
      <div className="pointer-events-none absolute inset-0 z-0 bg-gradient-to-b from-surface via-transparent to-surface" />
      <div className="float-slow pointer-events-none absolute -left-24 top-1/3 z-0 h-80 w-80 rounded-full bg-primary/15 blur-3xl" />
      <div className="float-slower pointer-events-none absolute -right-24 bottom-10 z-0 h-96 w-96 rounded-full bg-secondary/10 blur-3xl" />

      <Reveal className="relative z-10 mx-auto max-w-4xl">
        <div className="mb-space-lg inline-flex items-center gap-space-md rounded-full border border-outline-variant/30 bg-surface-container/70 py-1.5 pl-1.5 pr-space-md backdrop-blur-md">
          <div className="flex -space-x-2">
            {Array.from({ length: 4 }, (_, k) => BUILDERS[(avatarShift + k) % BUILDERS.length]).map((b, k) => (
              <span
                key={b.initials}
                className="item-in grid h-7 w-7 place-items-center rounded-full border-2 border-surface-container font-code text-[9px] font-bold text-[#0d1117]"
                style={{ background: b.color, animationDelay: `${k * 60}ms` }}
              >
                {b.initials}
              </span>
            ))}
          </div>
          <span className="flex items-center gap-2 font-code text-code-sm text-on-surface-variant">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-primary opacity-75" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-primary" />
            </span>
            <span className="tabular-nums text-on-surface">{building.toLocaleString()}</span> people building right now
          </span>
        </div>

        <h2 className="mb-space-md font-display text-5xl font-bold leading-[0.98] tracking-[-0.04em] md:text-7xl">
          Ready to build
          <br />
          <span className="text-shimmer">{idea}</span>
          <span className="caret" />
          <br />
          together?
        </h2>
        <p className="mx-auto mb-space-xl max-w-xl text-body-lg text-on-surface-variant">
          Spin up your first build room in seconds. No credit card required. Invite your team and start coding together instantly.
        </p>

        <div className="flex flex-wrap items-center justify-center gap-space-md">
          <Magnetic>
            <Link
              href="/dashboard?new=1"
              className="btn-shine flex items-center gap-space-sm rounded-full bg-primary px-space-xl py-space-md text-label-md font-bold text-on-primary shadow-[0_10px_40px_-10px_rgba(59,130,246,0.8)] transition-shadow hover:shadow-[0_0_40px_rgba(59,130,246,0.7)]"
            >
              <PlusCircle className="h-[18px] w-[18px]" />
              Create Build Room Now
            </Link>
          </Magnetic>
          <Magnetic>
            <Link
              href="/pricing#contact"
              className="group flex items-center gap-space-sm rounded-full border border-white/15 bg-white/[0.04] px-space-xl py-space-md text-label-md font-medium text-on-surface backdrop-blur-md transition-colors hover:border-primary/50 hover:bg-white/[0.08]"
            >
              Contact Sales
              <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" />
            </Link>
          </Magnetic>
        </div>
        <p className="mt-space-lg font-code text-body-sm text-outline">Free tier includes 3 active rooms and unlimited AI copilot queries.</p>
      </Reveal>
    </section>
  );
}
