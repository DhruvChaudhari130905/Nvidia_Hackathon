'use client';

import React, { useEffect, useRef, useState } from 'react';
import { MessageSquareText, Users, Rocket } from 'lucide-react';
import { SplitHeading } from '@/components/shell';

// Three steps joined by a line that draws itself as you scroll; each step lights up when the
// line reaches it.

const STEPS = [
  {
    icon: MessageSquareText,
    title: 'Describe it',
    body: 'Say what you want to build. The coordinator turns it into a plan the room can edit and approve.',
    sample: '“A booking app for yoga classes with Stripe payments”',
  },
  {
    icon: Users,
    title: 'Steer together',
    body: 'Up to eight people chat, vote and answer questions while one agent writes the code and runs the builds.',
    sample: 'merge · queue · vote · rewind',
  },
  {
    icon: Rocket,
    title: 'Ship it',
    body: 'Every passing build is a checkpoint. When you like what you see, export the room straight to GitHub.',
    sample: 'checkpoint 7 → github.com/you/app',
  },
];

export function HowItWorks() {
  const ref = useRef<HTMLDivElement>(null);
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    let frame = 0;
    const onScroll = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const el = ref.current;
        if (!el) return;
        const r = el.getBoundingClientRect();
        // 0 when the list's top reaches 70% of the viewport, 1 when its bottom reaches 50%
        const start = window.innerHeight * 0.7;
        const end = window.innerHeight * 0.5;
        setProgress(Math.min(1, Math.max(0, (start - r.top) / (r.height + start - end))));
      });
    };
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener('scroll', onScroll);
    };
  }, []);

  return (
    <section className="relative px-gutter py-24 md:px-16 lg:px-24">
      <div className="mx-auto mb-20 max-w-3xl text-center">
        <SplitHeading text="From idea to repo in three moves" className="font-display text-4xl font-bold leading-[1.02] tracking-[-0.035em] md:text-6xl" />
      </div>

      <div ref={ref} className="relative mx-auto max-w-3xl">
        <div className="absolute bottom-0 left-6 top-0 w-px bg-white/10 md:left-1/2">
          <div className="w-full origin-top bg-gradient-to-b from-primary via-secondary to-[#a371f7] shadow-[0_0_12px_rgba(6,182,212,0.8)]" style={{ height: `${progress * 100}%` }} />
        </div>

        <div className="space-y-20">
          {STEPS.map((step, i) => {
            const lit = progress >= (i + 0.35) / STEPS.length;
            const Icon = step.icon;
            // Alternate sides on desktop; text faces the center line
            const left = i % 2 === 0;
            return (
              <div key={step.title} className="relative grid grid-cols-[3rem_1fr] items-center gap-space-lg md:grid-cols-2 md:gap-16">
                <div
                  className={`absolute left-6 top-1/2 z-10 grid h-12 w-12 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full border transition-all duration-500 md:left-1/2 ${
                    lit
                      ? 'scale-110 border-secondary bg-gradient-to-br from-primary to-secondary text-white shadow-[0_0_30px_rgba(6,182,212,0.6)]'
                      : 'border-white/15 bg-surface text-outline'
                  }`}
                >
                  <Icon className="h-5 w-5" />
                </div>
                <div
                  className={`col-start-2 transition-all duration-700 md:row-start-1 ${left ? 'md:col-start-1 md:pr-10 md:text-right' : 'md:col-start-2 md:pl-10'} ${
                    lit ? 'translate-y-0 opacity-100' : 'translate-y-4 opacity-40'
                  }`}
                >
                  <span className="font-code text-code-sm text-secondary">Step 0{i + 1}</span>
                  <h3 className="mb-space-sm mt-1 font-display text-2xl font-bold tracking-[-0.02em] text-on-surface">{step.title}</h3>
                  <p className="mb-space-md text-body-md text-on-surface-variant">{step.body}</p>
                  <span className="inline-block rounded-full bg-white/[0.04] px-space-md py-1.5 font-code text-code-sm text-on-surface-variant ring-1 ring-white/10">
                    {step.sample}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
