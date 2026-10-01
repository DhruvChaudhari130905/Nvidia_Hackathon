'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Search, ChevronRight } from 'lucide-react';
import { FileIcon } from './FileTree';

export interface PaletteCommand {
  id: string;
  label: string;
  shortcut?: string;
  run: () => void;
}

interface QuickOpenProps {
  files: string[];
  commands: PaletteCommand[];
  initialMode: 'files' | 'commands';
  onOpenFile: (path: string) => void;
  onClose: () => void;
}

// Subsequence match: "clcd" matches "ClassCard.tsx"; earlier, tighter matches score higher
function fuzzy(query: string, text: string): number | null {
  if (!query) return 0;
  const q = query.toLowerCase();
  const t = text.toLowerCase();
  let ti = 0;
  let score = 0;
  let last = -1;
  for (const ch of q) {
    const found = t.indexOf(ch, ti);
    if (found === -1) return null;
    score += found === last + 1 ? 3 : 1;
    if (found === 0 || '/._-'.includes(t[found - 1])) score += 2;
    last = found;
    ti = found + 1;
  }
  return score - t.length * 0.02;
}

// ⌘P quick open; typing ">" (or ⌘⇧P) switches to commands
export function QuickOpen({ files, commands, initialMode, onOpenFile, onClose }: QuickOpenProps) {
  const [query, setQuery] = useState(initialMode === 'commands' ? '>' : '');
  const [index, setIndex] = useState(0);
  const listRef = useRef<HTMLDivElement>(null);
  const isCommands = query.startsWith('>');
  const q = isCommands ? query.slice(1).trim() : query.trim();

  const results = useMemo(() => {
    if (isCommands) {
      return commands
        .map(c => ({ c, s: fuzzy(q, c.label) }))
        .filter(r => r.s !== null)
        .sort((a, b) => b.s! - a.s!)
        .map(r => ({ key: r.c.id, label: r.c.label, detail: r.c.shortcut ?? '', run: r.c.run, path: '' }));
    }
    return files
      .map(p => ({ p, s: Math.max(fuzzy(q, p.split('/').pop()!) ?? -Infinity, (fuzzy(q, p) ?? -Infinity) - 1) }))
      .filter(r => r.s > -Infinity)
      .sort((a, b) => b.s - a.s)
      .slice(0, 50)
      .map(r => ({ key: r.p, label: r.p.split('/').pop()!, detail: r.p, run: () => onOpenFile(r.p), path: r.p }));
  }, [isCommands, q, files, commands, onOpenFile]);

  useEffect(() => setIndex(0), [query]);
  useEffect(() => {
    listRef.current?.querySelector<HTMLElement>(`[data-i="${index}"]`)?.scrollIntoView({ block: 'nearest' });
  }, [index]);

  const choose = (i: number) => {
    const r = results[i];
    if (!r) return;
    onClose();
    r.run();
  };

  return (
    <div className="absolute inset-0 z-30 flex justify-center bg-black/40 pt-10 backdrop-blur-[2px]" onMouseDown={onClose}>
      <div
        className="item-in h-fit w-[min(560px,92%)] overflow-hidden rounded-lg border border-[var(--line)] bg-[var(--panel)] shadow-[0_24px_80px_rgba(0,0,0,0.6)]"
        onMouseDown={e => e.stopPropagation()}
        role="dialog"
        aria-label={isCommands ? 'Command palette' : 'Quick open'}
      >
        <div className="flex items-center gap-2 border-b border-[var(--line)] px-3">
          {isCommands ? <ChevronRight className="h-4 w-4 text-[var(--coder)]" /> : <Search className="h-4 w-4 text-[var(--faint)]" />}
          <input
            autoFocus
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Escape') onClose();
              else if (e.key === 'ArrowDown') { e.preventDefault(); setIndex(i => Math.min(results.length - 1, i + 1)); }
              else if (e.key === 'ArrowUp') { e.preventDefault(); setIndex(i => Math.max(0, i - 1)); }
              else if (e.key === 'Enter') { e.preventDefault(); choose(index); }
            }}
            placeholder={isCommands ? 'Run a command…' : 'Go to file…  (type > for commands)'}
            className="min-w-0 flex-1 bg-transparent py-2.5 font-mono text-[13px] text-[var(--ink)] outline-none placeholder:text-[var(--faint)]"
            aria-label="Search"
          />
        </div>
        <div ref={listRef} className="max-h-[320px] overflow-auto py-1">
          {results.length === 0 && <p className="px-3 py-2 text-[12px] text-[var(--faint)]">No matches</p>}
          {results.map((r, i) => (
            <button
              key={r.key}
              data-i={i}
              type="button"
              onMouseEnter={() => setIndex(i)}
              onClick={() => choose(i)}
              className={`flex w-full items-center gap-2 px-3 py-1.5 text-left text-[12.5px] ${i === index ? 'bg-[var(--coord)]/20 text-[var(--ink)]' : 'text-[var(--muted)]'}`}
            >
              {r.path ? <FileIcon name={r.path} className="h-3.5 w-3.5 flex-none" /> : <ChevronRight className="h-3.5 w-3.5 flex-none text-[var(--faint)]" />}
              <span className="truncate font-mono">{r.label}</span>
              <span className="ml-auto truncate pl-3 font-mono text-[11px] text-[var(--faint)]">{r.detail}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
