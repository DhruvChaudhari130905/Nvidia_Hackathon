'use client';

import React, { useEffect, useState } from 'react';
import { Check, Crown, Github, GitBranch, Package, RotateCcw, Timer, X } from 'lucide-react';

// Small interactive demos that sit inside each Docs section

const card = 'rounded-xl border border-white/10 bg-surface-container-lowest/70 p-space-md backdrop-blur';

/* Rooms: hover the regions of a room */
const REGIONS = [
  { id: 'top', label: 'Top bar', text: 'Room name, who’s here, who’s typing, the token/build budget, Share and Export.' },
  { id: 'feed', label: 'Feed', text: 'Everyone’s messages and the agent’s replies, each labelled by the coordinator.' },
  { id: 'center', label: 'Preview / Code', text: 'The running app, or the full editor with explorer, terminal and problems.' },
  { id: 'side', label: 'Decisions & plan', text: 'Open votes and agent questions on top, the plan underneath.' },
  { id: 'timeline', label: 'Timeline', text: 'A checkpoint for every passing build. Click one to rewind.' },
];

export function RoomDiagram() {
  const [hover, setHover] = useState('center');
  const region = (id: string, className: string, children?: React.ReactNode) => (
    <button
      type="button"
      onMouseEnter={() => setHover(id)}
      onFocus={() => setHover(id)}
      onClick={() => setHover(id)}
      className={`relative rounded-md border text-left transition-all duration-300 ${
        hover === id ? 'border-secondary bg-secondary/15 shadow-[0_0_24px_rgba(6,182,212,0.35)]' : 'border-white/10 bg-white/[0.03] hover:border-white/25'
      } ${className}`}
      aria-label={REGIONS.find(r => r.id === id)!.label}
    >
      {children}
    </button>
  );
  const active = REGIONS.find(r => r.id === hover)!;
  return (
    <div className={`${card} grid gap-space-md md:grid-cols-[1.3fr_1fr]`}>
      <div className="grid aspect-[16/10] grid-rows-[12%_1fr_14%] gap-1.5">
        {region('top', 'flex items-center gap-1.5 px-2', <><span className="h-1.5 w-8 rounded bg-white/30" /><span className="ml-auto h-2 w-2 rounded-full bg-primary" /><span className="h-2 w-2 rounded-full bg-secondary" /></>)}
        <div className="grid grid-cols-[1fr_1.6fr_1fr] gap-1.5">
          {region('feed', 'space-y-1 p-2', [0, 1, 2, 3].map(i => <span key={i} className="block h-1.5 rounded bg-white/20" style={{ width: `${90 - i * 15}%` }} />))}
          {region('center', 'p-2', <span className="block h-full w-full rounded bg-[#fbf8f4]/80" />)}
          {region('side', 'space-y-1.5 p-2', <><span className="block h-5 rounded border border-[#f85149]/60" /><span className="block h-5 rounded border border-[#a371f7]/60" /></>)}
        </div>
        {region('timeline', 'flex items-center justify-around px-3', [0, 1, 2, 3].map(i => <span key={i} className="h-2 w-2 rounded-full border border-primary" />))}
      </div>
      <div key={active.id} className="item-in flex flex-col justify-center">
        <span className="mb-1 font-code text-label-md uppercase tracking-wider text-secondary">{active.label}</span>
        <p className="text-body-md text-on-surface">{active.text}</p>
        <p className="mt-space-md font-code text-code-sm text-outline">Hover or tap a region</p>
      </div>
    </div>
  );
}

/* Message labels: type and see the label */
type Label = 'merge' | 'queue' | 'interrupt' | 'chat';
function classify(text: string): Label {
  const t = text.toLowerCase();
  if (/\b(stop|wait|undo|wrong|hold on)\b/.test(t)) return 'interrupt';
  if (/\b(add|new|also need|create|another)\b/.test(t)) return 'queue';
  if (/\?\s*$/.test(t) || /\b(thanks|great|nice|cool|love)\b/.test(t)) return 'chat';
  return 'merge';
}
const LABEL_TEXT: Record<Label, string> = {
  merge: 'Refines the current task — folded in at the next turn boundary.',
  queue: 'New scope — added to the plan after the current task.',
  interrupt: 'The coder stops at the next turn boundary and asks what to change.',
  chat: 'Conversation only — never changes the plan.',
};
const SAMPLES = ['Make the headings bigger', 'Also add a pricing page', 'Stop, that’s the wrong page', 'This looks great!'];

export function LabelPlayground() {
  const [text, setText] = useState(SAMPLES[0]);
  const label = classify(text);
  return (
    <div className={card}>
      <div className="mb-space-sm flex flex-wrap gap-1.5">
        {SAMPLES.map(s => (
          <button key={s} type="button" onClick={() => setText(s)} className="rounded-full border border-white/10 px-2.5 py-1 font-code text-code-sm text-on-surface-variant transition-colors hover:border-primary/50 hover:text-on-surface">
            {s}
          </button>
        ))}
      </div>
      <div className="flex items-center gap-space-sm rounded-lg border border-white/10 bg-bg px-space-md focus-within:border-primary">
        <input
          value={text}
          onChange={e => setText(e.target.value)}
          placeholder="Message the room…"
          className="min-w-0 flex-1 bg-transparent py-2.5 text-body-md text-on-surface outline-none"
          aria-label="Try a message"
        />
        <span key={label} className={`chip ${label} item-in flex-none`}>{label}</span>
      </div>
      <p key={`${label}-t`} className="item-in mt-space-sm text-body-sm text-on-surface-variant">{LABEL_TEXT[label]}</p>
      <p className="mt-1 font-code text-[11px] text-outline">Keyword approximation for the demo — the real coordinator reads intent with the model. <span className="text-conflict">conflict</span> needs two clashing messages.</p>
    </div>
  );
}

/* Votes: weighted by domain, owner override */
type Domain = 'ui' | 'architecture' | 'scope';
const VOTERS: { name: string; role: 'design' | 'eng' | 'pm'; color: string }[] = [
  { name: 'Priya', role: 'design', color: '#f0a3c4' },
  { name: 'Marco', role: 'eng', color: '#9ad0f5' },
  { name: 'Dan', role: 'pm', color: '#c7e59a' },
];
const DOMAIN_ROLE: Record<Domain, 'design' | 'eng' | 'pm'> = { ui: 'design', architecture: 'eng', scope: 'pm' };

export function VoteSimulator() {
  const [domain, setDomain] = useState<Domain>('ui');
  const [picks, setPicks] = useState<Record<string, 0 | 1>>({ Priya: 0, Marco: 1, Dan: 0 });
  const [override, setOverride] = useState<0 | 1 | null>(null);
  const options = ['Calendar heatmap', 'Streak number'];
  const weight = (role: string) => (DOMAIN_ROLE[domain] === role ? 2 : 1);
  const totals = [0, 1].map(o => VOTERS.filter(v => picks[v.name] === o).reduce((n, v) => n + weight(v.role), 0));
  const winner = override ?? (totals[0] === totals[1] ? null : totals[0] > totals[1] ? 0 : 1);
  const max = Math.max(1, totals[0] + totals[1]);

  return (
    <div className={card}>
      <div className="mb-space-md flex flex-wrap items-center gap-space-sm text-body-sm">
        <span className="text-on-surface-variant">Conflict domain:</span>
        {(['ui', 'architecture', 'scope'] as Domain[]).map(d => (
          <button key={d} type="button" onClick={() => { setDomain(d); setOverride(null); }} className={`rounded-full px-2.5 py-0.5 font-code text-code-sm transition-colors ${domain === d ? 'bg-primary text-white' : 'bg-white/5 text-on-surface-variant hover:text-on-surface'}`}>
            {d}
          </button>
        ))}
        <span className="font-code text-code-sm text-outline">→ {DOMAIN_ROLE[domain]} counts 2×</span>
      </div>
      <div className="space-y-space-sm">
        {options.map((opt, o) => (
          <div key={opt} className={`rounded-lg p-space-sm transition-all duration-500 ${winner === o ? 'bg-primary/15 ring-1 ring-primary/60' : 'bg-white/[0.03]'}`}>
            <div className="mb-1.5 flex items-center justify-between text-body-md">
              <span className="flex items-center gap-2 text-on-surface">
                {winner === o && <Check className="h-4 w-4 text-primary" />}
                {opt}
              </span>
              <span className="font-code text-code-sm tabular-nums text-outline">{totals[o]} pts</span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-white/5">
              <div className="h-full rounded-full bg-gradient-to-r from-primary to-secondary transition-[width] duration-500" style={{ width: `${(totals[o] / max) * 100}%` }} />
            </div>
          </div>
        ))}
      </div>
      <div className="mt-space-md flex flex-wrap items-center gap-space-sm">
        {VOTERS.map(v => (
          <button
            key={v.name}
            type="button"
            onClick={() => { setPicks(p => ({ ...p, [v.name]: p[v.name] === 0 ? 1 : 0 })); setOverride(null); }}
            className="flex items-center gap-1.5 rounded-full border border-white/10 py-0.5 pl-0.5 pr-2.5 text-body-sm transition-all hover:border-primary/50"
            title="Click to switch this vote"
          >
            <span className="grid h-5 w-5 place-items-center rounded-full font-code text-[9px] font-bold text-[#0d1117]" style={{ background: v.color }}>{v.name.slice(0, 2).toUpperCase()}</span>
            <span className="text-on-surface">{v.name}</span>
            <span className="font-code text-[10px] text-outline">{v.role}{weight(v.role) === 2 ? ' ×2' : ''}</span>
            <span className="text-outline">→ {picks[v.name] === 0 ? 'A' : 'B'}</span>
          </button>
        ))}
        <button type="button" onClick={() => setOverride(o => (o === null ? (winner === 0 ? 1 : 0) : null))} className="ml-auto flex items-center gap-1 rounded-full px-2.5 py-1 text-body-sm text-conflict underline-offset-2 hover:underline">
          <Crown className="h-3.5 w-3.5" /> {override === null ? 'Owner override' : 'Undo override'}
        </button>
      </div>
      <p className="mt-space-sm text-body-sm text-on-surface-variant">
        {winner === null ? 'Tied — the vote stays open until the timer runs out.' : override !== null ? `Owner override → ${options[override]}.` : `${options[winner]} wins on weighted votes.`}
      </p>
    </div>
  );
}

/* Agent questions: timer runs down to the default */
export function QuestionCountdown() {
  const TOTAL = 12;
  const [left, setLeft] = useState(TOTAL);
  const [answer, setAnswer] = useState<{ value: string; how: 'you' | 'default' } | null>(null);
  useEffect(() => {
    if (answer) return;
    if (left <= 0) {
      setAnswer({ value: 'Push notifications', how: 'default' });
      return;
    }
    const id = setTimeout(() => setLeft(l => l - 1), 1000);
    return () => clearTimeout(id);
  }, [left, answer]);
  const reset = () => { setLeft(TOTAL); setAnswer(null); };
  return (
    <div className={`${card} border-[#a371f7]/40`}>
      <div className="mb-space-sm flex items-center justify-between">
        <span className="font-code text-[11px] uppercase tracking-[0.12em] text-[#a371f7]">Agent question · task 4</span>
        <span className="flex items-center gap-1 font-code text-code-sm tabular-nums text-outline"><Timer className="h-3.5 w-3.5" />0:{String(Math.max(0, left)).padStart(2, '0')}</span>
      </div>
      <p className="mb-space-sm font-headline text-headline-sm text-on-surface">Should reminders be push notifications or email?</p>
      <div className="mb-space-sm h-1 overflow-hidden rounded-full bg-white/5">
        <div className="h-full bg-[#a371f7] transition-[width] duration-1000 ease-linear" style={{ width: `${(left / TOTAL) * 100}%` }} />
      </div>
      {answer ? (
        <div className="item-in flex items-center justify-between gap-space-sm">
          <p className="text-body-md text-primary">
            <Check className="mr-1 inline h-4 w-4" />
            {answer.how === 'default' ? `No answer — used the default: ${answer.value}` : `Answered: ${answer.value} — sent to the coder`}
          </p>
          <button type="button" onClick={reset} className="flex items-center gap-1 font-code text-code-sm text-outline hover:text-on-surface"><RotateCcw className="h-3.5 w-3.5" /> replay</button>
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-space-sm">
          {['Push notifications', 'Email'].map(o => (
            <button key={o} type="button" onClick={() => setAnswer({ value: o, how: 'you' })} className="flex items-center justify-between rounded-lg border border-white/10 px-space-sm py-2 text-left text-body-md text-on-surface transition-colors hover:border-[#a371f7]/60">
              {o}
              {o === 'Push notifications' && <span className="font-code text-[10px] text-outline">default</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/* Plan: a task moving through its lifecycle */
const STAGES = [
  { id: 'draft', label: 'draft', hint: 'Anyone with edit access can reword or reorder' },
  { id: 'todo', label: 'todo', hint: 'Approved and waiting its turn' },
  { id: 'doing', label: 'doing', hint: 'The coder is working on it' },
  { id: 'skipped', label: 'skipped', hint: 'Blocked on a vote or question — the coder moves on' },
  { id: 'done', label: 'done', hint: 'Built, and the build passed' },
];
export function PlanLifecycle() {
  const [i, setI] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setI(x => (x + 1) % STAGES.length), 1800);
    return () => clearInterval(id);
  }, []);
  return (
    <div className={card}>
      <div className="relative flex items-center justify-between">
        <div className="absolute left-4 right-4 top-1/2 h-px -translate-y-1/2 bg-white/10" />
        <div className="absolute left-4 top-1/2 h-px -translate-y-1/2 bg-gradient-to-r from-primary to-secondary transition-all duration-700" style={{ width: `calc(${(i / (STAGES.length - 1)) * 100}% - 2rem)` }} />
        {STAGES.map((s, k) => (
          <button key={s.id} type="button" onClick={() => setI(k)} className={`relative z-10 rounded-full border px-2.5 py-1 font-code text-code-sm transition-all duration-500 ${
            k === i ? (s.id === 'skipped' ? 'scale-110 border-conflict bg-conflict/20 text-conflict' : 'scale-110 border-secondary bg-secondary/20 text-on-surface shadow-[0_0_20px_rgba(6,182,212,0.4)]') : k < i ? 'border-primary/40 bg-surface text-primary' : 'border-white/10 bg-surface text-outline'
          }`}>
            {s.label}
          </button>
        ))}
      </div>
      <p key={i} className="item-in mt-space-md text-center text-body-sm text-on-surface-variant">{STAGES[i].hint}</p>
    </div>
  );
}

/* Checkpoints: drag to rewind */
const CHECKPOINTS = ['Starter template', 'Scaffold', 'Navbar', 'Hero section', 'Schedule grid'];
export function RewindSlider() {
  const [at, setAt] = useState(CHECKPOINTS.length - 1);
  const latest = at === CHECKPOINTS.length - 1;
  return (
    <div className={card}>
      <div className="relative mb-space-md flex justify-between px-1">
        <div className="absolute left-4 right-4 top-3 h-px bg-white/10" />
        {CHECKPOINTS.map((c, k) => (
          <button key={c} type="button" onClick={() => setAt(k)} className={`relative z-10 flex w-16 flex-col items-center gap-1 transition-opacity duration-300 ${k > at ? 'opacity-30' : ''}`}>
            <span className={`grid h-6 w-6 place-items-center rounded-full border-2 font-code text-[10px] transition-all ${k === at ? 'border-primary bg-primary text-white shadow-[0_0_0_4px_rgba(59,130,246,0.25)]' : 'border-primary bg-surface text-primary'}`}>{k}</span>
            <span className="text-center text-[10.5px] leading-tight text-on-surface-variant">{c}</span>
          </button>
        ))}
      </div>
      <input type="range" min={0} max={CHECKPOINTS.length - 1} value={at} onChange={e => setAt(Number(e.target.value))} className="w-full accent-[#3b82f6]" aria-label="Rewind to checkpoint" />
      <div className="mt-space-sm flex items-center justify-between gap-space-sm">
        <p key={at} className={`item-in text-body-sm ${latest ? 'text-on-surface-variant' : 'text-conflict'}`}>
          {latest ? 'You’re on the latest checkpoint.' : `Viewing checkpoint ${at}. Files, plan and log reverted — later work is greyed out, not deleted.`}
        </p>
        {!latest && (
          <button type="button" onClick={() => setAt(CHECKPOINTS.length - 1)} className="btn flex-none text-xs">Return to latest</button>
        )}
      </div>
    </div>
  );
}

/* Budget: meter colors */
export function BudgetDial() {
  const [pct, setPct] = useState(62);
  const color = pct > 90 ? 'var(--conflict)' : pct > 70 ? 'var(--ask)' : 'var(--coord)';
  const tokens = (2 * pct) / 100;
  return (
    <div className={card}>
      <div className="mb-1 flex justify-between font-code text-code-sm tabular-nums text-on-surface-variant">
        <span>{tokens.toFixed(2)}M / 2M tokens</span>
        <span>{Math.round(pct)} / 100 builds</span>
      </div>
      <div className="mb-space-md h-2.5 overflow-hidden rounded-full bg-white/5">
        <div className="h-full rounded-full transition-[width,background] duration-300" style={{ width: `${pct}%`, background: color }} />
      </div>
      <input type="range" min={0} max={100} value={pct} onChange={e => setPct(Number(e.target.value))} className="w-full accent-[#06b6d4]" aria-label="Budget used" />
      <p className="mt-space-sm text-body-sm" style={{ color }}>
        {pct > 90 ? 'Over 90% — red. Time to raise the cap or wrap up.' : pct > 70 ? 'Over 70% — purple warning.' : 'Plenty left — blue.'}
      </p>
    </div>
  );
}

/* Roles: permissions matrix */
const CAPS: [string, boolean, boolean, boolean][] = [
  ['Chat and steer the agent', true, true, false],
  ['Vote on conflicts', true, true, false],
  ['Answer agent questions', true, true, false],
  ['Edit code and the plan', true, true, false],
  ['Watch everything live', true, true, true],
  ['Owner override on votes', true, false, false],
  ['Export to GitHub', true, false, false],
];
export function RolesMatrix() {
  const [role, setRole] = useState(1);
  const roles = ['Owner', 'Editor', 'Viewer'];
  return (
    <div className={card}>
      <div className="mb-space-md flex gap-1 rounded-lg bg-white/5 p-1">
        {roles.map((r, k) => (
          <button key={r} type="button" onClick={() => setRole(k)} className={`flex-1 rounded-md py-1.5 text-body-sm transition-all ${role === k ? 'bg-primary text-white shadow' : 'text-on-surface-variant hover:text-on-surface'}`}>
            {r}
          </button>
        ))}
      </div>
      <ul className="space-y-1.5">
        {CAPS.map(([cap, ...allowed]) => {
          const ok = allowed[role];
          return (
            <li key={cap} className={`flex items-center gap-space-sm text-body-md transition-all duration-300 ${ok ? 'text-on-surface' : 'text-outline line-through decoration-outline/40'}`}>
              <span className={`grid h-5 w-5 flex-none place-items-center rounded-full transition-colors duration-300 ${ok ? 'bg-primary/20 text-primary' : 'bg-white/5 text-outline'}`}>
                {ok ? <Check className="h-3 w-3" /> : <X className="h-3 w-3" />}
              </span>
              {cap}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/* Export: pipeline animation */
const EXPORT_STEPS = [
  { icon: Package, text: 'Snapshot the current checkpoint' },
  { icon: GitBranch, text: 'Create the repository' },
  { icon: Github, text: 'Push the files to main' },
];
export function ExportPipeline() {
  const [step, setStep] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setStep(s => (s + 1) % (EXPORT_STEPS.length + 2)), 1100);
    return () => clearInterval(id);
  }, []);
  return (
    <div className={`${card} flex flex-col gap-space-sm sm:flex-row sm:items-center`}>
      {EXPORT_STEPS.map((s, k) => {
        const Icon = s.icon;
        const done = step > k;
        const now = step === k;
        return (
          <React.Fragment key={s.text}>
            {k > 0 && <div className={`hidden h-px flex-1 transition-colors duration-500 sm:block ${done || now ? 'bg-primary' : 'bg-white/10'}`} />}
            <div className={`flex items-center gap-space-sm rounded-lg px-space-sm py-2 transition-all duration-500 ${now ? 'bg-primary/15 ring-1 ring-primary/50' : ''}`}>
              <span className={`grid h-8 w-8 flex-none place-items-center rounded-full transition-colors duration-500 ${done ? 'bg-primary text-white' : now ? 'bg-secondary/20 text-secondary' : 'bg-white/5 text-outline'}`}>
                {done ? <Check className="h-4 w-4" /> : now ? <span className="h-3.5 w-3.5 animate-spin rounded-full border-[1.5px] border-secondary border-t-transparent" /> : <Icon className="h-4 w-4" />}
              </span>
              <span className={`text-body-sm ${done || now ? 'text-on-surface' : 'text-outline'}`}>{s.text}</span>
            </div>
          </React.Fragment>
        );
      })}
    </div>
  );
}
