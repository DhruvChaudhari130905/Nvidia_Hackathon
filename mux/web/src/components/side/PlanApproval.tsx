'use client';

import React, { useEffect, useState } from 'react';
import type { PlanItem } from '@/types';
import { GripVertical, Trash2, Plus } from 'lucide-react';

interface PlanApprovalProps {
  plan: PlanItem[];
  onUpdate: (items: PlanItem[]) => void | Promise<void>;
  onApprove: () => void | Promise<void>;
}

export function PlanApproval({ plan, onUpdate, onApprove }: PlanApprovalProps) {
  const [items, setItems] = useState<PlanItem[]>(plan);
  // Unsaved local edits; while there are none, the editor follows the server's draft
  const [dirty, setDirty] = useState(false);
  const [newItemTitle, setNewItemTitle] = useState('');
  const [dragIndex, setDragIndex] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!dirty) setItems(plan);
  }, [plan, dirty]);

  const edit = (next: PlanItem[]) => {
    setItems(next);
    setDirty(true);
  };

  const handleAddItem = () => {
    if (!newItemTitle.trim()) return;
    edit([...items, { id: `temp-${Date.now()}`, title: newItemTitle.trim(), status: 'draft' }]);
    setNewItemTitle('');
  };

  const handleRemoveItem = (id: string) => {
    edit(items.filter(item => item.id !== id));
  };

  const handleReorder = (fromIndex: number, toIndex: number) => {
    if (fromIndex === toIndex) return;
    const newItems = [...items];
    const [removed] = newItems.splice(fromIndex, 1);
    newItems.splice(toIndex, 0, removed);
    edit(newItems);
  };

  const handleSave = async () => {
    setBusy(true);
    try {
      await onUpdate(items);
      setDirty(false);
    } catch {
      // the room page reports the error; keep the edits
    } finally {
      setBusy(false);
    }
  };

  // Approving saves pending edits first, so they aren't lost
  const handleApprove = async () => {
    setBusy(true);
    try {
      if (dirty) {
        await onUpdate(items);
        setDirty(false);
      }
      await onApprove();
    } catch {
      // the room page reports the error; keep the edits
    } finally {
      setBusy(false);
    }
  };

  const handleCancel = () => {
    setItems(plan);
    setDirty(false);
  };

  return (
    <div className="card">
      <div className="card-head">
        <span>Plan (draft)</span>
        <button
          className="btn primary"
          onClick={handleApprove}
          type="button"
          disabled={busy || items.length === 0}
          title={items.length === 0 ? 'Add at least one task first' : undefined}
        >
          Approve
        </button>
      </div>

      <div className="space-y-2">
        {items.length === 0 && (
          <p className="text-sm text-[var(--muted)]">No tasks yet. The coordinator drafts a plan from the room&apos;s messages, or add tasks below.</p>
        )}
        {items.map((item, index) => (
          <div
            key={item.id}
            className={`flex items-center gap-2 p-2 bg-[var(--panel)] rounded border ${dragIndex !== null && dragIndex !== index ? 'border-dashed' : ''} border-[var(--line)]`}
            onDragOver={e => { if (dragIndex !== null) e.preventDefault(); }}
            onDrop={e => {
              e.preventDefault();
              if (dragIndex !== null) handleReorder(dragIndex, index);
              setDragIndex(null);
            }}
          >
            <span
              draggable
              onDragStart={e => { setDragIndex(index); e.dataTransfer.effectAllowed = 'move'; }}
              onDragEnd={() => setDragIndex(null)}
              className="cursor-grab"
              aria-label={`Drag to reorder ${item.title}`}
            >
              <GripVertical className="w-4 h-4 text-[var(--muted)]" />
            </span>
            <input
              type="text"
              value={item.title}
              onChange={e => edit(items.map((i, idx) => idx === index ? { ...i, title: e.target.value } : i))}
              className="flex-1 bg-transparent border-none outline-none text-[var(--ink)]"
            />
            <span className="text-xs text-[var(--muted)] mono capitalize">{item.status}</span>
            <button
              className="btn p-1.5 text-[var(--conflict)] hover:bg-[var(--conflict)]/10"
              onClick={() => handleRemoveItem(item.id)}
              type="button"
              aria-label={`Remove ${item.title}`}
            >
              <Trash2 className="w-4 h-4" />
            </button>
          </div>
        ))}

        <div className="flex gap-2 pt-2 border-t border-[var(--line)]">
          <input
            type="text"
            value={newItemTitle}
            onChange={e => setNewItemTitle(e.target.value)}
            placeholder="Add a task..."
            className="flex-1 bg-[var(--bg)] border border-[var(--line)] rounded px-3 py-2"
            onKeyDown={e => e.key === 'Enter' && handleAddItem()}
          />
          <button className="btn" onClick={handleAddItem} type="button" aria-label="Add task">
            <Plus className="w-4 h-4" />
          </button>
        </div>
      </div>

      <div className="flex justify-end gap-2 mt-4 pt-4 border-t border-[var(--line)]">
        <button className="btn" onClick={handleCancel} type="button" disabled={busy || !dirty}>Cancel</button>
        <button className="btn primary" onClick={handleSave} type="button" disabled={busy || !dirty}>Save Plan</button>
      </div>
    </div>
  );
}
