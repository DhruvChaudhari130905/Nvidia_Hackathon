'use client';

import React, { useEffect, useRef, useState } from 'react';
import { Plus, Trash2, X, SquareTerminal, Play, CircleAlert, TriangleAlert, ChevronUp, ChevronDown } from 'lucide-react';
import { type TerminalFs } from './Terminal';
import { ShellTerminal, type ShellControl } from './ShellTerminal';
import { NewProjectMenu } from './NewProjectMenu';
import { TerminalDirPicker } from './TerminalDirPicker';
import { absoluteDir, detectStartDir, getSavedStartDir, setSavedStartDir, shellQuote } from '@/lib/terminalCwd';
import { RunOutput, type RunState } from './RunOutput';
import { FileIcon } from './FileTree';

export interface Problem {
  path: string;
  line: number;
  column: number;
  message: string;
  severity: 'error' | 'warning';
}

interface BottomPanelProps {
  roomId: string;
  view: PanelView;
  onViewChange: (view: PanelView) => void;
  onClose: () => void;
  height: number;
  onResize: (height: number) => void;
  fs: TerminalFs;
  problems: Problem[];
  onJump: (p: Problem) => void;
  // Run file: a command for the shell, or the Output view for remote runs
  shellRequest: { id: number; command: string } | null;
  onShellRequestFailed: (id: number) => void;
  run: RunState | null;
  stdin: string;
  onStdinChange: (value: string) => void;
  onRun: () => void;
  onStopRun: () => void;
}

export type PanelView = 'terminal' | 'problems' | 'output';

// Resizable panel under the editor with terminal sessions and the problems list
export function BottomPanel({
  roomId, view, onViewChange, onClose, height, onResize, fs, problems, onJump, shellRequest, onShellRequestFailed, run, stdin, onStdinChange, onRun, onStopRun,
}: BottomPanelProps) {
  const [sessions, setSessions] = useState<number[]>([1]);
  const [activeSession, setActiveSession] = useState(1);
  const nextId = useRef(2);
  const [maximized, setMaximized] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  // Folder new terminals start in: the user's choice for this room, else the detected project folder
  const paths = Array.from(fs.files.keys());
  const [savedDir, setSavedDir] = useState<string | null>(() => getSavedStartDir(roomId));
  const autoDir = detectStartDir(paths);
  const startDir = savedDir ?? autoDir;
  const chooseDir = (dir: string | null) => {
    setSavedStartDir(roomId, dir);
    setSavedDir(dir);
    // Move the open shell there too
    controls.current.get(activeSession)?.run(`cd ${shellQuote(absoluteDir(dir ?? autoDir))}`);
  };

  // Each session hands over a control so the New project menu can type into the active shell
  const controls = useRef(new Map<number, ShellControl>());
  const controlSetters = useRef(new Map<number, (c: ShellControl | null) => void>());
  const controlFor = (id: number) => {
    if (!controlSetters.current.has(id)) {
      controlSetters.current.set(id, c => { if (c) controls.current.set(id, c); else controls.current.delete(id); });
    }
    return controlSetters.current.get(id)!;
  };
  const runInShell = (command: string) => controls.current.get(activeSession)?.run(command) ?? false;
  // Child effects run first, so the active session's control is registered by the time this fires
  const lastRequest = useRef(0);
  useEffect(() => {
    if (!shellRequest || shellRequest.id === lastRequest.current) return;
    lastRequest.current = shellRequest.id;
    if (!runInShell(shellRequest.command)) onShellRequestFailed(shellRequest.id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shellRequest]);

  const showNotice = (text: string) => {
    setNotice(text);
    setTimeout(() => setNotice(n => (n === text ? null : n)), 4000);
  };

  const addSession = () => {
    const id = nextId.current++;
    setSessions(s => [...s, id]);
    setActiveSession(id);
    onViewChange('terminal');
  };

  const killSession = (id: number) => {
    const rest = sessions.filter(s => s !== id);
    if (!rest.length) {
      onClose();
      const fresh = nextId.current++;
      setSessions([fresh]);
      setActiveSession(fresh);
      return;
    }
    setSessions(rest);
    if (activeSession === id) setActiveSession(rest[rest.length - 1]);
  };

  // Drag the top edge to resize
  const startDrag = (e: React.MouseEvent) => {
    e.preventDefault();
    const startY = e.clientY;
    const startH = height;
    const move = (ev: MouseEvent) => onResize(Math.min(600, Math.max(120, startH + (startY - ev.clientY))));
    const up = () => {
      window.removeEventListener('mousemove', move);
      window.removeEventListener('mouseup', up);
      document.body.style.cursor = '';
    };
    document.body.style.cursor = 'row-resize';
    window.addEventListener('mousemove', move);
    window.addEventListener('mouseup', up);
  };

  const errors = problems.filter(p => p.severity === 'error').length;
  const warnings = problems.length - errors;

  return (
    <div className="bottom-panel item-in" style={{ height: maximized ? '70%' : height }}>
      <div className="panel-resize" onMouseDown={startDrag} role="separator" aria-orientation="horizontal" aria-label="Resize panel" />
      <div className="panel-head">
        <div className="flex items-center gap-1">
          <button type="button" className={`panel-tab ${view === 'terminal' ? 'on' : ''}`} onClick={() => onViewChange('terminal')}>
            <SquareTerminal className="h-3.5 w-3.5" /> Terminal
          </button>
          <button type="button" className={`panel-tab ${view === 'problems' ? 'on' : ''}`} onClick={() => onViewChange('problems')}>
            <CircleAlert className="h-3.5 w-3.5" /> Problems
            {problems.length > 0 && (
              <span className={`rounded-full px-1.5 text-[10px] font-semibold ${errors ? 'bg-[var(--conflict)]/20 text-[var(--conflict)]' : 'bg-[#d29922]/20 text-[#d29922]'}`}>{problems.length}</span>
            )}
          </button>
          <button type="button" className={`panel-tab ${view === 'output' ? 'on' : ''}`} onClick={() => onViewChange('output')}>
            <Play className="h-3.5 w-3.5" /> Output
            {run?.status === 'running' && <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--coder)]" />}
          </button>
        </div>
        <div className="flex items-center gap-0.5">
          {view === 'terminal' && (
            <>
              {notice && <span className="item-in mr-2 font-sans text-[11px] text-[#d29922]">{notice}</span>}
              <TerminalDirPicker paths={paths} current={startDir} saved={savedDir} autoDir={autoDir} onChoose={chooseDir} />
              <NewProjectMenu
                existingPaths={Array.from(fs.files.keys())}
                run={runInShell}
                onUnavailable={() => showNotice('Wait for the shell to finish booting (a real Node.js terminal is needed)')}
              />
              {sessions.length > 1 && (
                <div className="mr-1 flex items-center gap-0.5">
                  {sessions.map((id, i) => (
                    <button key={id} type="button" onClick={() => setActiveSession(id)} className={`rounded px-1.5 py-0.5 font-mono text-[11px] ${activeSession === id ? 'bg-white/10 text-[var(--ink)]' : 'text-[var(--muted)] hover:text-[var(--ink)]'}`}>
                      {i + 1}: jsh
                    </button>
                  ))}
                </div>
              )}
              <button type="button" className="icon-btn" title="New terminal" aria-label="New terminal" onClick={addSession}><Plus className="h-3.5 w-3.5" /></button>
              <button type="button" className="icon-btn" title="Kill terminal" aria-label="Kill terminal" onClick={() => killSession(activeSession)}><Trash2 className="h-3.5 w-3.5" /></button>
            </>
          )}
          <button type="button" className="icon-btn" title={maximized ? 'Restore panel' : 'Maximize panel'} aria-label={maximized ? 'Restore panel' : 'Maximize panel'} onClick={() => setMaximized(m => !m)}>
            {maximized ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronUp className="h-3.5 w-3.5" />}
          </button>
          <button type="button" className="icon-btn" title="Close panel (Ctrl+`)" aria-label="Close panel" onClick={onClose}><X className="h-3.5 w-3.5" /></button>
        </div>
      </div>

      <div className="min-h-0 flex-1">
        {sessions.map(id => (
          <div key={id} className="h-full" hidden={view !== 'terminal' || id !== activeSession}>
            <ShellTerminal roomId={roomId} fs={fs} active={view === 'terminal' && id === activeSession} onExit={() => killSession(id)} onControl={controlFor(id)} startDir={startDir} />
          </div>
        ))}
        {view === 'output' && (
          <RunOutput run={run} stdin={stdin} onStdinChange={onStdinChange} onRun={onRun} onStop={onStopRun} />
        )}
        {view === 'problems' && (
          <div className="h-full overflow-auto py-1 font-mono text-[12px]">
            {problems.length === 0 ? (
              <p className="px-3 py-2 font-sans text-[12px] text-[var(--faint)]">No problems detected in open files. Syntax errors show up here as you type.</p>
            ) : (
              <>
                <p className="px-3 pb-1 font-sans text-[11px] text-[var(--faint)]">{errors} error{errors === 1 ? '' : 's'} · {warnings} warning{warnings === 1 ? '' : 's'}</p>
                {problems.map((p, i) => (
                  <button key={i} type="button" onClick={() => onJump(p)} className="flex w-full items-start gap-2 px-3 py-1 text-left transition-colors hover:bg-white/5">
                    {p.severity === 'error' ? <CircleAlert className="mt-0.5 h-3.5 w-3.5 flex-none text-[var(--conflict)]" /> : <TriangleAlert className="mt-0.5 h-3.5 w-3.5 flex-none text-[#d29922]" />}
                    <span className="min-w-0 flex-1 text-[#c9d1d9]">{p.message}</span>
                    <span className="flex flex-none items-center gap-1 text-[var(--faint)]">
                      <FileIcon name={p.path} className="h-3 w-3" />
                      {p.path.split('/').pop()}:{p.line}:{p.column}
                    </span>
                  </button>
                ))}
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
