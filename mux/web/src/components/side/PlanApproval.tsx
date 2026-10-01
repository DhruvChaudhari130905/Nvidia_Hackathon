'use client';

import React, { useState } from 'react';
import type { PlanItem } from '@/types';
import { GripVertical, Trash2, Plus } from 'lucide-react';

interface PlanApprovalProps {
  plan: PlanItem[];
  onUpdate: (items: PlanItem[]) => void;
  onApprove: () => void;
}

export function PlanApproval({ plan, onUpdate, onApprove }: PlanApprovalProps) {
  const [items, setItems] = useState<PlanItem[]>(plan);
  const [newItemTitle, setNewItemTitle] = useState('');

  const handleAddItem = () => {
    if (!newItemTitle.trim()) return;
    const newItem: PlanItem = {
      id: `temp-${Date.now()}`,
      title: newItemTitle.trim(),
      status: 'draft',
    };
    setItems([...items, newItem]);
    setNewItemTitle('');
  };

  const handleRemoveItem = (id: string) => {
    setItems(items.filter(item => item.id !== id));
  };

  const handleReorder = (fromIndex: number, toIndex: number) => {
    const newItems = [...items];
    const [removed] = newItems.splice(fromIndex, 1);
    newItems.splice(toIndex, 0, removed);
    setItems(newItems);
  };

  const handleSave = () => {
    onUpdate(items);
  };

  return (
    <div className="card">
      <div className="card-head">
        <span>Plan (draft)</span>
        <button className="btn primary" onClick={onApprove} type="button">Approve</button>
      </div>

      <div className="space-y-2">
        {items.map((item, index) => (
          <div key={item.id} className="flex items-center gap-2 p-2 bg-[var(--panel)] rounded border border-[var(--line)]">
            <GripVertical className="w-4 h-4 text-[var(--muted)] cursor-grab" />
            <input
              type="text"
              value={item.title}
              onChange={e => setItems(items.map((i, idx) => idx === index ? { ...i, title: e.target.value } : i))}
              className="flex-1 bg-transparent border-none outline-none text-[var(--ink)]"
            />
            <span className="text-xs text-[var(--muted)] mono capitalize">{item.status}</span>
            <button
              className="btn p-1.5 text-[var(--conflict)] hover:bg-[var(--conflict)]/10"
              onClick={() => handleRemoveItem(item.id)}
              type="button"
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
          <button className="btn" onClick={handleAddItem} type="button">
            <Plus className="w-4 h-4" />
          </button>
        </div>
      </div>

      <div className="flex justify-end gap-2 mt-4 pt-4 border-t border-[var(--line)]">
        <button className="btn" onClick={() => setItems(plan)} type="button">Cancel</button>
        <button className="btn primary" onClick={handleSave} type="button">Save Plan</button>
      </div>
    </div>
  );
}