'use client';

import React, { useState } from 'react';
import { BadgeCheck, ChevronLeft, ChevronRight, Quote } from 'lucide-react';

// Auto-advancing testimonial carousel. Each slide's progress bar is a CSS animation; when it
// finishes the carousel moves on, and hovering pauses it (animation-play-state).

const QUOTES = [
  {
    text: 'MUX transformed how our distributed team prototyped our core product. We cut our feature delivery cycle from two weeks down to a single afternoon.',
    name: 'Elena Rostova',
    role: 'VP of Engineering at CloudScale',
    initials: 'ER',
    gradient: 'from-primary to-secondary',
  },
  {
    text: 'Our PM, designer and two engineers steered one agent together. The vote cards ended the "whose idea wins" meetings for good.',
    name: 'Marcus Chen',
    role: 'Head of Product at Northwind',
    initials: 'MC',
    gradient: 'from-secondary to-[#a371f7]',
  },
  {
    text: 'Being able to rewind to any checkpoint made us fearless. We tried three checkout flows in an hour and kept the best one.',
    name: 'Aisha Patel',
    role: 'Founding Engineer at Loop',
    initials: 'AP',
    gradient: 'from-[#a371f7] to-primary',
  },
];

const SLIDE_MS = 6500;

export function Testimonials() {
  const [index, setIndex] = useState(0);
  const [paused, setPaused] = useState(false);
  const go = (i: number) => setIndex((i + QUOTES.length) % QUOTES.length);

  return (
    <section
      className="relative overflow-hidden px-gutter py-24 md:px-16 lg:px-24"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      aria-roledescription="carousel"
      aria-label="What teams say"
    >
      <div className="pointer-events-none absolute inset-0 bg-gradient-to-b from-transparent via-primary/[0.04] to-transparent" />
      <Quote className="pointer-events-none absolute left-1/2 top-10 h-40 w-40 -translate-x-1/2 text-primary/[0.06]" aria-hidden="true" />

      <div className="relative mx-auto flex max-w-5xl flex-col items-center text-center">
        <div className="mb-space-xl inline-flex items-center gap-space-xs rounded-full border border-primary/20 bg-primary/10 px-space-md py-space-xs text-label-md text-primary">
          <BadgeCheck className="h-4 w-4" />
          Trusted by engineering leads at top tech companies
        </div>

        <div className="relative w-full overflow-hidden">
          <div className="flex transition-transform duration-700 ease-[cubic-bezier(.2,.8,.2,1)]" style={{ transform: `translateX(-${index * 100}%)` }}>
            {QUOTES.map((q, i) => (
              <figure
                key={q.name}
                className="w-full flex-none px-2 transition-all duration-700"
                style={{ opacity: i === index ? 1 : 0.2, transform: i === index ? 'none' : 'scale(0.94)' }}
                aria-hidden={i !== index}
              >
                <blockquote className="mx-auto mb-space-xl max-w-3xl font-display text-xl font-medium leading-snug tracking-[-0.01em] text-on-surface md:text-2xl lg:text-3xl">
                  “{q.text}”
                </blockquote>
                <figcaption className="flex items-center justify-center gap-space-md">
                  <div className={`grid h-12 w-12 place-items-center rounded-full bg-gradient-to-br ${q.gradient} font-headline text-headline-sm text-white shadow-[0_0_20px_rgba(59,130,246,0.35)]`}>
                    {q.initials}
                  </div>
                  <div className="text-left">
                    <p className="font-headline text-headline-sm text-on-surface">{q.name}</p>
                    <p className="text-body-sm text-on-surface-variant">{q.role}</p>
                  </div>
                </figcaption>
              </figure>
            ))}
          </div>
        </div>

        <div className="mt-space-xl flex items-center gap-space-md">
          <button type="button" onClick={() => go(index - 1)} className="grid h-9 w-9 place-items-center rounded-full text-on-surface-variant transition-all hover:bg-white/10 hover:text-on-surface" aria-label="Previous testimonial">
            <ChevronLeft className="h-5 w-5" />
          </button>
          <div className="flex items-center gap-2">
            {QUOTES.map((q, i) => (
              <button
                key={q.name}
                type="button"
                onClick={() => go(i)}
                aria-label={`Show testimonial ${i + 1}`}
                aria-current={i === index}
                className={`relative h-1.5 overflow-hidden rounded-full bg-white/10 transition-all duration-500 ${i === index ? 'w-14' : 'w-6 hover:bg-white/20'}`}
              >
                {i === index && (
                  <span
                    key={index}
                    className="absolute inset-y-0 left-0 rounded-full bg-gradient-to-r from-primary to-secondary"
                    style={{
                      animation: `carousel-fill ${SLIDE_MS}ms linear forwards`,
                      animationPlayState: paused ? 'paused' : 'running',
                    }}
                    onAnimationEnd={() => go(index + 1)}
                  />
                )}
              </button>
            ))}
          </div>
          <button type="button" onClick={() => go(index + 1)} className="grid h-9 w-9 place-items-center rounded-full text-on-surface-variant transition-all hover:bg-white/10 hover:text-on-surface" aria-label="Next testimonial">
            <ChevronRight className="h-5 w-5" />
          </button>
        </div>
      </div>
    </section>
  );
}
