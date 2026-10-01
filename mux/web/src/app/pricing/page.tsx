'use client';

import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { Zap, Code2, Users, ShieldCheck, CheckCircle2, Minus, Check, ChevronDown, Calculator, PlayCircle, Mail } from 'lucide-react';
import { BTN_GHOST, BTN_PRIMARY, CARD, CtaCard, IconTile, PageHero, Reveal, ShaderBackground, SiteHeader, SiteFooter, Spotlight } from '@/components/shell';

// Pricing screen (stitch: mux_pricing_live_wallpaper_pro)

type Billing = 'monthly' | 'annual';

const COMPARISON: { feature: string; free: React.ReactNode; pro: React.ReactNode; enterprise: React.ReactNode }[] = [
  { feature: 'Active Rooms', free: '3 rooms', pro: 'Unlimited', enterprise: 'Unlimited + VPC' },
  { feature: 'Monthly AI Tokens', free: '100k', pro: '2M / user', enterprise: 'Custom / Unlimited' },
  { feature: 'Build Workers', free: 'Standard', pro: 'Priority Nebius', enterprise: 'Dedicated Runners' },
  { feature: 'GitHub Integration', free: false, pro: true, enterprise: true },
  { feature: 'Real-Time Voice & Cursors', free: false, pro: true, enterprise: true },
  { feature: 'SAML / SSO & Audit Logs', free: false, pro: false, enterprise: true },
];

const FAQS = [
  {
    q: 'What is a collaborative coding room?',
    a: 'A room is an isolated live development environment where multiple users and AI coding assistants can write code simultaneously, run builds, and vote on tasks in real time.',
  },
  {
    q: 'Can I bring my own API keys for AI models?',
    a: 'Yes! Team Pro and Enterprise plans allow you to configure custom API keys for OpenAI, Anthropic, or local model providers running on your infrastructure.',
  },
  {
    q: 'How do build workers function?',
    a: 'MUX spins up lightning-fast isolated build containers (powered by Nebius) to test your React, Vite, and Node applications instantly whenever code changes or tasks merge.',
  },
  {
    q: 'Can I cancel or change my plan anytime?',
    a: 'Absolutely. You can upgrade, downgrade, or cancel your subscription directly from your billing dashboard with zero cancellation fees.',
  },
];

function Feature({ children, muted, iconClass = 'text-primary' }: { children: React.ReactNode; muted?: boolean; iconClass?: string }) {
  return (
    <div className={`flex items-center gap-space-sm text-body-md ${muted ? 'text-on-surface-variant' : 'text-on-surface'}`}>
      {muted ? <Minus className="h-[18px] w-[18px] flex-none text-outline" /> : <CheckCircle2 className={`h-[18px] w-[18px] flex-none ${iconClass}`} />}
      <span className={muted ? 'line-through' : ''}>{children}</span>
    </div>
  );
}

function Cell({ value, highlight }: { value: React.ReactNode; highlight?: boolean }) {
  if (value === true) return <Check className={`mx-auto h-5 w-5 ${highlight ? 'text-primary' : 'text-on-surface'}`} aria-label="Included" />;
  if (value === false) return <Minus className="mx-auto h-5 w-5 text-outline" aria-label="Not included" />;
  return <>{value}</>;
}

// Question that expands to show its answer, with the height animated
function FaqItem({ q, a }: { q: string; a: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className={`rounded-xl border bg-surface-container/70 backdrop-blur transition-colors ${open ? 'border-primary/40' : 'border-white/10 hover:border-white/20'}`}>
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-space-md p-space-lg text-left"
      >
        <h3 className="font-headline text-headline-sm text-on-surface">{q}</h3>
        <ChevronDown className={`h-4 w-4 flex-none text-outline transition-transform duration-300 ${open ? 'rotate-180 text-primary' : ''}`} />
      </button>
      <div className={`grid transition-[grid-template-rows] duration-300 ease-out ${open ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'}`}>
        <div className="overflow-hidden">
          <p className="px-space-lg pb-space-lg text-body-md text-on-surface-variant">{a}</p>
        </div>
      </div>
    </div>
  );
}

const PRO_MONTHLY = 29;
const PRO_ANNUAL = 23;

// Team-size slider: what Team Pro costs, and how many tokens the team gets
function Estimator({ annual }: { annual: boolean }) {
  const [seats, setSeats] = useState(5);
  const rate = annual ? PRO_ANNUAL : PRO_MONTHLY;
  const monthly = seats * rate;
  const saved = seats * (PRO_MONTHLY - PRO_ANNUAL) * 12;
  return (
    <div className={`${CARD} grid gap-space-xl p-space-xl md:grid-cols-[1.2fr_1fr] md:items-center`}>
      <div>
        <div className="mb-space-md flex items-center gap-space-md">
          <IconTile icon={Calculator} size="sm" />
          <div>
            <span className="font-code text-[11px] uppercase tracking-[0.18em] text-outline">Team Pro estimate</span>
            <h3 className="font-headline text-headline-md text-on-surface">How big is your team?</h3>
          </div>
        </div>
        <div className="mb-space-sm flex items-baseline justify-between">
          <span className="text-body-md text-on-surface-variant">Seats</span>
          <span className="font-headline text-2xl font-bold tabular-nums text-on-surface">{seats}</span>
        </div>
        <input
          type="range"
          min={1}
          max={50}
          value={seats}
          onChange={e => setSeats(Number(e.target.value))}
          aria-label="Number of seats"
          className="w-full accent-[rgb(59,130,246)]"
        />
        <div className="mt-1 flex justify-between font-code text-[11px] text-outline">
          <span>1</span><span>8 per room</span><span>50</span>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-space-sm">
        <div className="rounded-xl border border-white/10 bg-surface/60 p-space-md">
          <div className="font-code text-[11px] uppercase tracking-[0.15em] text-outline">Per month</div>
          <div key={`${monthly}-${annual}`} className="item-in font-headline text-2xl font-bold tabular-nums text-primary">${monthly.toLocaleString()}</div>
        </div>
        <div className="rounded-xl border border-white/10 bg-surface/60 p-space-md">
          <div className="font-code text-[11px] uppercase tracking-[0.15em] text-outline">AI tokens</div>
          <div className="font-headline text-2xl font-bold tabular-nums text-secondary">{seats * 2}M</div>
        </div>
        <div className="col-span-2 rounded-xl border border-white/10 bg-surface/60 p-space-md text-body-sm text-on-surface-variant">
          {annual ? (
            <>Annual billing saves your team <span className="font-bold text-primary">${saved.toLocaleString()}</span> a year.</>
          ) : (
            <>Switch to annual billing to save <span className="font-bold text-primary">${saved.toLocaleString()}</span> a year.</>
          )}
        </div>
      </div>
    </div>
  );
}

export default function PricingPage() {
  const [billing, setBilling] = useState<Billing>('monthly');
  const annual = billing === 'annual';

  // Sliding highlight behind the selected billing option
  const monthlyRef = useRef<HTMLButtonElement>(null);
  const annualRef = useRef<HTMLButtonElement>(null);
  const [pill, setPill] = useState({ left: 0, width: 0 });
  const measurePill = useCallback(() => {
    const el = annual ? annualRef.current : monthlyRef.current;
    if (!el) return;
    const next = { left: el.offsetLeft, width: el.offsetWidth };
    setPill(prev => (prev.left === next.left && prev.width === next.width ? prev : next));
  }, [annual]);
  useLayoutEffect(measurePill, [measurePill]);
  // Re-measure when the window resizes or the web fonts finish loading (both change the buttons' widths)
  useEffect(() => {
    let active = true;
    window.addEventListener('resize', measurePill);
    document.fonts?.ready.then(() => { if (active) measurePill(); });
    return () => {
      active = false;
      window.removeEventListener('resize', measurePill);
    };
  }, [measurePill]);

  const toggleClass = (on: boolean) =>
    `relative z-10 flex items-center gap-space-xs rounded-full px-space-lg py-space-sm text-label-md transition-colors duration-300 ${
      on ? 'font-bold text-on-surface' : 'text-on-surface-variant hover:text-on-surface'
    }`;

  return (
    <div className="relative flex min-h-screen flex-col bg-surface font-ui text-body-md text-on-surface">
      <ShaderBackground className="fixed inset-0 z-0 opacity-20" />
      <SiteHeader active="pricing" />

      <main className="relative z-10 w-full bg-transparent pt-16">
        <PageHero
          centered
          badge={<><Zap className="h-4 w-4" /> Simple, predictable pricing</>}
          title={<>Scale your rooms <span className="text-shimmer">without limits</span></>}
          lead="Start free, upgrade when your team does. Every plan gets instant sandboxes, AI coding agents and real-time collaboration."
        >
          <div className="relative flex items-center gap-space-md rounded-full border border-white/10 bg-surface-container/80 p-1.5 backdrop-blur" role="group" aria-label="Billing period">
            <span
              aria-hidden="true"
              className="absolute bottom-1.5 top-1.5 rounded-full bg-surface-container-high shadow-[0_0_20px_rgba(59,130,246,0.25)] ring-1 ring-primary/30 transition-all duration-300 ease-out"
              style={{ left: pill.left, width: pill.width }}
            />
            <button ref={monthlyRef} type="button" className={toggleClass(!annual)} aria-pressed={!annual} onClick={() => setBilling('monthly')}>
              Monthly
            </button>
            <button ref={annualRef} type="button" className={toggleClass(annual)} aria-pressed={annual} onClick={() => setBilling('annual')}>
              Annual
              <span className="rounded-full bg-primary/20 px-space-xs py-0.5 font-code text-code-sm font-bold text-primary">Save 20%</span>
            </button>
          </div>
        </PageHero>

        {/* Plans */}
        <section className="mx-auto box-content max-w-6xl px-gutter pb-20 md:px-space-xl">
          <div className="grid grid-cols-1 gap-space-lg md:grid-cols-3">
            <Reveal className="h-full">
            <Spotlight className="group flex h-full flex-col justify-between rounded-2xl border border-white/10 bg-surface-container/70 p-space-xl backdrop-blur transition-all duration-300 hover:-translate-y-1 hover:border-primary/40 hover:bg-surface-container">
              <div>
                <div className="mb-space-md flex items-center justify-between">
                  <span className="font-headline text-headline-md text-on-surface">Free Developer</span>
                  <IconTile icon={Code2} size="sm" />
                </div>
                <p className="mb-space-lg text-body-sm text-on-surface-variant">
                  Perfect for trying out real-time coding rooms and small personal projects.
                </p>
                <div className="mb-space-lg flex items-baseline gap-space-xs">
                  <span className="font-headline text-[40px] font-bold tracking-tight text-on-surface">$0</span>
                  <span className="text-body-sm text-on-surface-variant">/ month</span>
                </div>
                <div className="mb-space-xl space-y-space-md">
                  <Feature>Up to 3 active collaboration rooms</Feature>
                  <Feature>100k AI tokens / month</Feature>
                  <Feature>Standard build workers</Feature>
                  <Feature muted>GitHub automatic PR sync</Feature>
                </div>
              </div>
              <Link
                href="/login"
                className="w-full rounded-full border border-white/15 py-space-md text-center text-label-md font-bold text-on-surface transition-colors hover:border-primary/50 hover:bg-white/[0.04]"
              >
                Get Started Free
              </Link>
            </Spotlight>
            </Reveal>

            <Reveal delay={100} className="relative z-10 h-full">
            <Spotlight className="group flex h-full flex-col justify-between rounded-2xl border border-primary/50 bg-gradient-to-br from-primary/15 via-surface-container/90 to-secondary/10 p-space-xl shadow-[0_20px_60px_-15px_rgba(59,130,246,0.5)] backdrop-blur transition-all duration-300 hover:-translate-y-1 md:scale-[1.02]">
              <div className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-gradient-to-r from-primary to-secondary px-space-md py-0.5 font-code text-code-sm font-bold uppercase tracking-wider text-on-primary shadow-[0_0_20px_rgba(59,130,246,0.6)]">
                Most Popular
              </div>
              <div>
                <div className="mb-space-md flex items-center justify-between">
                  <span className="font-headline text-headline-md text-on-surface">Team Pro</span>
                  <IconTile icon={Users} size="sm" />
                </div>
                <p className="mb-space-lg text-body-sm text-on-surface-variant">
                  For professional teams building fast with real-time AI and continuous sync.
                </p>
                <div className="mb-space-lg flex items-baseline gap-space-xs">
                  <span key={billing} className="item-in inline-block font-headline text-[40px] font-bold tracking-tight text-on-surface">{annual ? `$${PRO_ANNUAL}` : `$${PRO_MONTHLY}`}</span>
                  <span key={`${billing}-period`} className="item-in text-body-sm text-on-surface-variant">{annual ? '/ user / month, billed annually' : '/ user / month'}</span>
                </div>
                <div className="mb-space-xl space-y-space-md">
                  <Feature>Unlimited concurrent rooms</Feature>
                  <Feature>2M AI tokens / user / month</Feature>
                  <Feature>Priority Nebius build workers</Feature>
                  <Feature>Full GitHub PR &amp; repo export</Feature>
                  <Feature>Live voice &amp; cursor presence</Feature>
                </div>
              </div>
              <Link
                href="/login"
                className="btn-shine w-full rounded-full bg-primary py-space-md text-center text-label-md font-bold text-on-primary shadow-md transition-all hover:bg-primary/90 hover:shadow-[0_0_25px_rgba(59,130,246,0.6)]"
              >
                Start 14-Day Pro Trial
              </Link>
            </Spotlight>
            </Reveal>

            <Reveal delay={200} className="h-full">
            <Spotlight id="contact" className="flex h-full scroll-mt-24 flex-col justify-between rounded-lg bg-surface-container/90 p-space-xl shadow-lg backdrop-blur transition-all duration-300 hover:-translate-y-1 hover:bg-surface-container-high">
              <div>
                <div className="mb-space-md flex items-center justify-between">
                  <span className="font-headline text-headline-md text-on-surface">Enterprise</span>
                  <IconTile icon={ShieldCheck} size="sm" />
                </div>
                <p className="mb-space-lg text-body-sm text-on-surface-variant">
                  Advanced security, custom AI model routing, and dedicated infrastructure.
                </p>
                <div className="mb-space-lg flex items-baseline gap-space-xs">
                  <span className="font-headline text-[40px] font-bold tracking-tight text-on-surface">Custom</span>
                  <span className="text-body-sm text-on-surface-variant">/ tailored</span>
                </div>
                <div className="mb-space-xl space-y-space-md">
                  <Feature iconClass="text-secondary">Everything in Team Pro</Feature>
                  <Feature iconClass="text-secondary">Unlimited AI tokens (BYO keys option)</Feature>
                  <Feature iconClass="text-secondary">SSO / SAML &amp; Audit logs</Feature>
                  <Feature iconClass="text-secondary">Dedicated VPC &amp; custom runners</Feature>
                </div>
              </div>
              <a
                href="mailto:sales@mux.dev?subject=MUX%20Enterprise"
                className="w-full rounded-full border border-white/15 py-space-md text-center text-label-md font-bold text-on-surface transition-colors hover:border-primary/50 hover:bg-white/[0.04]"
              >
                Contact Sales
              </a>
            </Spotlight>
            </Reveal>
          </div>
        </section>

        {/* Estimator */}
        <section className="mx-auto box-content max-w-6xl px-gutter pb-20 md:px-space-xl">
          <Reveal>
            <div className="relative">
              <span className="absolute -top-2.5 left-4 z-10 rounded-full bg-surface px-2 font-code text-[10px] uppercase tracking-[0.2em] text-secondary">Try it</span>
              <Estimator annual={annual} />
            </div>
          </Reveal>
        </section>

        {/* Comparison */}
        <section className="mx-auto box-content max-w-6xl px-gutter pb-20 md:px-space-xl">
          <Reveal>
          <div className="mb-space-xl text-center">
            <span className="font-code text-[11px] uppercase tracking-[0.18em] text-outline">Compare</span>
            <h2 className="mb-space-sm font-headline text-2xl font-bold tracking-tight text-on-surface md:text-3xl">Every feature, side by side</h2>
            <p className="text-body-md text-on-surface-variant">Detailed breakdown of what&apos;s included across all tiers.</p>
          </div>
          <div className="overflow-x-auto rounded-xl border border-white/10 bg-surface-container/70 backdrop-blur">
            <div className="min-w-[560px]">
              <div className="grid grid-cols-4 border-b border-white/10 bg-white/[0.03] p-space-lg font-headline text-headline-sm text-on-surface">
                <div>Feature</div>
                <div className="text-center">Free</div>
                <div className="text-center text-primary">Team Pro</div>
                <div className="text-center">Enterprise</div>
              </div>
              <div className="divide-y divide-white/5">
                {COMPARISON.map(row => (
                  <div key={row.feature} className="grid grid-cols-4 items-center p-space-lg text-body-md transition-colors hover:bg-primary/5">
                    <div className="font-medium text-on-surface">{row.feature}</div>
                    <div className="text-center text-on-surface-variant"><Cell value={row.free} /></div>
                    <div className="text-center font-bold text-primary"><Cell value={row.pro} highlight /></div>
                    <div className="text-center text-on-surface"><Cell value={row.enterprise} highlight={row.feature.startsWith('SAML')} /></div>
                  </div>
                ))}
              </div>
            </div>
          </div>
          </Reveal>
        </section>

        {/* FAQ */}
        <section className="mx-auto box-content max-w-4xl px-gutter pb-20 md:px-space-xl">
          <Reveal className="mb-space-xl text-center">
            <span className="font-code text-[11px] uppercase tracking-[0.18em] text-outline">FAQ</span>
            <h2 className="mb-space-sm font-headline text-2xl font-bold tracking-tight text-on-surface md:text-3xl">Questions, answered</h2>
            <p className="text-body-md text-on-surface-variant">Got questions about billing, rooms, or security? We&apos;ve got answers.</p>
          </Reveal>
          <div className="space-y-space-md">
            {FAQS.map((faq, i) => (
              <Reveal key={faq.q} delay={i * 80}>
                <FaqItem q={faq.q} a={faq.a} />
              </Reveal>
            ))}
          </div>
        </section>

        <section className="mx-auto box-content max-w-6xl px-gutter pb-24 md:px-space-xl">
          <Reveal>
            <CtaCard title="See it before you pay for it." text="Open the sample room, or start free. No card needed.">
              <Link href="/login" className={BTN_PRIMARY}>
                <Zap className="h-4 w-4" /> Get started free
              </Link>
              <Link href="/docs" className={BTN_GHOST}>
                <PlayCircle className="h-4 w-4" /> Read the docs
              </Link>
              <a href="mailto:sales@mux.dev?subject=MUX%20Enterprise" className={BTN_GHOST}>
                <Mail className="h-4 w-4" /> Talk to sales
              </a>
            </CtaCard>
          </Reveal>
        </section>
      </main>

      <SiteFooter />
    </div>
  );
}
