'use client';

import React, { useEffect, useState } from 'react';
import { Check, GitBranch, GitPullRequest, GitMerge, Terminal } from 'lucide-react';

// Live mini-demos shown on each feature page. They only animate while their page is active.

// Cycles 0..steps-1 every `ms` while active; resets to 0 when the page becomes active again
function useStepper(active: boolean, ms: number, steps: number) {
  const [step, setStep] = useState(0);
  useEffect(() => {
    if (!active) return;
    setStep(0);
    const id = setInterval(() => setStep(s => (s + 1) % steps), ms);
    return () => clearInterval(id);
  }, [active, ms, steps]);
  return step;
}

const frame = 'relative w-full max-w-xl overflow-hidden rounded-2xl bg-surface-container-lowest/80 shadow-[0_40px_100px_-30px_rgba(59,130,246,0.45)] ring-1 ring-white/5 backdrop-blur-xl';
const titleBar = (label: string) => (
  <div className="flex items-center gap-2 border-b border-white/5 px-4 py-3">
    <span className="h-2.5 w-2.5 rounded-full bg-[#f85149]/70" />
    <span className="h-2.5 w-2.5 rounded-full bg-[#d29922]/70" />
    <span className="h-2.5 w-2.5 rounded-full bg-[#3fb950]/70" />
    <span className="ml-3 font-code text-code-sm text-outline">{label}</span>
  </div>
);

/* 1 · Live sync: teammates' cursors moving through the same file */
const CODE_LINES = [
  'export function ClassCard({ c }: Props) {',
  '  const [booked, setBooked] = useState(false);',
  '  return (',
  '    <div className="rounded-lg border p-4">',
  '      <h3>{c.title}</h3>',
  '      <p>{c.day} · {c.teacher}</p>',
  '      <button onClick={() => setBooked(true)}>',
  '        {booked ? "Booked" : "Book"}',
  '      </button>',
  '    </div>',
  '  );',
  '}',
];
const CURSORS = [
  { name: 'Dan', color: '#3b82f6', path: [[4, 22], [5, 12], [6, 30], [7, 18], [4, 38]] },
  { name: 'Priya', color: '#06b6d4', path: [[1, 30], [1, 16], [8, 8], [9, 6], [2, 10]] },
  { name: 'MUX', color: '#a371f7', path: [[6, 14], [7, 26], [5, 24], [3, 20], [6, 42]] },
];

export function LiveSyncVisual({ active }: { active: boolean }) {
  const step = useStepper(active, 1300, 5);
  return (
    <div className={frame}>
      {titleBar('src/components/ClassCard.tsx · 3 editing')}
      <div className="relative p-5 font-code text-[12.5px] leading-[1.7rem]">
        {CODE_LINES.map((line, i) => (
          <div key={i} className="flex whitespace-pre">
            <span className="w-8 select-none text-outline/40">{i + 1}</span>
            <span className={i === CURSORS[2].path[step][0] ? 'text-on-surface' : 'text-on-surface-variant'}>{line}</span>
          </div>
        ))}
        {CURSORS.map(c => {
          const [line, col] = c.path[step];
          return (
            <div
              key={c.name}
              className="pointer-events-none absolute transition-all duration-700 ease-[cubic-bezier(.2,.8,.2,1)]"
              style={{ top: `calc(1.25rem + ${line} * 1.7rem)`, left: `calc(1.25rem + 2rem + ${col}ch)` }}
            >
              <span className="block h-[1.4rem] w-[2px] animate-pulse" style={{ background: c.color }} />
              <span
                className="absolute -top-5 left-0 whitespace-nowrap rounded px-1.5 py-0.5 font-ui text-[10px] font-semibold text-white shadow-lg"
                style={{ background: c.color }}
              >
                {c.name}
              </span>
            </div>
          );
        })}
      </div>
      <div className="flex items-center justify-between border-t border-white/5 px-4 py-2 font-code text-[11px] text-outline">
        <span>synced · {(12 + step * 3) % 40} ops/s</span>
        <span className="text-primary">● 0.2s latency</span>
      </div>
    </div>
  );
}

/* 2 · Voting: a conflict vote fills up, closes, and is applied */
const VOTERS = [
  { initials: 'DA', color: '#9ad0f5', option: 0 },
  { initials: 'PR', color: '#f0a3c4', option: 1 },
  { initials: 'MA', color: '#c7e59a', option: 0 },
  { initials: 'SA', color: '#d6c7ff', option: 0 },
];

export function VotingVisual({ active }: { active: boolean }) {
  const step = useStepper(active, 1100, 8); // 0..3 votes arrive, 4..7 decided
  const cast = VOTERS.slice(0, Math.min(step + 1, VOTERS.length));
  const counts = [0, 1].map(o => cast.filter(v => v.option === o).length);
  const decided = step >= 5;
  return (
    <div className={frame}>
      {titleBar('Decisions · task 5')}
      <div className="space-y-4 p-6">
        <div className="flex items-center justify-between">
          <span className="font-code text-[11px] uppercase tracking-[0.15em] text-[#f85149]">Conflict · vote open</span>
          <span className="font-code text-code-sm tabular-nums text-outline">0:{String(Math.max(0, 42 - step * 6)).padStart(2, '0')}</span>
        </div>
        <p className="font-headline text-headline-md text-on-surface">What color should the buttons be?</p>
        {['Blue, match the logo', 'Cyan, feels calmer'].map((label, o) => {
          const pct = cast.length ? (counts[o] / VOTERS.length) * 100 : 0;
          const winner = decided && counts[o] > counts[1 - o];
          return (
            <div key={label} className={`rounded-xl p-3 transition-all duration-500 ${winner ? 'bg-primary/15 ring-1 ring-primary/60' : 'bg-white/[0.03]'}`}>
              <div className="mb-2 flex items-center justify-between text-body-md">
                <span className="text-on-surface">{label}</span>
                <span className="flex items-center gap-2">
                  <span className="flex -space-x-1.5">
                    {cast.filter(v => v.option === o).map(v => (
                      <span key={v.initials} className="item-in grid h-5 w-5 place-items-center rounded-full border border-surface font-code text-[8px] font-bold text-[#0d1117]" style={{ background: v.color }}>
                        {v.initials}
                      </span>
                    ))}
                  </span>
                  <span className="font-code text-code-sm tabular-nums text-outline">{counts[o]}</span>
                </span>
              </div>
              <div className="h-1.5 overflow-hidden rounded-full bg-white/5">
                <div className={`h-full rounded-full transition-[width] duration-700 ${o === 0 ? 'bg-primary' : 'bg-secondary'}`} style={{ width: `${pct}%` }} />
              </div>
            </div>
          );
        })}
        <div className="h-6">
          {decided ? (
            <p key="d" className="item-in flex items-center gap-2 text-body-md text-primary">
              <Check className="h-4 w-4" /> Decided: Blue · applied at next task boundary
            </p>
          ) : (
            <p key="w" className="text-body-sm text-outline">{cast.length} of 4 editors voted · design counts 2×</p>
          )}
        </div>
      </div>
    </div>
  );
}

/* 3 · Sandboxes: container boots, then the live preview slides in */
const BOOT = [
  '$ mux sandbox up --template react-vite',
  '↳ micro-VM allocated · nebius-eu-1',
  '↳ npm install · 212 packages · 6.8s',
  '↳ vite dev server on :5173',
  '✓ preview ready',
];

export function SandboxVisual({ active }: { active: boolean }) {
  const step = useStepper(active, 750, 12);
  const lines = Math.min(step, BOOT.length);
  const ready = step > BOOT.length;
  return (
    <div className="relative w-full max-w-xl">
      <div className={frame}>
        {titleBar('terminal')}
        <div className="min-h-[190px] space-y-1.5 p-5 font-code text-[12.5px]">
          {BOOT.slice(0, lines).map((l, i) => (
            <p key={i} className={`item-in ${l.startsWith('✓') ? 'text-primary' : l.startsWith('$') ? 'text-on-surface' : 'text-outline'}`}>{l}</p>
          ))}
          {!ready && <span className="caret" />}
        </div>
      </div>
      <div
        className={`absolute -bottom-10 -right-4 w-[62%] overflow-hidden rounded-xl bg-[#fbf8f4] text-[#2a2521] shadow-2xl ring-1 ring-black/10 transition-all duration-700 ease-[cubic-bezier(.2,.8,.2,1)] md:-right-10 ${
          ready ? 'translate-y-0 opacity-100' : 'translate-y-10 opacity-0'
        }`}
      >
        <div className="flex items-center gap-1.5 border-b border-[#ece4da] px-3 py-2">
          <span className="h-2 w-2 rounded-full bg-[#ece4da]" />
          <span className="h-2 w-2 rounded-full bg-[#ece4da]" />
          <span className="ml-2 rounded bg-[#f3ede6] px-2 py-0.5 font-code text-[9px] text-[#8a7f74]">localhost:5173</span>
        </div>
        <div className="p-3">
          <p className="mb-2 font-display text-[13px] font-bold">Find your class this week</p>
          <div className="grid grid-cols-2 gap-1.5">
            {['Morning Vinyasa', 'Slow Hatha', 'Yin & Breath', 'Power Flow'].map(t => (
              <div key={t} className="rounded-md border border-[#ece4da] bg-white p-1.5">
                <p className="text-[9px] font-semibold">{t}</p>
                <span className="mt-1 inline-block rounded bg-[#3b82f6] px-1.5 py-0.5 text-[8px] font-semibold text-white">Book</span>
              </div>
            ))}
          </div>
        </div>
      </div>
      <div className="absolute -left-3 -top-3 grid h-10 w-10 place-items-center rounded-xl bg-gradient-to-br from-primary to-secondary text-white shadow-lg">
        <Terminal className="h-5 w-5" />
      </div>
    </div>
  );
}

/* 4 · GitHub export: commits stack up, checks pass, PR merges */
const COMMITS = [
  { msg: 'feat: class schedule grid', who: 'Dan', color: '#9ad0f5' },
  { msg: 'feat: day filter', who: 'MUX', color: '#a371f7' },
  { msg: 'style: blue booking buttons', who: 'Priya', color: '#f0a3c4' },
];

export function GitHubVisual({ active }: { active: boolean }) {
  const step = useStepper(active, 900, 10);
  const shown = Math.min(step + 1, COMMITS.length);
  const checksDone = step >= 5;
  const merged = step >= 7;
  return (
    <div className={frame}>
      {titleBar('github.com/lotus-yoga/booking')}
      <div className="space-y-4 p-6">
        <div className="flex items-center gap-2 font-code text-code-sm text-outline">
          <GitBranch className="h-4 w-4" /> mux/room-lotus-yoga → main
        </div>
        <div className="relative space-y-3 pl-6">
          <span className="absolute bottom-2 left-[7px] top-2 w-px bg-gradient-to-b from-primary to-secondary/20" />
          {COMMITS.slice(0, shown).map(c => (
            <div key={c.msg} className="item-in relative flex items-center gap-3">
              <span className="absolute -left-6 top-1/2 h-3.5 w-3.5 -translate-y-1/2 rounded-full border-2 border-surface bg-primary" />
              <span className="grid h-6 w-6 flex-none place-items-center rounded-full font-code text-[9px] font-bold text-[#0d1117]" style={{ background: c.color }}>
                {c.who.slice(0, 2).toUpperCase()}
              </span>
              <span className="font-code text-code-md text-on-surface">{c.msg}</span>
            </div>
          ))}
        </div>
        <div className={`rounded-xl p-4 ring-1 transition-all duration-500 ${merged ? 'bg-[#a371f7]/10 ring-[#a371f7]/50' : 'bg-white/[0.03] ring-white/10'}`}>
          <div className="mb-3 flex items-center justify-between">
            <span className="flex items-center gap-2 font-headline text-headline-sm text-on-surface">
              {merged ? <GitMerge className="h-4 w-4 text-[#a371f7]" /> : <GitPullRequest className="h-4 w-4 text-primary" />}
              Lotus Yoga booking · PR #1
            </span>
            <span className={`rounded-full px-2 py-0.5 font-code text-[10px] font-bold uppercase ${merged ? 'bg-[#a371f7] text-white' : 'bg-primary/20 text-primary'}`}>
              {merged ? 'Merged' : 'Open'}
            </span>
          </div>
          {['build', 'type check', 'tests'].map((check, i) => (
            <div key={check} className="flex items-center gap-2 py-0.5 font-code text-code-sm text-on-surface-variant">
              {checksDone || step > 2 + i ? (
                <Check className="h-3.5 w-3.5 text-primary" />
              ) : (
                <span className="h-3.5 w-3.5 animate-spin rounded-full border-[1.5px] border-secondary border-t-transparent" />
              )}
              {check}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
