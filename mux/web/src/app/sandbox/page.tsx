'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { Terminal, Cpu, Globe, Server, ArrowRight, Layers, Atom, Boxes, FileCode2, Network, PlusCircle, PlayCircle, Rocket } from 'lucide-react';
import { AppShell, BTN_GHOST, BTN_PRIMARY, CARD, CtaCard, FilterChip, IconTile, PageHero, Reveal, Spotlight, prefersReducedMotion } from '@/components/shell';
import { STARTER_TEMPLATES } from '@/lib/templates';
import { useRouter } from 'next/navigation';
import { setDemoMode } from '@/lib/demo';
import { useRequireAuth } from '@/lib/useRequireAuth';

// Sandbox screen: starter templates and the runtimes rooms build on.
// No stitch screen exists for it; it follows the Active Rooms layout.

const RUNTIMES = [
  {
    icon: Globe,
    name: 'Browser WebContainer',
    detail: 'Node 20 runs inside your tab. Vite dev server + Hono API boot in seconds with live preview.',
    status: 'Ready',
    tone: 'primary',
  },
  {
    icon: Server,
    name: 'Nebius build workers',
    detail: 'Isolated containers run installs, type checks and builds on every task boundary.',
    status: 'Online',
    tone: 'secondary',
  },
  {
    icon: Cpu,
    name: 'Checkpoint snapshots',
    detail: 'Every passing build is snapshotted so the room can rewind files, plan and log together.',
    status: 'Enabled',
    tone: 'primary',
  },
] as const;

const TEMPLATE_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  'react-vite': Atom,
  nextjs: Boxes,
  fastapi: FileCode2,
  fullstack: Network,
};

const BOOT_STEPS = [
  { icon: Layers, title: 'Pick a template', text: 'Its prompt pre-fills the room so the agent knows the stack.' },
  { icon: Cpu, title: 'Agent drafts a plan', text: 'The coordinator turns it into tasks the room can edit and approve.' },
  { icon: Terminal, title: 'Sandbox boots', text: 'Node runs in your tab; installs and builds stream into the terminal.' },
  { icon: Rocket, title: 'Preview goes live', text: 'Each passing build becomes a checkpoint you can rewind to.' },
];

const TONES = {
  primary: 'bg-primary/20 text-primary',
  secondary: 'bg-secondary/20 text-secondary',
};

const BUILD_LOG = [
  { t: '14:07:02', text: '$ npm install --prefer-offline', cls: 'text-on-surface' },
  { t: '14:07:09', text: 'added 212 packages in 6.8s', cls: 'text-outline' },
  { t: '14:07:09', text: '$ tsc --noEmit', cls: 'text-on-surface' },
  { t: '14:07:12', text: '0 errors', cls: 'text-outline' },
  { t: '14:07:12', text: '$ vite build', cls: 'text-on-surface' },
  { t: '14:07:16', text: '✓ 48 modules transformed · dist/ 142 kB', cls: 'text-outline' },
  { t: '14:07:16', text: 'run_build passed · 14.2s · built on Nebius', cls: 'text-primary' },
  { t: '14:07:16', text: 'checkpoint 4 created · snapshot 7f3a…e21', cls: 'text-secondary' },
];

const LINE_MS = 650;
const HOLD_LINES = 6; // pause (in line-steps) on the finished log before replaying

export default function SandboxPage() {
  const user = useRequireAuth();

  // Stream the build log one line at a time, then replay it
  const [step, setStep] = useState(0);
  useEffect(() => {
    if (prefersReducedMotion()) {
      setStep(BUILD_LOG.length);
      return;
    }
    const id = setInterval(() => setStep(s => (s >= BUILD_LOG.length + HOLD_LINES ? 0 : s + 1)), LINE_MS);
    return () => clearInterval(id);
  }, []);
  const shownLines = Math.min(step, BUILD_LOG.length);
  const finished = shownLines === BUILD_LOG.length;

  const router = useRouter();
  const [runtime, setRuntime] = useState<'all' | 'node' | 'python'>('all');
  const templates = STARTER_TEMPLATES.filter(t => runtime === 'all' || t.runtime === runtime);

  const openDemo = () => {
    setDemoMode(true);
    router.push('/room/demo-yoga');
  };

  // Signed-in only: render nothing until the session is confirmed (or while redirecting to /login)
  if (!user) return <div className="min-h-screen bg-surface" />;

  const buildLog = (
    <div className="overflow-hidden rounded-xl border border-white/10 bg-[#010409] shadow-[0_30px_80px_-30px_rgba(59,130,246,0.5)]">
      <div className="flex items-center justify-between border-b border-white/5 px-3 py-2">
        <div className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full bg-[#f85149]/70" />
          <span className="h-2.5 w-2.5 rounded-full bg-[#d29922]/70" />
          <span className="h-2.5 w-2.5 rounded-full bg-[#3fb950]/70" />
          <span className="ml-2 font-code text-[11px] text-outline">build · lotus-yoga</span>
        </div>
        {finished ? (
          <span key="passed" className="item-in flex items-center gap-space-xs font-code text-code-sm text-primary">
            <span className="h-2 w-2 rounded-full bg-primary" />
            passed · 14.2s
          </span>
        ) : (
          <span key="running" className="flex items-center gap-space-xs font-code text-code-sm text-secondary">
            <span className="h-3 w-3 animate-spin rounded-full border-[1.5px] border-secondary border-t-transparent" />
            running…
          </span>
        )}
      </div>
      <pre className="min-h-[248px] overflow-x-auto p-space-md font-code text-code-sm leading-7" aria-live="off">
        {BUILD_LOG.slice(0, shownLines).map((line, i) => (
          <div key={i} className="item-in">
            <span className="mr-space-md text-outline/60">{line.t}</span>
            <span className={line.cls}>{line.text}</span>
          </div>
        ))}
        {!finished && <span className="caret" />}
      </pre>
      <div className="h-0.5 bg-white/5">
        <div className="h-full bg-gradient-to-r from-primary to-secondary transition-[width] duration-500" style={{ width: `${(shownLines / BUILD_LOG.length) * 100}%` }} />
      </div>
    </div>
  );

  const hero = (
    <PageHero
      badge={<><Terminal className="h-4 w-4" /> Sandbox · {STARTER_TEMPLATES.length} starter templates</>}
      title={<>Instant <span className="text-shimmer">sandboxes</span></>}
      lead="Pick a starter and MUX spins up a room with a running sandbox, a live preview and an agent ready to build."
      aside={buildLog}
    >
      <div className="flex flex-wrap items-center gap-space-sm">
        <Link href="/dashboard?new=1" className={BTN_PRIMARY}>
          <PlusCircle className="h-4 w-4" /> Blank room
        </Link>
        <button type="button" onClick={openDemo} className={BTN_GHOST}>
          <PlayCircle className="h-4 w-4" /> Open the sample room
        </button>
      </div>
    </PageHero>
  );

  return (
    <AppShell active="sandbox" hero={hero}>
      {/* Templates */}
      <div className="mb-space-lg flex flex-wrap items-end justify-between gap-space-md">
        <div>
          <span className="font-code text-[11px] uppercase tracking-[0.18em] text-outline">01 · Templates</span>
          <h2 className="font-headline text-2xl font-bold tracking-tight md:text-3xl">Start from a stack</h2>
        </div>
        <div className="flex gap-1.5">
          {(['all', 'node', 'python'] as const).map(r => (
            <FilterChip key={r} on={runtime === r} onClick={() => setRuntime(r)}>
              {r === 'all' ? 'All' : r === 'node' ? 'Node' : 'Python'}
            </FilterChip>
          ))}
        </div>
      </div>
      <div className="mb-20 grid grid-cols-1 gap-space-lg md:grid-cols-2">
        {templates.map((template, i) => {
          const Icon = TEMPLATE_ICONS[template.id] ?? Layers;
          return (
            <Reveal key={template.id} delay={i * 90} className="h-full">
            <Spotlight className="group flex h-full flex-col justify-between rounded-xl border border-white/10 bg-surface-container/70 p-space-lg backdrop-blur transition-all duration-300 hover:-translate-y-1 hover:border-primary/40 hover:bg-surface-container">
              <div>
                <div className="mb-space-md flex items-start justify-between">
                  <IconTile icon={Icon} />
                  <span className="rounded-full border border-white/10 px-space-sm py-0.5 font-code text-code-sm uppercase text-on-surface-variant">
                    {template.runtime}
                  </span>
                </div>
                <h3 className="mb-space-xs font-headline text-headline-md text-on-surface transition-colors group-hover:text-primary">
                  {template.name}
                </h3>
                <p className="mb-space-md text-body-md text-on-surface-variant">{template.summary}</p>
                <div className="mb-space-lg flex flex-wrap gap-space-xs">
                  {template.stack.map(item => (
                    <span key={item} className="rounded bg-white/[0.06] px-1.5 py-0.5 font-code text-code-sm text-secondary">
                      {item}
                    </span>
                  ))}
                </div>
              </div>
              <div className="flex items-center justify-between gap-space-md border-t border-white/5 pt-space-md">
                <span className="truncate font-code text-code-sm text-outline">{template.prompt}</span>
                <Link
                  href={`/dashboard?template=${template.id}`}
                  className="flex flex-none items-center gap-space-xs rounded-lg px-space-sm py-1 text-body-sm text-primary transition-colors hover:bg-primary/10"
                >
                  Launch room
                  <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-1" />
                </Link>
              </div>
            </Spotlight>
            </Reveal>
          );
        })}
      </div>

      {/* How it boots */}
      <Reveal>
        <span className="font-code text-[11px] uppercase tracking-[0.18em] text-outline">02 · Lifecycle</span>
        <h2 className="mb-space-lg font-headline text-2xl font-bold tracking-tight md:text-3xl">From template to live preview</h2>
      </Reveal>
      <div className="mb-20 grid grid-cols-1 gap-space-md sm:grid-cols-2 lg:grid-cols-4">
        {BOOT_STEPS.map((step, i) => (
          <Reveal key={step.title} delay={i * 90} className="h-full">
            <div className={`group relative h-full ${CARD} p-space-lg transition-all duration-300 hover:-translate-y-0.5 hover:border-primary/40`}>
              <span className="absolute right-space-md top-space-md font-code text-code-sm text-outline/60">{String(i + 1).padStart(2, '0')}</span>
              <IconTile icon={step.icon} size="sm" />
              <h3 className="mb-1 mt-space-md font-headline text-headline-sm text-on-surface">{step.title}</h3>
              <p className="text-body-sm text-on-surface-variant">{step.text}</p>
            </div>
          </Reveal>
        ))}
      </div>

      {/* Runtimes */}
      <Reveal>
        <span className="font-code text-[11px] uppercase tracking-[0.18em] text-outline">03 · Runtimes</span>
        <h2 className="mb-space-lg font-headline text-2xl font-bold tracking-tight md:text-3xl">What your room runs on</h2>
      </Reveal>
      <div className="mb-20 grid grid-cols-1 gap-space-md md:grid-cols-3">
        {RUNTIMES.map((rt, i) => (
          <Reveal key={rt.name} delay={i * 90} className="h-full">
            <div className={`group h-full ${CARD} p-space-lg transition-all duration-300 hover:-translate-y-0.5 hover:border-primary/40`}>
              <div className="mb-space-md flex items-center justify-between">
                <IconTile icon={rt.icon} size="sm" />
                <span className={`flex items-center gap-1.5 rounded-full px-space-sm py-0.5 font-code text-code-sm ${TONES[rt.tone]}`}>
                  <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-current" />
                  {rt.status}
                </span>
              </div>
              <h3 className="mb-1 font-headline text-headline-sm text-on-surface">{rt.name}</h3>
              <p className="text-body-sm text-on-surface-variant">{rt.detail}</p>
            </div>
          </Reveal>
        ))}
      </div>

      <Reveal>
        <CtaCard title="Have something else in mind?" text="Describe it in a sentence and the agent will pick the stack for you.">
          <Link href="/dashboard?new=1" className={BTN_PRIMARY}>
            <PlusCircle className="h-4 w-4" /> Create a room
          </Link>
          <Link href="/docs#code" className={BTN_GHOST}>
            <Terminal className="h-4 w-4" /> Learn the Code tab
          </Link>
        </CtaCard>
      </Reveal>
    </AppShell>
  );
}
