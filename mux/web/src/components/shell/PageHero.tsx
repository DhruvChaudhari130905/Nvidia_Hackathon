'use client';

import React from 'react';

// Hero band shared by the Docs, Rooms, Sandbox and Pricing screens: faded grid, floating glows,
// a pill badge, a headline and an optional right-hand column.

interface PageHeroProps {
  badge: React.ReactNode;
  title: React.ReactNode;
  lead: React.ReactNode;
  children?: React.ReactNode; // actions / search under the lead
  aside?: React.ReactNode; // right-hand column on large screens
  centered?: boolean;
}

export const GRID_BACKDROP: React.CSSProperties = {
  backgroundImage:
    'linear-gradient(rgba(255,255,255,0.04) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.04) 1px, transparent 1px)',
  backgroundSize: '44px 44px',
  maskImage: 'radial-gradient(ellipse at 30% 40%, black 20%, transparent 70%)',
  WebkitMaskImage: 'radial-gradient(ellipse at 30% 40%, black 20%, transparent 70%)',
};

export function PageHero({ badge, title, lead, children, aside, centered = false }: PageHeroProps) {
  return (
    <section className="relative overflow-hidden px-gutter pb-14 pt-14 md:px-space-xl">
      <div className="pointer-events-none absolute inset-0 opacity-40" style={GRID_BACKDROP} />
      <div className="float-slow pointer-events-none absolute -left-20 top-10 h-72 w-72 rounded-full bg-primary/15 blur-3xl" />
      <div className="float-slower pointer-events-none absolute right-0 top-24 h-80 w-80 rounded-full bg-secondary/10 blur-3xl" />

      <div
        className={`relative mx-auto grid max-w-6xl items-center gap-space-xl ${
          aside ? 'lg:grid-cols-[1.25fr_1fr]' : ''
        } ${centered ? 'justify-items-center text-center' : ''}`}
      >
        <div className={`animate-fade-up ${centered ? 'flex flex-col items-center' : ''}`}>
          <div className="mb-space-md inline-flex items-center gap-space-sm rounded-full border border-primary/20 bg-primary/10 px-space-md py-space-xs text-label-md text-primary">
            {badge}
          </div>
          <h1 className="mb-space-md font-headline text-4xl font-bold leading-tight tracking-tight md:text-5xl">{title}</h1>
          <p className={`mb-space-lg max-w-xl text-body-lg text-on-surface-variant ${centered ? 'mx-auto' : ''}`}>{lead}</p>
          {children}
        </div>
        {aside && <div className="animate-fade-up" style={{ animationDelay: '120ms' }}>{aside}</div>}
      </div>
    </section>
  );
}

// Gradient icon tile used on cards (matches the Docs quick-start tiles)
export function IconTile({ icon: Icon, size = 'md' }: { icon: React.ComponentType<{ className?: string }>; size?: 'sm' | 'md' }) {
  const dims = size === 'sm' ? 'h-9 w-9 rounded-lg' : 'h-11 w-11 rounded-xl';
  return (
    <span
      className={`grid flex-none place-items-center bg-gradient-to-br from-primary to-secondary text-white shadow-[0_8px_24px_-8px_rgba(59,130,246,0.8)] transition-transform duration-300 group-hover:rotate-6 group-hover:scale-110 ${dims}`}
    >
      <Icon className={size === 'sm' ? 'h-4 w-4' : 'h-5 w-5'} />
    </span>
  );
}

// Rounded pill filter chip (the Docs search-suggestion style)
export function FilterChip({ on, onClick, children }: { on: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={on}
      className={`rounded-full border px-3 py-1 font-code text-code-sm transition-colors ${
        on ? 'border-primary/50 bg-primary/15 text-on-surface' : 'border-white/10 text-outline hover:border-primary/40 hover:text-on-surface'
      }`}
    >
      {children}
    </button>
  );
}

// Closing gradient call-to-action card (the Docs "You've got the whole picture" block)
export function CtaCard({ title, text, children }: { title: React.ReactNode; text: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="relative overflow-hidden rounded-2xl border border-white/10 bg-gradient-to-br from-primary/15 via-surface-container to-secondary/10 p-space-xl text-center">
      <div className="float-slow pointer-events-none absolute -right-10 -top-10 h-48 w-48 rounded-full bg-secondary/20 blur-3xl" />
      <h3 className="relative mb-space-sm font-headline text-2xl font-bold">{title}</h3>
      <p className="relative mb-space-lg text-body-md text-on-surface-variant">{text}</p>
      <div className="relative flex flex-wrap justify-center gap-space-sm">{children}</div>
    </div>
  );
}

export const BTN_PRIMARY =
  'btn-shine flex items-center gap-space-sm rounded-full bg-primary px-space-lg py-space-sm text-label-md font-bold text-white transition-all hover:shadow-[0_0_25px_rgba(59,130,246,0.6)] disabled:opacity-60';
export const BTN_GHOST =
  'flex items-center gap-space-sm rounded-full border border-white/15 px-space-lg py-space-sm text-label-md text-on-surface transition-colors hover:border-primary/50 disabled:opacity-60';
export const CARD = 'rounded-xl border border-white/10 bg-surface-container/70 backdrop-blur';
