'use client';

import React, { useMemo, useState } from 'react';
import { X, FolderDown, FileArchive, ExternalLink, RefreshCw, ArrowDownToLine, Blocks, Check } from 'lucide-react';
import {
  canUseFolders, diffFolder, downloadBlob, exportFiles, linkedFolderName, projectSlug, readFolder, recommendedExtensions,
  saveToFolder, zipFiles, type FileContents,
} from '@/lib/vscodeExport';

// "Open in VS Code": hand the room's files to desktop VS Code (every extension, Microsoft's included),
// then bring the edits made there back into the room.

interface OpenInVsCodeProps {
  roomId: string;
  roomTitle: string;
  files: Map<string, { content: string }>;
  lockedFiles: Set<string>;
  onWrite: (path: string, content: string) => void | Promise<void>;
  onApplied: (paths: string[]) => void;
  onClose: () => void;
}

type Pending = { changed: string[]; added: string[]; missing: string[]; folder: FileContents; skipped: number };

export function OpenInVsCode({ roomId, roomTitle, files, lockedFiles, onWrite, onApplied, onClose }: OpenInVsCodeProps) {
  const slug = projectSlug(roomTitle);
  const folderMode = canUseFolders();
  const [folder, setFolder] = useState<string | null>(() => linkedFolderName(roomId));
  const [zipped, setZipped] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [status, setStatus] = useState<{ text: string; tone: 'ok' | 'err' } | null>(null);
  const [pending, setPending] = useState<Pending | null>(null);

  const contents = useMemo<FileContents>(() => new Map(Array.from(files, ([p, f]) => [p, f.content])), [files]);
  const recs = useMemo(() => recommendedExtensions(contents), [contents]);
  const exported = folder || zipped;

  const run = async (label: string, fn: () => Promise<void>) => {
    setBusy(label);
    setStatus(null);
    try {
      await fn();
    } catch (e) {
      // Closing the folder picker isn't an error worth showing
      if ((e as Error).name !== 'AbortError') setStatus({ text: (e as Error).message, tone: 'err' });
    } finally {
      setBusy(null);
    }
  };

  const save = (pickNew: boolean) =>
    run('save', async () => {
      const name = await saveToFolder(roomId, exportFiles(contents), pickNew);
      setFolder(name);
      setPending(null);
      setStatus({ text: `Saved ${contents.size} files to “${name}”`, tone: 'ok' });
    });

  const downloadZip = () => {
    downloadBlob(zipFiles(exportFiles(contents), slug), `${slug}.zip`);
    setZipped(true);
    setStatus({ text: `Downloaded ${slug}.zip`, tone: 'ok' });
  };

  const check = () =>
    run('check', async () => {
      const { files: folderFiles, skipped } = await readFolder(roomId);
      const diff = diffFolder(contents, folderFiles);
      if (!diff.changed.length && !diff.added.length) {
        setPending(null);
        setStatus({ text: 'No changes in the folder: the room is up to date', tone: 'ok' });
      } else setPending({ ...diff, folder: folderFiles, skipped });
    });

  const apply = () =>
    run('apply', async () => {
      if (!pending) return;
      const paths = [...pending.changed, ...pending.added].filter(p => !lockedFiles.has(p));
      for (const p of paths) await onWrite(p, pending.folder.get(p)!);
      onApplied(paths);
      const locked = pending.changed.length + pending.added.length - paths.length;
      setPending(null);
      setStatus({ text: `Brought back ${paths.length} file${paths.length === 1 ? '' : 's'}${locked ? ` · ${locked} locked file${locked === 1 ? '' : 's'} skipped` : ''}`, tone: 'ok' });
    });

  const step = (n: number, title: string, done: boolean, body: React.ReactNode) => (
    <div className="flex gap-3">
      <span className={`mt-0.5 grid h-5 w-5 flex-none place-items-center rounded-full font-mono text-[10.5px] ${done ? 'bg-[var(--coord)] text-white' : 'border border-[var(--line)] text-[var(--muted)]'}`}>
        {done ? <Check className="h-3 w-3" /> : n}
      </span>
      <div className="min-w-0 flex-1 pb-4">
        <p className="mb-1.5 text-[12.5px] font-medium text-[var(--ink)]">{title}</p>
        {body}
      </div>
    </div>
  );

  const btn = 'btn inline-flex items-center gap-1.5 disabled:cursor-not-allowed disabled:opacity-50';
  const list = (label: string, paths: string[], cls: string) =>
    paths.length > 0 && (
      <div>
        <p className="text-[11px] text-[var(--muted)]">{label} · {paths.length}</p>
        <ul className="max-h-24 overflow-auto font-mono text-[11px]">
          {paths.map(p => (
            <li key={p} className={`truncate ${lockedFiles.has(p) ? 'text-[var(--faint)] line-through' : cls}`} title={lockedFiles.has(p) ? `${p} is locked and will be skipped` : p}>{p}</li>
          ))}
        </ul>
      </div>
    );

  return (
    <div className="absolute inset-0 z-40 grid place-items-center bg-black/50 p-4 backdrop-blur-[2px]" onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
      <div role="dialog" aria-modal="true" aria-labelledby="vscode-title" className="item-in max-h-full w-full max-w-md overflow-auto rounded-xl border border-[var(--line)] bg-[var(--panel)] p-4 font-sans shadow-2xl">
        <div className="mb-1 flex items-center justify-between">
          <h2 id="vscode-title" className="flex items-center gap-2 text-[14px] font-semibold text-[var(--ink)]">
            <VsCodeIcon className="h-4 w-4" /> Open in VS Code
          </h2>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Close"><X className="h-3.5 w-3.5" /></button>
        </div>
        <p className="mb-4 text-[12px] leading-relaxed text-[var(--muted)]">
          Work on this room in VS Code on your computer, with any extension from the marketplace. The room isn&apos;t synced live: bring your edits back when you&apos;re done.
        </p>

        {step(1, folderMode ? 'Save the project to a folder' : 'Download the project', !!exported, (
          <div className="flex flex-wrap gap-2">
            {folderMode && (
              <button type="button" className={btn} disabled={!!busy} onClick={() => save(false)}>
                <FolderDown className="h-4 w-4" /> {folder ? `Save again to “${folder}”` : 'Choose folder…'}
              </button>
            )}
            {folderMode && folder && (
              <button type="button" className="text-[11.5px] text-[var(--muted)] underline-offset-2 hover:text-[var(--ink)] hover:underline" disabled={!!busy} onClick={() => save(true)}>
                Use another folder
              </button>
            )}
            <button type="button" className={btn} disabled={!!busy} onClick={downloadZip}>
              <FileArchive className="h-4 w-4" /> Download .zip
            </button>
          </div>
        ))}

        {step(2, 'Open it in VS Code', false, (
          <>
            <a href="vscode://" className={btn}>
              <ExternalLink className="h-4 w-4" /> Launch VS Code
            </a>
            <p className="mt-1.5 text-[11.5px] leading-relaxed text-[var(--faint)]">
              Then <span className="text-[var(--muted)]">File → Open Folder…</span> and pick{' '}
              <span className="mono text-[var(--muted)]">{folder ?? slug}</span>{folder ? '' : ' (unzip it first)'}, or run{' '}
              <code className="mono rounded bg-[var(--bg)] px-1 text-[var(--muted)]">code {folder ?? slug}</code>.
            </p>
            <div className="mt-2 rounded-md border border-[var(--line)] bg-[var(--bg)] p-2">
              <p className="mb-1 flex items-center gap-1.5 text-[11px] text-[var(--muted)]"><Blocks className="h-3 w-3" /> VS Code will offer to install these recommended extensions</p>
              <div className="flex flex-wrap gap-1">
                {recs.map(r => (
                  <a key={r} href={`https://marketplace.visualstudio.com/items?itemName=${r}`} target="_blank" rel="noreferrer" className="rounded bg-white/5 px-1.5 py-0.5 font-mono text-[10.5px] text-[var(--muted)] hover:text-[var(--ink)]">{r}</a>
                ))}
              </div>
            </div>
          </>
        ))}

        {step(3, 'Bring your edits back', false, folderMode ? (
          <>
            <button type="button" className={btn} disabled={!folder || !!busy} onClick={check}>
              <RefreshCw className={`h-4 w-4 ${busy === 'check' ? 'animate-spin' : ''}`} /> Check folder for changes
            </button>
            {!folder && <p className="mt-1.5 text-[11.5px] text-[var(--faint)]">Save to a folder first so MUX can read your edits back.</p>}
            {pending && (
              <div className="item-in mt-2 space-y-1.5 rounded-md border border-[var(--line)] bg-[var(--bg)] p-2">
                {list('Changed', pending.changed, 'text-[#e2c08d]')}
                {list('New', pending.added, 'text-[#73c991]')}
                {pending.missing.length > 0 && (
                  <p className="text-[11px] text-[var(--faint)]">{pending.missing.length} room file{pending.missing.length === 1 ? ' is' : 's are'} missing from the folder; they stay in the room.</p>
                )}
                {pending.skipped > 0 && <p className="text-[11px] text-[var(--faint)]">{pending.skipped} binary or large file{pending.skipped === 1 ? '' : 's'} skipped.</p>}
                <button type="button" className={`${btn} mt-1`} disabled={!!busy} onClick={apply}>
                  <ArrowDownToLine className="h-4 w-4" /> Apply to room
                </button>
              </div>
            )}
          </>
        ) : (
          <p className="text-[11.5px] leading-relaxed text-[var(--faint)]">
            This browser can&apos;t read local folders, so use <span className="text-[var(--muted)]">Upload</span> in the Explorer (or drop files onto it) to bring changed files back. Chrome or Edge can do it in one click.
          </p>
        ))}

        {status && (
          <p className={`item-in text-[11.5px] ${status.tone === 'err' ? 'text-[var(--conflict)]' : 'text-[var(--coder)]'}`}>{status.text}</p>
        )}
      </div>
    </div>
  );
}

// VS Code's mark, simplified, in the editor's blue
export function VsCodeIcon({ className = 'h-5 w-5' }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true">
      <path fill="#2489ca" d="M17.6 2.2 9.7 9.4 4.9 5.8 3 6.7v10.6l1.9.9 4.8-3.6 7.9 7.2 3.4-1.6V3.8l-3.4-1.6ZM5 14.6V9.4l2.7 2.6L5 14.6Zm12.4 1.5-4.6-4.1 4.6-4.1v8.2Z" />
    </svg>
  );
}
