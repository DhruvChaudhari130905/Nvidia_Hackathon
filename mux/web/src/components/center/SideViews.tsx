'use client';

import React, { useMemo, useState } from 'react';
import {
  Files, Search, GitBranch, Blocks, Settings, ChevronRight, CaseSensitive, X, Undo2, Check, Plus, Trash2,
  WandSparkles, SquareTerminal, Globe, CircleAlert, FileCode2, Package,
} from 'lucide-react';
import { FileIcon } from './FileTree';
import { VsCodeIcon } from './OpenInVsCode';
import type { TerminalFs } from './Terminal';

// VS Code-style activity bar and the side views it switches between (Explorer lives in FileTree)

export type SideView = 'explorer' | 'search' | 'scm' | 'extensions';

const ACTIVITIES: { id: SideView; label: string; icon: React.ElementType }[] = [
  { id: 'explorer', label: 'Explorer', icon: Files },
  { id: 'search', label: 'Search', icon: Search },
  { id: 'scm', label: 'Source Control', icon: GitBranch },
  { id: 'extensions', label: 'Extensions', icon: Blocks },
];

export function ActivityBar({
  view,
  onSelect,
  badges,
  onSettings,
  onOpenVsCode,
}: {
  view: SideView | null;
  onSelect: (view: SideView) => void;
  badges: Partial<Record<SideView, number>>;
  onSettings: () => void;
  onOpenVsCode: () => void;
}) {
  return (
    <nav className="activity-bar" aria-label="Side views">
      {ACTIVITIES.map(({ id, label, icon: Icon }) => (
        <button
          key={id}
          type="button"
          className={`activity-btn ${view === id ? 'on' : ''}`}
          title={label}
          aria-label={label}
          aria-pressed={view === id}
          onClick={() => onSelect(id)}
        >
          <Icon className="h-5 w-5" strokeWidth={1.6} />
          {!!badges[id] && <span className="activity-badge">{badges[id]! > 99 ? '99+' : badges[id]}</span>}
        </button>
      ))}
      <div className="flex-1" />
      <button type="button" className="activity-btn" title="Open in VS Code" aria-label="Open in VS Code" onClick={onOpenVsCode}>
        <VsCodeIcon className="h-[18px] w-[18px] opacity-80" />
      </button>
      <button type="button" className="activity-btn" title="Commands (⌘⇧P)" aria-label="Commands" onClick={onSettings}>
        <Settings className="h-5 w-5" strokeWidth={1.6} />
      </button>
    </nav>
  );
}

function ViewHeader({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-1 px-3 pb-1.5 pt-1">
      <span className="font-sans text-[10.5px] font-medium uppercase tracking-[0.12em] text-[var(--muted)]">{title}</span>
      <div className="flex items-center">{children}</div>
    </div>
  );
}

function HeaderBtn({ label, onClick, children, on = false }: { label: string; onClick: () => void; children: React.ReactNode; on?: boolean }) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      aria-pressed={on}
      onClick={onClick}
      className={`grid h-6 w-6 place-items-center rounded transition-colors hover:bg-white/10 hover:text-[var(--ink)] ${on ? 'bg-white/10 text-[var(--ink)]' : 'text-[var(--muted)]'}`}
    >
      {children}
    </button>
  );
}

function FieldBox({ children }: { children: React.ReactNode }) {
  return (
    <div className="mx-2 mb-1.5 flex items-center gap-1.5 rounded border border-[var(--line)] bg-[var(--bg)] px-2 transition-colors focus-within:border-[var(--coord)]">
      {children}
    </div>
  );
}

const inputCls = 'min-w-0 flex-1 bg-transparent py-1 font-sans text-[12px] text-[var(--ink)] outline-none placeholder:text-[var(--faint)]';

// ───────────── Search ─────────────

const MAX_RESULTS = 500;

export function SearchView({
  paths,
  contentOf,
  onJump,
}: {
  paths: string[];
  contentOf: (path: string) => string;
  onJump: (target: { path: string; line: number; column: number }) => void;
}) {
  const [query, setQuery] = useState('');
  const [matchCase, setMatchCase] = useState(false);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());

  const { groups, total } = useMemo(() => {
    const groups: { path: string; hits: { line: number; column: number; text: string }[] }[] = [];
    let total = 0;
    if (!query) return { groups, total };
    const needle = matchCase ? query : query.toLowerCase();
    for (const path of paths) {
      const hits: { line: number; column: number; text: string }[] = [];
      contentOf(path).split('\n').forEach((text, i) => {
        if (total >= MAX_RESULTS) return;
        const col = (matchCase ? text : text.toLowerCase()).indexOf(needle);
        if (col >= 0) {
          hits.push({ line: i + 1, column: col + 1, text });
          total++;
        }
      });
      if (hits.length) groups.push({ path, hits });
    }
    return { groups, total };
  }, [query, matchCase, paths, contentOf]);

  // Show the match with a little context, trimmed so it fits the row
  const snippet = (text: string, column: number) => {
    const start = Math.max(0, column - 1 - 20);
    const before = (start > 0 ? '…' : '') + text.slice(start, column - 1).trimStart();
    return (
      <>
        {before}
        <mark className="rounded-sm bg-[var(--coder)]/25 text-[var(--ink)]">{text.slice(column - 1, column - 1 + query.length)}</mark>
        {text.slice(column - 1 + query.length, column - 1 + query.length + 60)}
      </>
    );
  };

  return (
    <div className="tree flex flex-col">
      <ViewHeader title="Search">
        {groups.length > 0 && (
          <HeaderBtn label="Collapse all" onClick={() => setCollapsed(new Set(groups.map(g => g.path)))}>
            <ChevronRight className="h-3.5 w-3.5" />
          </HeaderBtn>
        )}
      </ViewHeader>
      <FieldBox>
        <Search className="h-3.5 w-3.5 flex-none text-[var(--faint)]" />
        <input autoFocus value={query} onChange={e => setQuery(e.target.value)} placeholder="Search in files" className={inputCls} aria-label="Search in files" />
        {query && (
          <button type="button" onClick={() => setQuery('')} className="text-[var(--faint)] hover:text-[var(--ink)]" aria-label="Clear search">
            <X className="h-3 w-3" />
          </button>
        )}
        <HeaderBtn label="Match case" on={matchCase} onClick={() => setMatchCase(m => !m)}>
          <CaseSensitive className="h-4 w-4" />
        </HeaderBtn>
      </FieldBox>
      {query && (
        <p className="px-3 pb-1 font-sans text-[11px] text-[var(--faint)]">
          {total === 0 ? 'No results' : `${total}${total >= MAX_RESULTS ? '+' : ''} result${total === 1 ? '' : 's'} in ${groups.length} file${groups.length === 1 ? '' : 's'}`}
        </p>
      )}
      <div className="min-h-0 flex-1 overflow-auto pb-2">
        {groups.map(g => {
          const open = !collapsed.has(g.path);
          const name = g.path.split('/').pop()!;
          return (
            <div key={g.path}>
              <div
                className="tree-row pl-2"
                role="button"
                tabIndex={0}
                onClick={() => setCollapsed(prev => { const n = new Set(prev); if (open) n.add(g.path); else n.delete(g.path); return n; })}
                onKeyDown={e => { if (e.key === 'Enter') (e.currentTarget as HTMLElement).click(); }}
              >
                <ChevronRight className={`h-3.5 w-3.5 flex-none transition-transform ${open ? 'rotate-90' : ''}`} />
                <FileIcon name={name} className="h-3.5 w-3.5 flex-none" />
                <span className="truncate text-[var(--ink)]">{name}</span>
                <span className="truncate text-[11px] text-[var(--faint)]">{g.path.slice(0, -name.length - 1)}</span>
                <span className="ml-auto rounded-full bg-white/10 px-1.5 text-[10px]">{g.hits.length}</span>
              </div>
              {open && g.hits.map(h => (
                <div
                  key={h.line}
                  className="tree-row pl-8"
                  role="button"
                  tabIndex={0}
                  title={`${g.path}:${h.line}`}
                  onClick={() => onJump({ path: g.path, line: h.line, column: h.column })}
                  onKeyDown={e => { if (e.key === 'Enter') onJump({ path: g.path, line: h.line, column: h.column }); }}
                >
                  <span className="truncate whitespace-pre text-[12px]">{snippet(h.text, h.column)}</span>
                </div>
              ))}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ───────────── Source Control ─────────────

export type Change = { path: string; status: 'M' | 'A' | 'D' };
export type Commit = { id: string; message: string; files: number; at: Date };

const STATUS_STYLE: Record<Change['status'], { cls: string; label: string }> = {
  M: { cls: 'text-[#e2c08d]', label: 'Modified' },
  A: { cls: 'text-[#73c991]', label: 'Added' },
  D: { cls: 'text-[var(--conflict)]', label: 'Deleted' },
};

export function diffAgainst(baseline: Map<string, string>, files: Map<string, { content: string }>): Change[] {
  const changes: Change[] = [];
  files.forEach((f, path) => {
    if (!baseline.has(path)) changes.push({ path, status: 'A' });
    else if (baseline.get(path) !== f.content) changes.push({ path, status: 'M' });
  });
  baseline.forEach((_, path) => { if (!files.has(path)) changes.push({ path, status: 'D' }); });
  return changes.sort((a, b) => a.path.localeCompare(b.path));
}

export function SourceControlView({
  changes,
  unsaved,
  commits,
  onOpen,
  onDiscard,
  onCommit,
}: {
  changes: Change[];
  unsaved: string[];
  commits: Commit[];
  onOpen: (path: string) => void;
  onDiscard: (change: Change) => void;
  onCommit: (message: string) => void;
}) {
  const [message, setMessage] = useState('');
  const canCommit = changes.length > 0 && message.trim().length > 0;
  const commit = () => {
    if (!canCommit) return;
    onCommit(message.trim());
    setMessage('');
  };

  const row = (path: string, right: React.ReactNode, onClick?: () => void, actions?: React.ReactNode, deleted = false) => {
    const name = path.split('/').pop()!;
    return (
      <div key={path} className="tree-row pl-3" role="button" tabIndex={0} title={path} onClick={onClick} onKeyDown={e => { if (e.key === 'Enter') onClick?.(); }}>
        <FileIcon name={name} className="h-3.5 w-3.5 flex-none" />
        <span className={`truncate ${deleted ? 'line-through opacity-70' : 'text-[var(--ink)]'}`}>{name}</span>
        <span className="truncate text-[11px] text-[var(--faint)]">{path.slice(0, -name.length - 1)}</span>
        <span className="ml-auto flex flex-none items-center gap-1">
          {actions && <span className="row-actions items-center">{actions}</span>}
          {right}
        </span>
      </div>
    );
  };

  return (
    <div className="tree flex flex-col">
      <ViewHeader title="Source Control" />
      <div className="mx-2 mb-2 space-y-1.5">
        <textarea
          value={message}
          onChange={e => setMessage(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); commit(); } }}
          rows={2}
          placeholder="Message (⌘Enter to commit)"
          className="w-full resize-none rounded border border-[var(--line)] bg-[var(--bg)] px-2 py-1 font-sans text-[12px] text-[var(--ink)] outline-none transition-colors placeholder:text-[var(--faint)] focus:border-[var(--coord)]"
          aria-label="Commit message"
        />
        <button
          type="button"
          onClick={commit}
          disabled={!canCommit}
          className="flex w-full items-center justify-center gap-1.5 rounded bg-[var(--coord)] py-1 font-sans text-[12px] font-medium text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
        >
          <Check className="h-3.5 w-3.5" /> Commit{changes.length ? ` ${changes.length} change${changes.length === 1 ? '' : 's'}` : ''}
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-auto pb-2">
        {unsaved.length > 0 && (
          <>
            <p className="px-3 pb-0.5 pt-1 font-sans text-[10.5px] uppercase tracking-[0.1em] text-[var(--faint)]">Unsaved · {unsaved.length}</p>
            {unsaved.map(p => row(p, <span className="h-2 w-2 rounded-full bg-[var(--coder)]" title="Unsaved" />, () => onOpen(p)))}
          </>
        )}
        <p className="px-3 pb-0.5 pt-1 font-sans text-[10.5px] uppercase tracking-[0.1em] text-[var(--faint)]">Changes · {changes.length}</p>
        {changes.length === 0 && <p className="px-3 py-2 font-sans text-[12px] text-[var(--faint)]">No changes since the last commit.</p>}
        {changes.map(c =>
          row(
            c.path,
            <span className={`w-3 text-center font-mono text-[11px] font-semibold ${STATUS_STYLE[c.status].cls}`} title={STATUS_STYLE[c.status].label}>{c.status}</span>,
            c.status === 'D' ? undefined : () => onOpen(c.path),
            <button
              type="button"
              title="Discard change"
              aria-label={`Discard change to ${c.path}`}
              onClick={e => { e.stopPropagation(); if (window.confirm(`Discard changes to ${c.path}?`)) onDiscard(c); }}
              className="grid h-5 w-5 place-items-center rounded hover:bg-white/10 hover:text-[var(--ink)]"
            >
              <Undo2 className="h-3 w-3" />
            </button>,
            c.status === 'D',
          ),
        )}

        {commits.length > 0 && (
          <>
            <p className="px-3 pb-0.5 pt-3 font-sans text-[10.5px] uppercase tracking-[0.1em] text-[var(--faint)]">Commits this session</p>
            {commits.map(c => (
              <div key={c.id} className="flex items-start gap-2 px-3 py-1 font-sans text-[12px] text-[var(--muted)]">
                <GitBranch className="mt-0.5 h-3 w-3 flex-none text-[var(--coord)]" />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[var(--ink)]">{c.message}</span>
                  <span className="mono text-[10.5px] text-[var(--faint)]">{c.id} · {c.files} file{c.files === 1 ? '' : 's'} · {c.at.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                </span>
              </div>
            ))}
          </>
        )}
      </div>
    </div>
  );
}

// ───────────── Extensions ─────────────

const BUILT_IN = [
  { icon: FileCode2, name: 'TypeScript & JavaScript', detail: 'IntelliSense, go to definition, rename and type errors.' },
  { icon: WandSparkles, name: 'Formatter', detail: 'Format document from the editor toolbar (⇧⌥F).' },
  { icon: SquareTerminal, name: 'Terminal', detail: 'Sandbox shell for this room’s files (Ctrl+`).' },
  { icon: Globe, name: 'Live Preview', detail: 'Runs the app in a WebContainer next to the code.' },
  { icon: CircleAlert, name: 'Problems', detail: 'Collects errors and warnings from every open file.' },
];

type Pkg = { dependencies?: Record<string, string>; devDependencies?: Record<string, string>; [k: string]: unknown };

export function ExtensionsView({ fs, onOpenVsCode }: { fs: TerminalFs; onOpenVsCode: () => void }) {
  const [query, setQuery] = useState('');
  const [adding, setAdding] = useState('');
  const [dev, setDev] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const raw = fs.files.get('package.json')?.content;
  const pkg = useMemo<Pkg | null>(() => {
    if (!raw) return null;
    try {
      return JSON.parse(raw);
    } catch {
      return null;
    }
  }, [raw]);

  const q = query.trim().toLowerCase();
  const match = (s: string) => !q || s.toLowerCase().includes(q);
  const deps = (key: 'dependencies' | 'devDependencies') => Object.entries(pkg?.[key] ?? {}).filter(([n]) => match(n));

  const writePkg = async (next: Pkg) => fs.write('package.json', `${JSON.stringify(next, null, 2)}\n`);

  const add = async () => {
    const spec = adding.trim();
    if (!spec) return;
    if (!pkg) return setError(raw ? 'package.json is not valid JSON' : 'No package.json in this project');
    const [name, version] = spec.startsWith('@') ? [`@${spec.slice(1).split('@')[0]}`, spec.slice(1).split('@')[1]] : spec.split('@');
    const key = dev ? 'devDependencies' : 'dependencies';
    const section = { ...(pkg[key] ?? {}), [name]: version ? `^${version.replace(/^\^/, '')}` : 'latest' };
    await writePkg({ ...pkg, [key]: Object.fromEntries(Object.entries(section).sort(([a], [b]) => a.localeCompare(b))) });
    setAdding('');
    setError(null);
  };

  const remove = async (name: string) => {
    if (!pkg) return;
    const next: Pkg = { ...pkg };
    for (const key of ['dependencies', 'devDependencies'] as const) {
      if (next[key]?.[name]) {
        const { [name]: _removed, ...rest } = next[key]!;
        next[key] = rest;
      }
    }
    await writePkg(next);
  };

  const heading = (text: string, count: number) => (
    <p className="px-3 pb-0.5 pt-2 font-sans text-[10.5px] uppercase tracking-[0.1em] text-[var(--faint)]">{text} · {count}</p>
  );

  const depRow = ([name, version]: [string, string]) => (
    <div key={name} className="tree-row pl-3" title={`${name}@${version}`}>
      <Package className="h-3.5 w-3.5 flex-none text-[var(--coder)]" />
      <span className="truncate text-[var(--ink)]">{name}</span>
      <span className="ml-auto flex flex-none items-center gap-1">
        <span className="row-actions items-center">
          <button type="button" title="Uninstall" aria-label={`Uninstall ${name}`} onClick={() => remove(name)} className="grid h-5 w-5 place-items-center rounded hover:bg-white/10 hover:text-[var(--conflict)]">
            <Trash2 className="h-3 w-3" />
          </button>
        </span>
        <span className="row-meta text-[11px] text-[var(--faint)]">{version}</span>
      </span>
    </div>
  );

  const builtIn = BUILT_IN.filter(b => match(b.name));
  const prod = deps('dependencies');
  const devDeps = deps('devDependencies');

  return (
    <div className="tree flex flex-col">
      <ViewHeader title="Extensions" />
      <FieldBox>
        <Search className="h-3.5 w-3.5 flex-none text-[var(--faint)]" />
        <input value={query} onChange={e => setQuery(e.target.value)} placeholder="Search extensions & packages" className={inputCls} aria-label="Search extensions" />
      </FieldBox>

      <div className="min-h-0 flex-1 overflow-auto pb-2">
        <div className="mx-2 mb-1 rounded-md border border-[var(--line)] bg-[var(--bg)] p-2 font-sans">
          <p className="mb-1.5 text-[11.5px] leading-snug text-[var(--muted)]">
            Need a marketplace extension? Open this room in desktop VS Code, where every extension works.
          </p>
          <button type="button" onClick={onOpenVsCode} className="btn inline-flex items-center gap-1.5 !py-1 text-[12px]">
            <VsCodeIcon className="h-3.5 w-3.5" /> Open in VS Code
          </button>
        </div>
        {heading('Installed', builtIn.length)}
        {builtIn.map(b => (
          <div key={b.name} className="flex items-start gap-2 px-3 py-1.5 font-sans">
            <span className="grid h-7 w-7 flex-none place-items-center rounded bg-white/5 text-[var(--coord)]">
              <b.icon className="h-4 w-4" />
            </span>
            <span className="min-w-0 flex-1">
              <span className="flex items-center gap-1.5 text-[12px] text-[var(--ink)]">
                {b.name}
                <span className="rounded bg-white/10 px-1 text-[9.5px] uppercase tracking-wide text-[var(--muted)]">Built-in</span>
              </span>
              <span className="block text-[11px] leading-snug text-[var(--faint)]">{b.detail}</span>
            </span>
          </div>
        ))}

        {heading('Dependencies', prod.length)}
        {prod.map(depRow)}
        {heading('Dev dependencies', devDeps.length)}
        {devDeps.map(depRow)}
        {!pkg && <p className="px-3 py-1 font-sans text-[12px] text-[var(--faint)]">{raw ? 'package.json is not valid JSON.' : 'No package.json in this project.'}</p>}
      </div>

      <div className="border-t border-[var(--line)] p-2">
        <div className="flex items-center gap-1.5 rounded border border-[var(--line)] bg-[var(--bg)] px-2 transition-colors focus-within:border-[var(--coord)]">
          <input
            value={adding}
            onChange={e => setAdding(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') add(); }}
            placeholder="Add package, e.g. zod@3"
            className={inputCls}
            aria-label="Package to add"
          />
          <HeaderBtn label="Add as dev dependency" on={dev} onClick={() => setDev(d => !d)}>
            <span className="font-mono text-[10px]">-D</span>
          </HeaderBtn>
          <HeaderBtn label="Add package" onClick={add}>
            <Plus className="h-3.5 w-3.5" />
          </HeaderBtn>
        </div>
        {error && <p className="mt-1 font-sans text-[11px] text-[var(--conflict)]">{error}</p>}
      </div>
    </div>
  );
}
