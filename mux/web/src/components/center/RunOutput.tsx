'use client';

import React from 'react';
import { Play, Square, CircleCheck, CircleX, Loader2 } from 'lucide-react';
import type { RunResult } from '@/lib/codeRunner';
import { FileIcon } from './FileTree';

export interface RunState {
  path: string;
  language: string;
  status: 'running' | 'done' | 'error';
  result?: RunResult;
  error?: string;
}

interface RunOutputProps {
  run: RunState | null;
  stdin: string;
  onStdinChange: (value: string) => void;
  onRun: () => void;
  onStop: () => void;
}

export function RunOutput({ run, stdin, onStdinChange, onRun, onStop }: RunOutputProps) {
  if (!run) {
    return (
      <p className="px-3 py-2 font-sans text-[12px] text-[var(--faint)]">
        Open a Python, C, C++, Java, Go, Rust or other source file and press Run (▶ in the editor toolbar, or F5). Output shows up here.
      </p>
    );
  }
  const r = run.result;
  const name = run.path.split('/').pop()!;

  return (
    <div className="flex h-full min-h-0">
      <div className="min-w-0 flex-1 overflow-auto px-3 py-2 font-mono text-[12px] leading-relaxed">
        <div className="mb-1.5 flex flex-wrap items-center gap-2 font-sans text-[11.5px]">
          <FileIcon name={name} className="h-3.5 w-3.5" />
          <span className="text-[var(--ink)]">{run.path}</span>
          {run.status === 'running' && <span className="flex items-center gap-1 text-[var(--coder)]"><Loader2 className="h-3 w-3 animate-spin" /> Running {run.language}…</span>}
          {r && (
            <span className={`flex items-center gap-1 ${r.ok ? 'text-[var(--coder)]' : 'text-[var(--conflict)]'}`}>
              {r.ok ? <CircleCheck className="h-3 w-3" /> : <CircleX className="h-3 w-3" />}
              exit {r.exitCode} · {(r.ms / 1000).toFixed(1)}s
            </span>
          )}
          {r && <span className="text-[var(--faint)]">{r.compilerName} · via wandbox.org</span>}
        </div>

        {run.status === 'error' && <pre className="whitespace-pre-wrap text-[var(--conflict)]">{run.error}</pre>}
        {r?.compileOutput && <pre className={`mb-1 whitespace-pre-wrap ${r.ok ? 'text-[#d29922]' : 'text-[var(--conflict)]'}`}>{r.compileOutput}</pre>}
        {r?.stdout && <pre className="whitespace-pre-wrap text-[#c9d1d9]">{r.stdout}</pre>}
        {r?.stderr && <pre className="whitespace-pre-wrap text-[var(--conflict)]">{r.stderr}</pre>}
        {r && !r.stdout && !r.stderr && !r.compileOutput && <p className="font-sans text-[11.5px] text-[var(--faint)]">(no output)</p>}
      </div>

      <div className="flex w-56 flex-none flex-col border-l border-[var(--line)] p-2">
        <label htmlFor="run-stdin" className="mb-1 font-sans text-[10.5px] uppercase tracking-[0.1em] text-[var(--faint)]">Input (stdin)</label>
        <textarea
          id="run-stdin"
          value={stdin}
          onChange={e => onStdinChange(e.target.value)}
          placeholder="Text your program reads with input(), cin, Scanner…"
          className="min-h-0 flex-1 resize-none rounded border border-[var(--line)] bg-[var(--bg)] px-2 py-1 font-mono text-[11.5px] text-[var(--ink)] outline-none placeholder:font-sans placeholder:text-[var(--faint)] focus:border-[var(--coord)]"
        />
        {run.status === 'running' ? (
          <button type="button" className="btn mt-2 flex items-center justify-center gap-1.5" onClick={onStop}>
            <Square className="h-3.5 w-3.5" /> Stop
          </button>
        ) : (
          <button type="button" className="btn mt-2 flex items-center justify-center gap-1.5" onClick={onRun}>
            <Play className="h-3.5 w-3.5" /> Run again
          </button>
        )}
      </div>
    </div>
  );
}
