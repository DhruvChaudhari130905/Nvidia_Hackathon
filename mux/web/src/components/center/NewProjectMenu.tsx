'use client';

import React, { useEffect, useRef, useState } from 'react';
import { LayoutTemplate, ChevronDown, Globe, Smartphone } from 'lucide-react';
import { PROJECT_TEMPLATES, safeFolderName, type ProjectTemplate } from '@/lib/projectTemplates';
import { writeContainerFile } from '@/lib/runtime';
import { PROJECT_DIR } from '@/lib/terminalCwd';

interface NewProjectMenuProps {
  existingPaths: string[];
  // Types the command into the active shell; false when no real shell is running
  run: (command: string) => boolean;
  onUnavailable: () => void;
}

export function NewProjectMenu({ existingPaths, run, onUnavailable }: NewProjectMenuProps) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState('');
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false); };
    window.addEventListener('mousedown', close);
    window.addEventListener('keydown', esc);
    return () => {
      window.removeEventListener('mousedown', close);
      window.removeEventListener('keydown', esc);
    };
  }, [open]);

  // Never scaffold over an existing folder: react-app, react-app-2, …
  const freeName = (base: string) => {
    const taken = (n: string) => existingPaths.some(p => p === n || p.startsWith(`${n}/`));
    if (!taken(base)) return base;
    let i = 2;
    while (taken(`${base}-${i}`)) i++;
    return `${base}-${i}`;
  };

  const create = async (t: ProjectTemplate) => {
    const folder = freeName(safeFolderName(name, t.defaultName));
    setOpen(false);
    setName('');
    if (t.files) {
      try {
        for (const [path, content] of Object.entries(t.files(folder))) await writeContainerFile(path, content);
      } catch {
        return onUnavailable();
      }
    }
    // New projects go in the room's top folder, wherever the terminal currently is
    if (!run(`cd ${PROJECT_DIR} && ${t.command(folder)}`)) onUnavailable();
  };

  const groups: { id: ProjectTemplate['group']; label: string; icon: React.ElementType }[] = [
    { id: 'Web', label: 'Web', icon: Globe },
    { id: 'App', label: 'Mobile app', icon: Smartphone },
  ];

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        className={`flex items-center gap-1 rounded px-1.5 py-0.5 font-sans text-[11.5px] transition-colors hover:bg-white/10 hover:text-[var(--ink)] ${open ? 'bg-white/10 text-[var(--ink)]' : 'text-[var(--muted)]'}`}
        aria-haspopup="menu"
        aria-expanded={open}
        title="Scaffold a new project in the terminal"
      >
        <LayoutTemplate className="h-3.5 w-3.5" /> New project <ChevronDown className="h-3 w-3" />
      </button>

      {open && (
        <div role="menu" className="item-in absolute right-0 top-full z-30 mt-1 w-72 rounded-lg border border-[var(--line)] bg-[var(--panel)] p-1.5 font-sans shadow-2xl">
          <label className="mb-1.5 flex items-center gap-2 rounded border border-[var(--line)] bg-[var(--bg)] px-2 transition-colors focus-within:border-[var(--coord)]">
            <span className="text-[11px] text-[var(--faint)]">Folder</span>
            <input
              autoFocus
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="auto (e.g. react-app)"
              className="min-w-0 flex-1 bg-transparent py-1 font-mono text-[12px] text-[var(--ink)] outline-none placeholder:text-[var(--faint)]"
              aria-label="Project folder name"
            />
          </label>
          {groups.map(g => (
            <div key={g.id}>
              <p className="flex items-center gap-1.5 px-2 pb-0.5 pt-1.5 text-[10.5px] uppercase tracking-[0.1em] text-[var(--faint)]">
                <g.icon className="h-3 w-3" /> {g.label}
              </p>
              {PROJECT_TEMPLATES.filter(t => t.group === g.id).map(t => (
                <button
                  key={t.id}
                  type="button"
                  role="menuitem"
                  onClick={() => void create(t)}
                  className="flex w-full items-baseline justify-between gap-2 rounded px-2 py-1 text-left transition-colors hover:bg-white/5"
                >
                  <span className="text-[12px] text-[var(--ink)]">{t.label}</span>
                  <span className="truncate font-mono text-[10.5px] text-[var(--faint)]">{t.detail}</span>
                </button>
              ))}
            </div>
          ))}
          <p className="mt-1 border-t border-[var(--line)] px-2 pt-1.5 text-[10.5px] leading-snug text-[var(--faint)]">
            Runs the real tool in the terminal, installs packages and starts the dev server. The first run downloads from npm, so it takes a minute.
          </p>
        </div>
      )}
    </div>
  );
}
