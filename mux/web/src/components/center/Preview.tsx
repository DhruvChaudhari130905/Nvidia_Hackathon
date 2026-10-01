'use client';

import React, { useEffect, useState } from 'react';
import { Sparkles, MessageSquareText } from 'lucide-react';
import type { PlanItem } from '@/types';
import { getDemoPreview, isDemoMode, type DemoPreview } from '@/lib/demo';
import type { FileMap } from './FileTree';

interface PreviewProps {
  files: FileMap;
  roomId: string;
  title: string;
  description: string;
  plan: PlanItem[];
}

// Preview tab. Sample projects in demo mode render their app; any other room shows a blank-project
// canvas until something has been built (the live WebContainer preview takes over once connected).
export function Preview({ files, roomId, title, description, plan }: PreviewProps) {
  const [buildStatus, setBuildStatus] = useState<'building' | 'ready'>('building');
  const [spec, setSpec] = useState<DemoPreview | null>(null);

  useEffect(() => {
    setSpec(isDemoMode() ? getDemoPreview(roomId) : null);
    setBuildStatus('building');
    const timer = setTimeout(() => setBuildStatus('ready'), 900);
    return () => clearTimeout(timer);
  }, [roomId]);

  if (buildStatus === 'building') {
    return (
      <div className="preview flex min-h-[400px] items-center justify-center">
        <div className="text-center">
          <div className="mx-auto mb-4 h-8 w-8 animate-spin rounded-full border-b-2 border-[var(--coord)]" />
          <p className="text-[#8a7f74]">Starting preview…</p>
        </div>
      </div>
    );
  }

  if (spec) return <SampleApp spec={spec} />;
  return <BlankProject title={title} description={description} plan={plan} fileCount={files.size} />;
}

function SampleApp({ spec }: { spec: DemoPreview }) {
  const [clicked, setClicked] = useState<Set<string>>(new Set());
  const toggle = (t: string) =>
    setClicked(prev => {
      const next = new Set(prev);
      if (next.has(t)) next.delete(t);
      else next.add(t);
      return next;
    });

  return (
    <div className="preview item-in" style={{ background: spec.background, color: spec.ink }}>
      <div className="pv-nav" style={{ borderColor: `${spec.ink}14` }}>
        <span className="pv-logo">{spec.brand}</span>
        <div className="pv-links" style={{ color: `${spec.ink}aa` }}>
          {spec.links.map(l => <span key={l}>{l}</span>)}
        </div>
      </div>
      <div className="pv-hero">
        <h2>{spec.headline}</h2>
        <p style={{ color: `${spec.ink}aa` }}>{spec.tagline}</p>
      </div>
      <div className="pv-grid">
        {spec.cards.map(c => {
          const on = clicked.has(c.title);
          return (
            <div key={c.title} className="pv-card" style={{ borderColor: `${spec.ink}14` }}>
              <span className="t">{c.title}</span>
              <span className="m" style={{ color: `${spec.ink}88` }}>{c.meta}</span>
              <button
                className="pv-btn transition-transform active:scale-95"
                type="button"
                onClick={() => toggle(c.title)}
                aria-pressed={on}
                style={{ background: spec.accent, opacity: on ? 0.8 : 1 }}
              >
                {on ? `${c.action} ✓` : c.action}
              </button>
            </div>
          );
        })}
        <div className="pv-card skeleton whitespace-pre-line">{spec.building}</div>
      </div>
      <div className="built">
        <span><b>●</b> Last build passed</span>
        <span className="mono">snapshot 7f3a…e21</span>
        <span>Sample project preview</span>
      </div>
    </div>
  );
}

function BlankProject({ title, description, plan, fileCount }: { title: string; description: string; plan: PlanItem[]; fileCount: number }) {
  const done = plan.filter(p => p.status === 'done').length;
  return (
    <div className="item-in flex min-h-full flex-col overflow-hidden rounded-lg border border-[var(--line)] bg-[var(--panel)]">
      <div className="flex items-center gap-2 border-b border-[var(--line)] px-4 py-2.5">
        <span className="h-2.5 w-2.5 rounded-full bg-[#f85149]/60" />
        <span className="h-2.5 w-2.5 rounded-full bg-[#d29922]/60" />
        <span className="h-2.5 w-2.5 rounded-full bg-[#3fb950]/60" />
        <span className="mono ml-3 rounded bg-[var(--bg)] px-2 py-0.5 text-[11px] text-[var(--faint)]">localhost:5173</span>
      </div>
      <div className="relative flex flex-1 flex-col items-center justify-center gap-4 p-8 text-center">
        <div
          className="pointer-events-none absolute inset-0 opacity-[0.35]"
          style={{ backgroundImage: 'radial-gradient(var(--line) 1px, transparent 1px)', backgroundSize: '18px 18px' }}
        />
        <div className="relative grid h-16 w-16 place-items-center rounded-2xl bg-gradient-to-br from-[var(--coord)]/25 to-[var(--coder)]/25 ring-1 ring-white/10">
          <Sparkles className="h-7 w-7 text-[var(--coder)]" />
        </div>
        <div className="relative">
          <h3 className="mb-1 text-lg font-semibold text-[var(--ink)]">{title || 'Blank project'}</h3>
          <p className="mx-auto max-w-sm text-sm text-[var(--muted)]">
            {description && description.trim().toLowerCase() !== title.replace(/…$/, '').trim().toLowerCase()
              ? `“${description}”`
              : 'Nothing built yet.'}
          </p>
        </div>
        <div className="relative flex items-center gap-2 rounded-full bg-[var(--bg)] px-3 py-1.5 text-xs text-[var(--muted)] ring-1 ring-[var(--line)]">
          <MessageSquareText className="h-3.5 w-3.5 text-[var(--coord)]" />
          {plan.length
            ? `${done} of ${plan.length} plan items built · the preview appears after the first build`
            : 'Describe what you want in the feed — the preview appears after the first build'}
        </div>
        <p className="mono relative text-[11px] text-[var(--faint)]">{fileCount} {fileCount === 1 ? 'file' : 'files'} · edit them in the Code tab</p>
      </div>
    </div>
  );
}
