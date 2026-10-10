'use client';

import React, { useEffect, useState } from 'react';
import { Trash2, X } from 'lucide-react';
import { api } from '@/lib/api';
import { deleteRoomFiles } from '@/lib/roomFiles';
import { forgetRoomSnapshots } from '@/lib/packageSnapshots';
import { clearLastRoom } from '@/lib/preferences';

interface DeleteRoomDialogProps {
  room: { id: string; title: string } | null;
  onClose: () => void;
  onDeleted: (roomId: string) => void;
}

// Owner only. Typing the room's name confirms it: once closed, the room is gone for every member and
// there's no way to reopen it from the app.
export function DeleteRoomDialog({ room, onClose, onDeleted }: DeleteRoomDialogProps) {
  const [typed, setTyped] = useState('');
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setTyped('');
    setError(null);
  }, [room?.id]);

  useEffect(() => {
    if (!room) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !deleting) onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [room, deleting, onClose]);

  if (!room) return null;
  const name = room.title.trim();
  const matches = typed.trim() === name;

  const remove = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!matches || deleting) return;
    setDeleting(true);
    setError(null);
    try {
      await api.closeRoom(room.id, 'deleted_by_owner');
      // This browser's copy of the room's files, its saved packages (unless another room shares them) and
      // the header's "last room" link go with it
      await deleteRoomFiles(room.id);
      await forgetRoomSnapshots(room.id);
      clearLastRoom(room.id);
      onDeleted(room.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'The room could not be deleted');
      setDeleting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center glass-overlay p-4" onClick={() => !deleting && onClose()}>
      <div
        className="item-in w-full max-w-md rounded-2xl glass-modal p-6 font-sans text-[var(--ink)]"
        onClick={e => e.stopPropagation()}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="delete-room-title"
        aria-describedby="delete-room-desc"
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 id="delete-room-title" className="flex items-center gap-2 text-lg font-semibold">
            <Trash2 className="h-5 w-5 text-[var(--conflict)]" />
            Delete room
          </h2>
          <button className="btn p-2" onClick={onClose} disabled={deleting} type="button" aria-label="Close">
            <X className="h-5 w-5" />
          </button>
        </div>

        <form onSubmit={remove} className="space-y-4">
          <p id="delete-room-desc" className="text-sm text-[var(--muted)]">
            <span className="font-medium text-[var(--ink)]">{name}</span> will be closed for every member: its files, feed,
            plan and checkpoints disappear from MUX and the link stops working. This can&apos;t be undone from the app.
            Export it to GitHub first if you want to keep the code.
          </p>
          <div>
            <label htmlFor="delete-room-confirm" className="mb-1 block text-sm">
              Type <span className="font-mono font-semibold">{name}</span> to confirm
            </label>
            <input
              id="delete-room-confirm"
              className="w-full rounded-md border border-[var(--line)] bg-[var(--bg)] px-3 py-2 text-sm outline-none focus:border-[var(--conflict)]"
              value={typed}
              onChange={e => setTyped(e.target.value)}
              autoComplete="off"
              autoFocus
              disabled={deleting}
            />
          </div>
          {error && <p className="text-sm text-[var(--conflict)]" role="alert">{error}</p>}
          <div className="flex justify-end gap-2">
            <button className="btn" onClick={onClose} disabled={deleting} type="button">Cancel</button>
            <button
              className="btn flex items-center gap-1.5 border-[var(--conflict)] bg-[var(--conflict)] text-white disabled:cursor-not-allowed disabled:opacity-40"
              disabled={!matches || deleting}
              type="submit"
            >
              <Trash2 className="h-4 w-4" />
              {deleting ? 'Deleting…' : 'Delete room'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
