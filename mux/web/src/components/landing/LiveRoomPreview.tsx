'use client';

import React, { useEffect, useState } from 'react';
import { Code2, Send, Check } from 'lucide-react';
import { prefersReducedMotion, useTicker } from '@/components/shell';

// Self-playing snapshot of a room for the landing page: messages arrive in the feed,
// the coder types into ClassCard.tsx, and the plan advances with each passing build.

type Tone = 'primary' | 'tertiary' | 'violet' | 'agent';
type FeedEntry =
  | { kind: 'msg'; initial: string; name: string; text: string; tone: Tone; label?: 'merge' | 'queue' | 'conflict' | 'chat' }
  | { kind: 'tool'; text: string; ok?: boolean };

const FEED_SCRIPT: FeedEntry[] = [
  { kind: 'msg', initial: 'D', name: 'Dan', text: 'Make all the buttons blue to match the logo.', tone: 'primary', label: 'conflict' },
  { kind: 'msg', initial: 'P', name: 'Priya', text: 'Buttons should be cyan, it feels calmer.', tone: 'tertiary', label: 'conflict' },
  { kind: 'tool', text: 'coordinator · opened vote on task 5' },
  { kind: 'msg', initial: 'M', name: 'Maya', text: 'Show the teacher name under each class.', tone: 'violet', label: 'merge' },
  { kind: 'tool', text: 'run_build passed · 14.2s · Nebius', ok: true },
  { kind: 'msg', initial: 'H', name: 'MUX', text: 'Schedule grid renders. Adding the day filter next.', tone: 'agent' },
  { kind: 'msg', initial: 'P', name: 'Priya', text: 'We also need a member login page.', tone: 'tertiary', label: 'queue' },
  { kind: 'tool', text: 'coordinator · add_plan_item "Member login" at #7' },
];

const TONE_STYLE: Record<Tone, { avatar: string; name: string }> = {
  primary: { avatar: 'bg-primary text-on-primary', name: 'text-primary' },
  tertiary: { avatar: 'bg-tertiary-container text-on-tertiary-container', name: 'text-tertiary' },
  violet: { avatar: 'bg-[#a371f7] text-white', name: 'text-[#c4a5fb]' },
  agent: { avatar: 'bg-gradient-to-br from-primary to-secondary text-white', name: 'text-on-surface' },
};

const LABEL_STYLE = {
  merge: 'text-coord',
  queue: 'text-queue',
  conflict: 'text-conflict',
  chat: 'text-muted',
};

// Code the coder "types", as colored segments per line
type Segment = [string, string?];
const CODE: { indent: number; segs: Segment[] }[] = [
  { indent: 0, segs: [['import', 'text-tertiary'], [' { Yoga } '], ['from', 'text-tertiary'], [' "../data/classes"', 'text-primary'], [';']] },
  { indent: 0, segs: [["// Edited by coder · task 4 · merged Maya's note", 'text-outline']] },
  { indent: 0, segs: [['export function', 'text-tertiary'], [' '], ['ClassCard', 'text-secondary'], ['({ c }: { c: Yoga }) {']] },
  { indent: 1, segs: [['return', 'text-tertiary'], [' (']] },
  { indent: 2, segs: [['<'], ['div', 'text-primary'], [' className='], ['"rounded-lg border p-4"', 'text-primary'], ['>']] },
  { indent: 3, segs: [['<'], ['h3', 'text-primary'], [' className='], ['"font-semibold"', 'text-primary'], ['>{c.title}</'], ['h3', 'text-primary'], ['>']] },
  { indent: 3, segs: [['<'], ['p', 'text-primary'], ['>{c.day} · {c.teacher}</'], ['p', 'text-primary'], ['>']] },
  { indent: 3, segs: [['<'], ['button', 'text-primary'], [' className='], ['"btn-primary"', 'text-primary'], ['>Book</'], ['button', 'text-primary'], ['>']] },
  { indent: 2, segs: [['</'], ['div', 'text-primary'], ['>']] },
  { indent: 1, segs: [[');']] },
  { indent: 0, segs: [['}']] },
];
const TOTAL_CHARS = CODE.reduce((n, l) => n + l.segs.reduce((m, [t]) => m + t.length, 0), 0);
const PAUSE_TICKS = 110; // ~4s at the typing speed before the file is re-typed

const PLAN = ['Scaffold React + Vite', 'Navbar with studio logo', 'Hero section', 'Class schedule grid', 'Style booking buttons', 'Checkout flow'];
const TYPISTS = ['Dan', 'Priya', 'Maya'];

export function LiveRoomPreview() {
  const [feedIndex, setFeedIndex] = useState(3); // how many script entries have "arrived"
  const [typed, setTyped] = useState(0);
  const [planStep, setPlanStep] = useState(3); // index of the item being worked on
  const [reduced, setReduced] = useState(false);
  const seconds = useTicker(1000);

  useEffect(() => {
    if (prefersReducedMotion()) {
      setReduced(true);
      setTyped(TOTAL_CHARS);
      return;
    }
    const feed = setInterval(() => setFeedIndex(i => i + 1), 2800);
    const typing = setInterval(() => setTyped(t => (t >= TOTAL_CHARS + PAUSE_TICKS ? 0 : t + 1)), 36);
    const plan = setInterval(() => setPlanStep(s => (s >= PLAN.length ? 2 : s + 1)), 5200);
    return () => {
      clearInterval(feed);
      clearInterval(typing);
      clearInterval(plan);
    };
  }, []);

  // Newest four entries, keyed by their absolute position so only new ones animate in
  const visible = Array.from({ length: Math.min(4, feedIndex) }, (_, k) => {
    const abs = feedIndex - Math.min(4, feedIndex) + k;
    return { abs, entry: FEED_SCRIPT[abs % FEED_SCRIPT.length] };
  });

  const voteLeft = 42 - (seconds % 43);
  const typist = TYPISTS[Math.floor(seconds / 4) % TYPISTS.length];
  const typingDone = typed >= TOTAL_CHARS;
  const doneCount = Math.min(planStep, PLAN.length);
  const builds = 36 + doneCount;

  // Render code up to `typed` characters, with the caret after the last one
  let remaining = Math.min(typed, TOTAL_CHARS);
  const codeLines = CODE.map((line, li) => {
    const lineLen = line.segs.reduce((m, [t]) => m + t.length, 0);
    const shownHere = Math.max(0, Math.min(lineLen, remaining));
    const isCaretLine = !typingDone && remaining >= 0 && remaining < lineLen;
    let left = shownHere;
    remaining -= lineLen;
    const segs = line.segs.map(([text, cls], si) => {
      const part = text.slice(0, Math.max(0, left));
      left -= text.length;
      return part ? <span key={si} className={cls}>{part}</span> : null;
    });
    return (
      <p key={li} className={`min-h-[1.25rem] whitespace-pre ${isCaretLine ? 'caret' : ''}`} style={{ paddingLeft: `${line.indent}rem` }}>
        {segs}
      </p>
    );
  });

  return (
    <div className="relative w-full max-w-6xl rounded-2xl border border-outline-variant/40 bg-surface-container-low/90 p-space-sm shadow-[0_30px_80px_-20px_rgba(59,130,246,0.35)] backdrop-blur-xl transition-all duration-500 hover:border-primary/40 md:p-space-md">
      <div className="absolute -top-3 left-8 flex items-center gap-space-xs rounded-full border border-outline-variant/40 bg-surface-container px-space-md py-0.5 font-code text-code-sm text-primary">
        <span className="relative mr-1 flex h-2 w-2">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-error-strong opacity-75" />
          <span className="relative inline-flex h-2 w-2 rounded-full bg-error-strong" />
        </span>
        <Code2 className="h-3.5 w-3.5" />
        Lotus Yoga booking room • Live Session
      </div>
      <div className="absolute -top-3 right-8 hidden items-center gap-space-sm rounded-full border border-outline-variant/40 bg-surface-container py-0.5 pl-1 pr-space-md sm:flex">
        <div className="flex -space-x-1.5">
          {['bg-primary', 'bg-tertiary-container', 'bg-[#a371f7]'].map((c, i) => (
            <span key={i} className={`h-4 w-4 rounded-full border border-surface-container ${c}`} />
          ))}
        </div>
        <span key={typist} className="item-in font-code text-code-sm text-on-surface-variant">{typist} is typing…</span>
      </div>

      <div className="mt-2 grid grid-cols-1 gap-space-md text-left lg:grid-cols-12">
        {/* Feed */}
        <div className="flex flex-col justify-between rounded-lg border border-outline-variant/20 bg-surface-container p-space-md lg:col-span-3">
          <div>
            <div className="mb-space-md flex items-center justify-between">
              <span className="font-code text-label-md uppercase tracking-wider text-on-surface-variant">Live Feed</span>
              <span className="rounded bg-error-strong/20 px-1.5 py-0.5 font-code text-code-sm tabular-nums text-error">
                Vote · 0:{String(voteLeft).padStart(2, '0')}
              </span>
            </div>
            <div className="mb-space-md rounded-md border border-primary/30 bg-surface-container-high p-space-sm">
              <p className="mb-1.5 text-body-sm font-bold text-on-surface">Button color: blue or cyan?</p>
              <div className="space-y-1">
                {[['Blue', 55, 'bg-primary'], ['Cyan', 45, 'bg-secondary']].map(([label, base, color]) => {
                  const pct = (base as number) + (reduced ? 0 : Math.round(Math.sin(seconds / 3 + (label === 'Blue' ? 0 : 2)) * 8));
                  return (
                    <div key={label as string} className="flex items-center gap-2 text-[11px] text-on-surface-variant">
                      <span className="w-8">{label}</span>
                      <span className="h-1 flex-1 overflow-hidden rounded-full bg-surface">
                        <span className={`block h-full rounded-full transition-[width] duration-700 ${color}`} style={{ width: `${pct}%` }} />
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
            <div className="h-[196px] space-y-space-sm overflow-hidden text-body-sm">
              {visible.map(({ abs, entry }) =>
                entry.kind === 'tool' ? (
                  <div key={abs} className={`item-in flex items-baseline gap-2 pl-8 font-code text-[11px] ${entry.ok ? 'text-primary' : 'text-outline'}`}>
                    <span className={`h-1.5 w-1.5 flex-none rounded-full ${entry.ok ? 'bg-primary' : 'bg-outline'}`} />
                    {entry.text}
                  </div>
                ) : (
                  <div key={abs} className="item-in flex items-start gap-space-sm">
                    <div className={`flex h-6 w-6 flex-none items-center justify-center rounded-full text-xs font-bold ${TONE_STYLE[entry.tone].avatar}`}>
                      {entry.initial}
                    </div>
                    <div className="min-w-0">
                      <span className={`text-xs font-bold ${TONE_STYLE[entry.tone].name}`}>
                        {entry.name} <span className="font-code font-normal text-outline">14:{String(5 + (abs % 50)).padStart(2, '0')}</span>
                      </span>
                      {entry.label && (
                        <span className={`chip ${entry.label} ml-1.5 !py-[1px] !text-[9.5px] ${LABEL_STYLE[entry.label]}`}>{entry.label}</span>
                      )}
                      <p className="text-xs text-on-surface">{entry.text}</p>
                    </div>
                  </div>
                ),
              )}
            </div>
          </div>
          <div className="mt-space-md border-t border-outline-variant/20 pt-space-sm">
            <div className="flex items-center justify-between rounded-md bg-surface px-space-md py-space-sm text-xs text-outline">
              <span>Message the room...</span>
              <Send className="h-3.5 w-3.5 text-primary" />
            </div>
          </div>
        </div>

        {/* Code */}
        <div className="flex flex-col rounded-lg border border-outline-variant/20 bg-surface-container-lowest p-space-md font-code text-code-md lg:col-span-6">
          <div className="mb-space-md flex items-center justify-between border-b border-outline-variant/20 pb-space-sm text-xs text-on-surface-variant">
            <div className="flex items-center gap-space-md">
              <span className="flex items-center gap-1.5 font-bold text-on-surface">
                ClassCard.tsx
                {typingDone ? <Check className="h-3 w-3 text-primary" /> : <span className="h-1.5 w-1.5 rounded-full bg-secondary" title="Unsaved" />}
              </span>
              <span>App.tsx</span>
              <span>Navbar.tsx</span>
            </div>
            <span className={typingDone ? 'text-primary' : 'text-secondary'}>{typingDone ? 'saved · build queued' : 'coder editing…'}</span>
          </div>
          <div className="flex gap-space-md overflow-x-auto text-xs text-on-surface-variant">
            <div className="select-none text-right text-outline/50">
              {CODE.map((_, i) => (
                <p key={i} className="min-h-[1.25rem]">{i + 1}</p>
              ))}
            </div>
            <div className="min-w-0 flex-1">{codeLines}</div>
          </div>
        </div>

        {/* Plan */}
        <div className="flex flex-col justify-between rounded-lg border border-outline-variant/20 bg-surface-container p-space-md lg:col-span-3">
          <div>
            <div className="mb-space-md flex items-center justify-between">
              <span className="font-code text-label-md uppercase tracking-wider text-on-surface-variant">Plan &amp; Status</span>
              <span className="text-xs font-bold text-primary">{PLAN.length - doneCount} Open</span>
            </div>
            <div className="space-y-1.5 text-body-sm">
              {PLAN.map((item, i) => {
                const done = i < planStep;
                const active = i === planStep;
                return (
                  <div
                    key={item}
                    className={`flex items-center gap-space-sm rounded-md p-2 transition-all duration-500 ${
                      active ? 'border border-primary/40 bg-surface-container-high' : done ? 'bg-surface-container-high/60' : 'opacity-50'
                    }`}
                  >
                    {done ? (
                      <span className="grid h-3.5 w-3.5 flex-none place-items-center rounded-full bg-primary">
                        <Check className="h-2.5 w-2.5 text-white" />
                      </span>
                    ) : active ? (
                      <span className="h-3.5 w-3.5 flex-none animate-spin rounded-full border-[1.5px] border-secondary border-t-transparent" />
                    ) : (
                      <span className="h-3.5 w-3.5 flex-none rounded-full border-[1.5px] border-dashed border-outline" />
                    )}
                    <span className={`text-xs ${active ? 'font-bold text-on-surface' : done ? 'text-on-surface-variant line-through decoration-outline' : 'text-on-surface-variant'}`}>
                      {item}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
          <div className="mt-space-md rounded-md bg-surface p-space-sm">
            <div className="mb-1 flex items-center justify-between text-xs text-on-surface-variant">
              <span>Builds Passed</span>
              <span key={builds} className="item-in font-bold tabular-nums text-primary">{builds} builds</span>
            </div>
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-container-high">
              <div
                className="h-full rounded-full bg-gradient-to-r from-primary to-secondary transition-[width] duration-700"
                style={{ width: `${(doneCount / PLAN.length) * 100}%` }}
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
