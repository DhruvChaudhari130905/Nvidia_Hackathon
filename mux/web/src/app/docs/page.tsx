'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import {
  BookOpen, Search, ArrowRight, ArrowLeft, LayoutPanelLeft, Tags, Vote, MessageCircleQuestion, ListChecks, Code2,
  History, Gauge, Users, Github, Check, ThumbsUp, ThumbsDown, PlayCircle, PlusCircle, Keyboard, X,
} from 'lucide-react';
import { ShaderBackground, SiteHeader, SiteFooter, useInView, HeroBackdrop, HERO_TITLE, trackHeroSpot } from '@/components/shell';
import { setDemoMode } from '@/lib/demo';
import {
  BudgetDial, ExportPipeline, LabelPlayground, PlanLifecycle, QuestionCountdown, RewindSlider, RolesMatrix, RoomDiagram, VoteSimulator,
} from '@/components/docs/Widgets';

// Docs: an interactive guide to a MUX room. Each section has a live demo you can play with.

interface Section {
  id: string;
  group: string;
  title: string;
  icon: React.ComponentType<{ className?: string }>;
  keywords: string;
  lead: string;
  body: React.ReactNode;
  demo?: React.ReactNode;
}

function Code({ children }: { children: React.ReactNode }) {
  return <code className="rounded bg-white/[0.06] px-1.5 py-0.5 font-code text-code-sm text-secondary">{children}</code>;
}

function Kbd({ children }: { children: React.ReactNode }) {
  return <kbd className="rounded border border-white/15 bg-white/[0.04] px-1.5 py-0.5 font-code text-[11px] text-on-surface shadow-[inset_0_-1px_0_rgba(255,255,255,0.08)]">{children}</kbd>;
}

const TERMINAL_COMMANDS: [string, string][] = [
  ['npm install', 'Install the project’s dependencies for real'],
  ['npm install <pkg>', 'Add a package (updates package.json)'],
  ['npm run dev / build / test', 'Run any package.json script'],
  ['npx <tool>', 'Run a package binary, e.g. npx tsc --noEmit'],
  ['node script.js', 'Run a file with Node.js'],
  ['ls · cd · cat · mkdir · rm · mv · cp', 'Shell commands on the room’s files'],
];

const EDITOR_KEYS: [string, string][] = [
  ['⌘ S', 'Save (formats first)'],
  ['⇧ ⌥ F', 'Format document'],
  ['⌘ P', 'Quick open a file'],
  ['⌘ ⇧ P', 'Command palette'],
  ['Ctrl `', 'Toggle terminal'],
  ['⌘ F', 'Find in file'],
];

const SECTIONS: Section[] = [
  {
    id: 'rooms',
    group: 'Getting started',
    title: 'Rooms',
    icon: LayoutPanelLeft,
    keywords: 'room layout feed preview code timeline top bar create',
    lead: 'One shared workspace where up to eight people steer and one agent builds.',
    body: (
      <p>
        A coordinator agent reads every message and keeps the plan straight; a coder agent writes the code and runs the builds.
        Create a room from <Link href="/dashboard?new=1" className="text-primary hover:underline">Rooms</Link> or start from a template in the{' '}
        <Link href="/sandbox" className="text-primary hover:underline">Sandbox</Link>.
      </p>
    ),
    demo: <RoomDiagram />,
  },
  {
    id: 'labels',
    group: 'Getting started',
    title: 'Message labels',
    icon: Tags,
    keywords: 'merge queue interrupt conflict chat coordinator message label',
    lead: 'Every message gets a label, so the whole room can see how it will be handled.',
    body: <p>Type something below and watch the label change. The coder only acts on labelled messages at safe turn boundaries, so nothing half-finished gets clobbered.</p>,
    demo: <LabelPlayground />,
  },
  {
    id: 'conflicts',
    group: 'Collaborating',
    title: 'Conflicts & votes',
    icon: Vote,
    keywords: 'vote conflict override owner weight domain design eng pm evidence',
    lead: 'When two requests clash, the room votes — and the coder keeps building everything else.',
    body: (
      <p>
        Every editor gets a vote. The domain owner counts 2× — design for UI, engineering for architecture, PM for scope. The room owner can close any vote with an override.
        The result is pinned to the room log and applied at the next task boundary. Click the voters to change their picks.
      </p>
    ),
    demo: <VoteSimulator />,
  },
  {
    id: 'questions',
    group: 'Collaborating',
    title: 'Agent questions',
    icon: MessageCircleQuestion,
    keywords: 'question ask default timeout answer',
    lead: 'When the agent needs a decision, it asks — with a sensible default so the build never stalls.',
    body: <p>Answer before the timer runs out, or let it expire and watch the default kick in. Answers reach the coder as a merge.</p>,
    demo: <QuestionCountdown />,
  },
  {
    id: 'plan',
    group: 'Collaborating',
    title: 'The plan',
    icon: ListChecks,
    keywords: 'plan task approve draft todo doing done skipped',
    lead: 'A shared, editable task list the coder works through top to bottom.',
    body: <p>Draft plans can be reworded, reordered and extended by anyone with edit access. Once approved, each task moves through its lifecycle — click a stage to see what it means.</p>,
    demo: <PlanLifecycle />,
  },
  {
    id: 'code',
    group: 'Building',
    title: 'The Code tab',
    icon: Code2,
    keywords: 'code editor terminal format explorer file upload shortcuts problems quick open palette',
    lead: 'A full editor in the room: explorer, tabs, a Format button, a terminal and a problems list.',
    body: (
      <p>
        Create, upload, rename or delete files from the explorer (or drop files onto it). The Format button (⇧⌥F) tidies the open file; syntax errors show up in Problems, and{' '}
        <Code>npm run build</Code> fails while any remain.
      </p>
    ),
    demo: (
      <div className="grid gap-space-md lg:grid-cols-[1.4fr_1fr]">
        <div className="overflow-hidden rounded-xl border border-white/10 bg-[#010409]">
          <div className="flex items-center gap-1.5 border-b border-white/5 px-3 py-2">
            <span className="h-2.5 w-2.5 rounded-full bg-[#f85149]/70" />
            <span className="h-2.5 w-2.5 rounded-full bg-[#d29922]/70" />
            <span className="h-2.5 w-2.5 rounded-full bg-[#3fb950]/70" />
            <span className="ml-2 font-code text-[11px] text-outline">terminal</span>
          </div>
          <div className="divide-y divide-white/5">
            {TERMINAL_COMMANDS.map(([cmd, what]) => (
              <div key={cmd} className="group flex items-center justify-between gap-space-md px-3 py-1.5 transition-colors hover:bg-white/[0.03]">
                <span className="font-code text-code-sm"><span className="text-[#3fb950]">$ </span><span className="text-on-surface">{cmd}</span></span>
                <span className="text-right text-body-sm text-outline transition-colors group-hover:text-on-surface-variant">{what}</span>
              </div>
            ))}
          </div>
        </div>
        <div className="rounded-xl border border-white/10 bg-surface-container-lowest/70 p-space-md">
          <p className="mb-space-sm flex items-center gap-2 font-code text-label-md uppercase tracking-wider text-secondary"><Keyboard className="h-4 w-4" /> Shortcuts</p>
          <div className="space-y-2">
            {EDITOR_KEYS.map(([k, what]) => (
              <div key={k} className="flex items-center justify-between gap-2 text-body-sm">
                <span className="text-on-surface-variant">{what}</span>
                <Kbd>{k}</Kbd>
              </div>
            ))}
          </div>
          <p className="mt-space-md text-[11px] text-outline">The terminal is a real shell running Node.js in your browser (WebContainers). Files it creates or changes sync back to the room; node_modules and build output stay in the terminal. Browsers that can’t run WebContainers get a simulated shell instead.</p>
        </div>
      </div>
    ),
  },
  {
    id: 'checkpoints',
    group: 'Building',
    title: 'Checkpoints & rewind',
    icon: History,
    keywords: 'checkpoint rewind timeline undo history snapshot',
    lead: 'Every passing build is a checkpoint you can travel back to.',
    body: <p>Rewinding reverts files, plan and log together. Later work is greyed out, not deleted — drag the slider to try it.</p>,
    demo: <RewindSlider />,
  },
  {
    id: 'budget',
    group: 'Building',
    title: 'Budget',
    icon: Gauge,
    keywords: 'budget tokens builds cap limit meter',
    lead: 'Each room has a token and build budget, always visible in the top bar.',
    body: <p>The meter changes colour as you use it up. Owners can raise the caps at any time.</p>,
    demo: <BudgetDial />,
  },
  {
    id: 'sharing',
    group: 'Sharing',
    title: 'Sharing & roles',
    icon: Users,
    keywords: 'share invite link owner editor viewer permission role access',
    lead: 'Rooms are private by default. Invite people as editors or viewers, or share a link.',
    body: (
      <p>
        Switch the link to <Code>anyone with the link</Code> as editor or viewer from the room’s Share dialog. Pick a role to see what it can do.
      </p>
    ),
    demo: <RolesMatrix />,
  },
  {
    id: 'export',
    group: 'Sharing',
    title: 'GitHub export',
    icon: Github,
    keywords: 'github export repository repo push public private',
    lead: 'When you like what you see, turn the room into a real repository.',
    body: (
      <p>
        The owner clicks <Code>Export to GitHub</Code> in the room’s top bar, picks a name and public or private, and the current checkpoint is pushed to a new repo.
      </p>
    ),
    demo: <ExportPipeline />,
  },
];

const GROUPS = Array.from(new Set(SECTIONS.map(s => s.group)));

function SectionBlock({ s, index, prev, next, onSeen }: { s: Section; index: number; prev?: Section; next?: Section; onSeen: (id: string) => void }) {
  const [ref, inView] = useInView<HTMLElement>('0px 0px -35% 0px');
  const [feedback, setFeedback] = useState<'up' | 'down' | null>(null);
  const Icon = s.icon;

  useEffect(() => {
    if (inView) onSeen(s.id);
  }, [inView, onSeen, s.id]);

  return (
    <section ref={ref} id={s.id} className={`reveal ${inView ? 'in' : ''} scroll-mt-28`}>
      <div className="mb-space-md flex items-center gap-space-md">
        <span className="grid h-11 w-11 flex-none place-items-center rounded-xl bg-gradient-to-br from-primary/30 to-secondary/20 text-secondary ring-1 ring-white/10">
          <Icon className="h-5 w-5" />
        </span>
        <div>
          <span className="font-code text-[11px] uppercase tracking-[0.18em] text-outline">{String(index + 1).padStart(2, '0')} · {s.group}</span>
          <h2 className="font-headline text-2xl font-bold tracking-tight text-on-surface md:text-3xl">{s.title}</h2>
        </div>
      </div>
      <p className="mb-space-sm text-body-lg text-on-surface">{s.lead}</p>
      <div className="mb-space-lg text-body-md leading-7 text-on-surface-variant">{s.body}</div>
      {s.demo && (
        <div className="relative">
          <span className="absolute -top-2.5 left-4 z-10 rounded-full bg-surface px-2 font-code text-[10px] uppercase tracking-[0.2em] text-secondary">Try it</span>
          {s.demo}
        </div>
      )}
      <div className="mt-space-lg flex flex-wrap items-center justify-between gap-space-md border-t border-white/5 pt-space-md">
        <div className="flex items-center gap-2 text-body-sm text-outline">
          {feedback ? (
            <span className="item-in text-primary">Thanks for the feedback!</span>
          ) : (
            <>
              Was this helpful?
              <button type="button" onClick={() => setFeedback('up')} className="grid h-7 w-7 place-items-center rounded-full transition-all hover:scale-110 hover:bg-white/10 hover:text-primary" aria-label="Helpful"><ThumbsUp className="h-3.5 w-3.5" /></button>
              <button type="button" onClick={() => setFeedback('down')} className="grid h-7 w-7 place-items-center rounded-full transition-all hover:scale-110 hover:bg-white/10 hover:text-conflict" aria-label="Not helpful"><ThumbsDown className="h-3.5 w-3.5" /></button>
            </>
          )}
        </div>
        <div className="flex gap-space-sm">
          {prev && (
            <a href={`#${prev.id}`} className="group flex items-center gap-1.5 rounded-lg px-space-sm py-1 text-body-sm text-on-surface-variant transition-colors hover:bg-white/5 hover:text-on-surface">
              <ArrowLeft className="h-3.5 w-3.5 transition-transform group-hover:-translate-x-0.5" /> {prev.title}
            </a>
          )}
          {next && (
            <a href={`#${next.id}`} className="group flex items-center gap-1.5 rounded-lg px-space-sm py-1 text-body-sm text-primary transition-colors hover:bg-primary/10">
              {next.title} <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" />
            </a>
          )}
        </div>
      </div>
    </section>
  );
}

export default function DocsPage() {
  const router = useRouter();
  const [current, setCurrent] = useState(SECTIONS[0].id);
  const [read, setRead] = useState<Set<string>>(new Set());
  const [progress, setProgress] = useState(0);
  const [query, setQuery] = useState('');
  const searchRef = useRef<HTMLInputElement>(null);

  const markSeen = useMemo(() => (id: string) => setRead(prev => (prev.has(id) ? prev : new Set(prev).add(id))), []);

  // Reading progress bar + which section is current
  useEffect(() => {
    const onScroll = () => {
      const max = document.documentElement.scrollHeight - window.innerHeight;
      setProgress(max > 0 ? Math.min(1, window.scrollY / max) : 0);
      let cur = SECTIONS[0].id;
      for (const s of SECTIONS) {
        const el = document.getElementById(s.id);
        if (el && el.getBoundingClientRect().top < window.innerHeight * 0.35) cur = s.id;
      }
      setCurrent(cur);
    };
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  // ⌘K or "/" focuses search
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const typing = (e.target as HTMLElement)?.matches?.('input, textarea');
      if ((e.key.toLowerCase() === 'k' && (e.metaKey || e.ctrlKey)) || (e.key === '/' && !typing)) {
        e.preventDefault();
        searchRef.current?.focus();
        searchRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const q = query.trim().toLowerCase();
  const visible = q ? SECTIONS.filter(s => `${s.title} ${s.keywords} ${s.lead}`.toLowerCase().includes(q)) : SECTIONS;

  const openDemo = () => {
    setDemoMode(true);
    router.push('/room/demo-yoga');
  };

  const quickStart = [
    { icon: PlayCircle, title: 'Explore a sample room', text: 'Jump into Lotus Yoga with votes, questions and a live preview.', action: openDemo },
    { icon: PlusCircle, title: 'Create your own room', text: 'Describe an idea and get a blank room with a plan.', href: '/dashboard?new=1' },
    { icon: Code2, title: 'Learn the Code tab', text: 'Editor, formatting, terminal and shortcuts.', href: '#code' },
  ];

  return (
    <div className="relative flex min-h-screen flex-col bg-surface font-ui text-body-md text-on-surface">
      <ShaderBackground className="fixed inset-0 z-0 opacity-20" />
      <SiteHeader active="docs" />
      <div className="fixed left-0 right-0 top-16 z-40 h-0.5" aria-hidden="true">
        <div className="h-full origin-left bg-gradient-to-r from-primary to-secondary shadow-[0_0_10px_rgba(6,182,212,0.7)]" style={{ transform: `scaleX(${progress})` }} />
      </div>

      <main className="relative z-10 w-full flex-1 pt-16">
        {/* Hero */}
        <section onPointerMove={trackHeroSpot} className="relative isolate overflow-hidden px-gutter pb-16 pt-16 md:px-space-xl md:pt-20">
          <HeroBackdrop />

          <div className="relative mx-auto grid max-w-6xl items-center gap-space-xl lg:grid-cols-[1.25fr_1fr]">
            <div className="hero-in">
              <div className="mb-space-lg inline-flex items-center gap-space-sm rounded-full border border-white/10 bg-surface-container/70 px-space-md py-space-xs text-label-md text-on-surface-variant backdrop-blur-md">
                <BookOpen className="h-4 w-4 text-secondary" /> {SECTIONS.length} interactive guides
              </div>
              <h1 className={`mb-space-lg text-balance ${HERO_TITLE}`}>How a MUX room works</h1>
              <p className="mb-space-xl max-w-xl text-pretty font-headline text-lg leading-relaxed text-on-surface-variant">
                Eight people steering, one agent building. Every guide below has a live demo — click, type and drag to see it happen.
              </p>
              <div className="group relative max-w-xl">
                <div className="pointer-events-none absolute -inset-px rounded-xl bg-gradient-to-r from-primary/60 to-secondary/60 opacity-0 blur transition-opacity duration-300 group-focus-within:opacity-100" />
                <div className="relative flex items-center gap-space-sm rounded-xl border border-white/10 bg-surface-container-lowest px-space-md">
                  <Search className="h-4 w-4 text-outline" />
                  <input
                    ref={searchRef}
                    value={query}
                    onChange={e => setQuery(e.target.value)}
                    onKeyDown={e => {
                      if (e.key === 'Escape') setQuery('');
                      if (e.key === 'Enter' && visible[0]) document.getElementById(visible[0].id)?.scrollIntoView({ behavior: 'smooth' });
                    }}
                    placeholder="Search the docs — try “vote”, “terminal” or “rewind”"
                    className="min-w-0 flex-1 bg-transparent py-3 text-body-md text-on-surface outline-none placeholder:text-outline"
                    aria-label="Search the docs"
                  />
                  {query ? (
                    <button type="button" onClick={() => setQuery('')} className="text-outline hover:text-on-surface" aria-label="Clear search"><X className="h-4 w-4" /></button>
                  ) : (
                    <span className="hidden gap-1 sm:flex"><Kbd>⌘</Kbd><Kbd>K</Kbd></span>
                  )}
                </div>
              </div>
              <div className="mt-space-sm flex flex-wrap gap-1.5">
                {['vote', 'terminal', 'rewind', 'export', 'roles'].map(t => (
                  <button key={t} type="button" onClick={() => setQuery(t)} className="rounded-full border border-white/10 px-2.5 py-0.5 font-code text-code-sm text-outline transition-colors hover:border-primary/40 hover:text-on-surface">
                    {t}
                  </button>
                ))}
              </div>
            </div>

            <div className="space-y-space-sm">
              {quickStart.map((c, i) => {
                const Icon = c.icon;
                const inner = (
                  <>
                    <span className="grid h-10 w-10 flex-none place-items-center rounded-lg bg-gradient-to-br from-primary to-secondary text-white shadow-[0_8px_24px_-8px_rgba(59,130,246,0.8)] transition-transform duration-300 group-hover:rotate-6 group-hover:scale-110">
                      <Icon className="h-5 w-5" />
                    </span>
                    <span className="min-w-0 flex-1 text-left">
                      <span className="block font-headline text-headline-sm text-on-surface">{c.title}</span>
                      <span className="block text-body-sm text-on-surface-variant">{c.text}</span>
                    </span>
                    <ArrowRight className="h-4 w-4 flex-none text-outline transition-all group-hover:translate-x-1 group-hover:text-primary" />
                  </>
                );
                const cls = 'group flex w-full items-center gap-space-md rounded-xl border border-white/10 bg-surface-container/70 p-space-md backdrop-blur transition-all duration-300 hover:-translate-y-0.5 hover:border-primary/40 hover:bg-surface-container animate-fade-up';
                return c.href ? (
                  <Link key={c.title} href={c.href} className={cls} style={{ animationDelay: `${120 + i * 90}ms` }}>{inner}</Link>
                ) : (
                  <button key={c.title} type="button" onClick={c.action} className={cls} style={{ animationDelay: `${120 + i * 90}ms` }}>{inner}</button>
                );
              })}
            </div>
          </div>
        </section>

        <div className="mx-auto grid w-full max-w-6xl grid-cols-1 gap-space-xl px-gutter pb-24 md:grid-cols-[230px_minmax(0,1fr)] md:px-space-xl">
          {/* Sidebar */}
          <nav className="md:sticky md:top-24 md:self-start" aria-label="Docs sections">
            <div className="rounded-xl border border-white/10 bg-surface-container-low/80 p-space-sm backdrop-blur">
              <div className="mb-space-sm flex items-center justify-between px-space-sm pt-space-xs">
                <span className="font-code text-label-md uppercase tracking-wider text-outline">Guides</span>
                <span className="font-code text-code-sm tabular-nums text-secondary">{read.size}/{SECTIONS.length} read</span>
              </div>
              <div className="mx-space-sm mb-space-md h-1 overflow-hidden rounded-full bg-white/5">
                <div className="h-full rounded-full bg-gradient-to-r from-primary to-secondary transition-[width] duration-500" style={{ width: `${(read.size / SECTIONS.length) * 100}%` }} />
              </div>
              {GROUPS.map(g => (
                <div key={g} className="mb-space-sm">
                  <div className="px-space-sm pb-1 font-code text-[10.5px] uppercase tracking-[0.15em] text-outline/70">{g}</div>
                  {SECTIONS.filter(s => s.group === g).map(s => {
                    const Icon = s.icon;
                    const on = current === s.id;
                    const hidden = q && !visible.includes(s);
                    return (
                      <a
                        key={s.id}
                        href={`#${s.id}`}
                        className={`relative flex items-center gap-2 rounded-md px-space-sm py-1.5 text-body-md transition-all ${hidden ? 'opacity-30' : ''} ${
                          on ? 'bg-white/[0.06] text-on-surface' : 'text-on-surface-variant hover:bg-white/[0.03] hover:text-on-surface'
                        }`}
                      >
                        {on && <span className="absolute bottom-1.5 left-0 top-1.5 w-0.5 rounded-full bg-gradient-to-b from-primary to-secondary" />}
                        <Icon className={`h-3.5 w-3.5 flex-none ${on ? 'text-secondary' : ''}`} />
                        <span className="flex-1 truncate">{s.title}</span>
                        {read.has(s.id) && <Check className="item-in h-3.5 w-3.5 flex-none text-primary" />}
                      </a>
                    );
                  })}
                </div>
              ))}
            </div>
          </nav>

          {/* Content */}
          <div className="space-y-20">
            {q && visible.length > 0 && (
              <p className="item-in font-code text-code-sm text-outline">
                {visible.length} guide{visible.length === 1 ? '' : 's'} match “{query}”
              </p>
            )}
            {visible.length === 0 && (
              <div className="item-in rounded-xl border border-white/10 bg-surface-container/70 p-space-xl text-center">
                <Search className="mx-auto mb-space-sm h-8 w-8 text-outline" />
                <p className="mb-space-sm text-body-lg text-on-surface">Nothing matches “{query}”</p>
                <button type="button" onClick={() => setQuery('')} className="text-body-md text-primary hover:underline">Show all guides</button>
              </div>
            )}
            {visible.map(s => {
              const i = SECTIONS.indexOf(s);
              return <SectionBlock key={s.id} s={s} index={i} prev={SECTIONS[i - 1]} next={SECTIONS[i + 1]} onSeen={markSeen} />;
            })}

            {!q && (
              <div className="relative overflow-hidden rounded-2xl border border-white/10 bg-gradient-to-br from-primary/15 via-surface-container to-secondary/10 p-space-xl text-center">
                <div className="float-slow pointer-events-none absolute -right-10 -top-10 h-48 w-48 rounded-full bg-secondary/20 blur-3xl" />
                <h3 className="relative mb-space-sm font-headline text-2xl font-bold">You’ve got the whole picture.</h3>
                <p className="relative mb-space-lg text-body-md text-on-surface-variant">Now watch it all come together in a real room.</p>
                <div className="relative flex flex-wrap justify-center gap-space-sm">
                  <button type="button" onClick={openDemo} className="btn-shine flex items-center gap-space-sm rounded-full bg-primary px-space-lg py-space-sm text-label-md font-bold text-white transition-all hover:shadow-[0_0_25px_rgba(59,130,246,0.6)]">
                    <PlayCircle className="h-4 w-4" /> Open the sample room
                  </button>
                  <Link href="/dashboard?new=1" className="flex items-center gap-space-sm rounded-full border border-white/15 px-space-lg py-space-sm text-label-md text-on-surface transition-colors hover:border-primary/50">
                    <PlusCircle className="h-4 w-4" /> Create a room
                  </Link>
                </div>
              </div>
            )}
          </div>
        </div>
      </main>

      <SiteFooter />
    </div>
  );
}
