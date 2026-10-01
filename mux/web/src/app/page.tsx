'use client';

import React from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Zap, PlayCircle } from 'lucide-react';
import { CountUp, Reveal, ShaderBackground, SiteHeader, SiteFooter } from '@/components/shell';
import { ActivityTicker, FeatureSlides, FinalCta, HowItWorks, LiveRoomPreview, Testimonials } from '@/components/landing';
import { setDemoMode } from '@/lib/demo';

// Overview / landing screen (stitch: mux_overview_live_wallpaper_pro)

const STATS = [
  { value: '0.2s', label: 'Real-Time Sync Latency', color: 'text-primary' },
  { value: '1.2M+', label: 'Tokens Processed Daily', color: 'text-secondary' },
  { value: '99.9%', label: 'Build Success Rate', color: 'text-primary' },
  { value: '50K+', label: 'Active Builders', color: 'text-tertiary' },
];

export default function OverviewPage() {
  const router = useRouter();

  const openDemo = () => {
    setDemoMode(true);
    router.push('/room/demo-yoga');
  };

  return (
    <div className="flex min-h-screen flex-col bg-surface font-ui text-body-md text-on-surface">
      <SiteHeader active="overview" />

      <main className="w-full bg-surface pt-16">
        {/* Hero */}
        <section className="relative flex flex-col items-center overflow-hidden px-gutter pb-24 pt-space-xl text-center md:px-16 lg:px-24">
          <ShaderBackground interactive className="absolute inset-0 z-0 opacity-75" />
          <div className="pointer-events-none absolute inset-0 z-0 bg-gradient-to-b from-primary/10 via-transparent to-transparent" />
          <div className="float-slow pointer-events-none absolute -top-48 z-0 h-[600px] w-[600px] rounded-full bg-primary/5 blur-3xl" />
          <div className="float-slower pointer-events-none absolute right-[-10%] top-40 z-0 h-[420px] w-[420px] rounded-full bg-secondary/5 blur-3xl" />

          <div className="relative z-10 flex w-full max-w-6xl flex-col items-center">
            <div className="animate-fade-up mb-space-lg inline-flex items-center gap-space-sm rounded-full border border-outline-variant/30 bg-surface-container/90 px-space-md py-space-xs text-body-sm text-on-surface-variant shadow-sm backdrop-blur-md transition-transform duration-300 hover:scale-105">
              <span className="flex h-2 w-2 rounded-full bg-primary animate-pulse" />
              <span className="font-code text-code-sm text-primary">v2.4 Live Release</span>
              <span className="text-outline">•</span>
              <span>Multiplayer Coding &amp; AI Workflows</span>
            </div>

            <h1 style={{ animationDelay: '80ms' }} className="mb-space-md max-w-4xl animate-fade-up font-headline text-4xl font-bold tracking-tight text-on-surface md:text-5xl lg:text-6xl">
              Build Together in{' '}
              <span className="text-shimmer">Real-Time</span>
            </h1>
            <p style={{ animationDelay: '160ms' }} className="mb-space-xl max-w-2xl animate-fade-up text-body-lg text-on-surface-variant">
              Synchronous coding rooms equipped with autonomous AI copilots, instant sandboxes, live voting, and seamless
              GitHub integration for high-velocity teams.
            </p>

            <div style={{ animationDelay: '240ms' }} className="mb-20 flex animate-fade-up flex-wrap items-center justify-center gap-space-md">
              <Link
                href="/dashboard"
                className="btn-shine flex items-center gap-space-sm rounded-lg bg-primary px-space-xl py-space-md text-label-md font-bold text-on-primary shadow-lg shadow-primary/20 transition-all hover:-translate-y-0.5 hover:bg-primary/90 hover:shadow-[0_0_25px_rgba(59,130,246,0.6)]"
              >
                <Zap className="h-[18px] w-[18px]" />
                Start a Build Room
              </Link>
              <button
                type="button"
                onClick={openDemo}
                className="flex items-center gap-space-sm rounded-lg border border-outline-variant/30 bg-surface-container/90 px-space-xl py-space-md text-label-md font-medium text-on-surface backdrop-blur-md transition-all hover:-translate-y-0.5 hover:border-primary/50 hover:bg-surface-bright hover:shadow-[0_0_20px_rgba(6,182,212,0.2)]"
              >
                <PlayCircle className="h-[18px] w-[18px]" />
                Watch 2-Min Demo
              </button>
            </div>

            <div style={{ animationDelay: '360ms' }} className="w-full animate-fade-up">
              <LiveRoomPreview />
            </div>
          </div>
        </section>

        {/* Stats */}
        <section className="bg-surface-container-lowest px-gutter py-space-xl md:px-16 lg:px-24">
          <div className="mx-auto grid max-w-6xl grid-cols-2 gap-space-xl text-center md:grid-cols-4">
            {STATS.map((stat, i) => (
              <Reveal key={stat.label} delay={i * 90}>
                <div className="p-space-md transition-transform duration-300 hover:scale-105">
                  <p className={`mb-1 font-headline text-3xl font-bold md:text-4xl ${stat.color}`}>
                    <CountUp value={stat.value} />
                  </p>
                  <p className="text-body-sm uppercase tracking-wider text-on-surface-variant">{stat.label}</p>
                </div>
              </Reveal>
            ))}
          </div>
        </section>

        {/* Live activity ticker */}
        <section className="border-y border-outline-variant/20 bg-surface">
          <ActivityTicker />
        </section>

        {/* Features: intro, then pinned sliding pages */}
        <section className="px-gutter pb-8 pt-24 md:px-16 lg:px-24">
          <Reveal className="mx-auto max-w-2xl text-center">
            <span className="mb-space-sm block font-code text-label-md uppercase tracking-widest text-primary">Engineered for Velocity</span>
            <h2 className="mb-space-md font-headline text-3xl font-bold tracking-tight md:text-4xl">
              Everything you need to ship products at <span className="text-shimmer">light speed</span>
            </h2>
            <p className="text-body-lg text-on-surface-variant">
              Designed by engineers for engineers. Eliminate context switching and build seamlessly with your team and AI.
            </p>
          </Reveal>
        </section>
        <FeatureSlides />

        <HowItWorks />
        <Testimonials />
        <FinalCta />
      </main>

      <SiteFooter />
    </div>
  );
}
