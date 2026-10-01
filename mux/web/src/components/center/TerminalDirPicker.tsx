'use client';

import React, { useEffect, useRef, useState } from 'react';
import { Folder, ChevronDown, Check, Wand2 } from 'lucide-react';
import { projectDirs } from '@/lib/terminalCwd';

interface TerminalDirPickerProps {
  paths: string[];
  current: string; // '' = project root
  saved: string | null; // null = automatic
  autoDir: string;
  onChoose: (dir: string | null) => void;
}

const label = (dir: string) => (dir ? `${dir}/` : 'project root');

// Terminal toolbar control: which folder this room's terminals open in
export function TerminalDirPicker({ paths, current, saved, autoDir, onChoose }: TerminalDirPickerProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false); };
    window.addEventListener('mousedown', close);
    return () => window.removeEventListener('mousedown', close);
  }, [open]);

  // Project folders, plus every top-level folder, so any of them can be chosen
  const topLevel = Array.from(new Set(paths.filter(p => p.includes('/')).map(p => p.split('/')[0]))).filter(d => !d.startsWith('.'));
  const options = Array.from(new Set(['', ...projectDirs(paths), ...topLevel])).sort((a, b) => (a === '' ? -1 : b === '' ? 1 : a.localeCompare(b)));
  const projects = new Set(projectDirs(paths));

  const item = (dir: string | null, text: React.ReactNode, on: boolean) => (
    <button
      key={dir ?? '__auto'}
      type="button"
      role="menuitemradio"
      aria-checked={on}
      onClick={() => { onChoose(dir); setOpen(false); }}
      className="flex w-full items-center gap-2 rounded px-2 py-1 text-left text-[12px] text-[var(--ink)] hover:bg-white/5"
    >
      <span className="w-3.5 flex-none">{on && <Check className="h-3.5 w-3.5 text-[var(--coord)]" />}</span>
      {text}
    </button>
  );

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        title="Folder new terminals start in"
        aria-haspopup="menu"
        aria-expanded={open}
        className={`flex max-w-40 items-center gap-1 rounded px-1.5 py-0.5 font-mono text-[11px] transition-colors hover:bg-white/10 hover:text-[var(--ink)] ${open ? 'bg-white/10 text-[var(--ink)]' : 'text-[var(--muted)]'}`}
      >
        <Folder className="h-3.5 w-3.5 flex-none" />
        <span className="truncate">{current ? `${current}/` : '~/project'}</span>
        <ChevronDown className="h-3 w-3 flex-none" />
      </button>

      {open && (
        <div role="menu" className="item-in absolute right-0 top-full z-30 mt-1 w-64 rounded-lg border border-[var(--line)] bg-[var(--panel)] p-1.5 font-sans shadow-2xl">
          <p className="px-2 pb-1 text-[10.5px] uppercase tracking-[0.1em] text-[var(--faint)]">Terminal opens in</p>
          {item(null, <span className="flex min-w-0 items-center gap-1.5"><Wand2 className="h-3.5 w-3.5 flex-none text-[var(--coder)]" /> Automatic <span className="truncate font-mono text-[11px] text-[var(--faint)]">({label(autoDir)})</span></span>, saved === null)}
          <div className="my-1 border-t border-[var(--line)]" />
          <div className="max-h-56 overflow-auto">
            {options.map(dir =>
              item(
                dir,
                <span className="flex min-w-0 items-center gap-1.5">
                  <Folder className="h-3.5 w-3.5 flex-none text-[var(--muted)]" />
                  <span className="truncate font-mono text-[11.5px]">{label(dir)}</span>
                  {projects.has(dir) && dir !== '' && <span className="flex-none rounded bg-white/10 px-1 text-[9.5px] uppercase text-[var(--muted)]">project</span>}
                </span>,
                saved === dir,
              ),
            )}
          </div>
          <p className="mt-1 border-t border-[var(--line)] px-2 pt-1.5 text-[10.5px] leading-snug text-[var(--faint)]">
            Saved for this room. Choosing a folder also moves the open terminal there.
          </p>
        </div>
      )}
    </div>
  );
}
