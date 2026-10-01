'use client';

import React from 'react';
import type { PlanItem } from '@/types';

interface PlanListProps {
  plan: PlanItem[];
  approved: boolean;
  onEdit?: (items: PlanItem[]) => void;
  onApprove?: () => void;
  canEdit: boolean;
}

const statusStyles: Record<string, string> = {
  done: 'plan-item done',
  doing: 'plan-item doing',
  todo: 'plan-item',
  draft: 'plan-item',
  skipped_conflict: 'plan-item blocked',
  skipped_question: 'plan-item waiting',
};

// Shown under the title when the item has no notes of its own
const statusLabels: Record<string, string> = {
  doing: 'coder working',
  skipped_conflict: 'skipped · vote open',
  skipped_question: 'skipped · waiting on answer',
};

export function PlanList({ plan, approved, onEdit, onApprove, canEdit }: PlanListProps) {
  return (
    <div className="plan">
      <div className="plan-head">
        <span>Plan</span>
        <span>{approved ? 'approved' : 'draft'} {approved ? '· ready' : canEdit ? '· click to edit' : ''}</span>
      </div>
      {plan.map((item, index) => (
        <div key={item.id} className={statusStyles[item.status]}>
          <span className="ic" />
          <div>
            <span className="t">{item.title}</span>
            {(item.notes || statusLabels[item.status]) && <span className={`m ${item.status === 'skipped_conflict' ? 'c' : item.status === 'skipped_question' ? 'a' : item.status === 'todo' && item.notes?.includes('queued') ? 'q' : ''}`}>
              {item.notes || statusLabels[item.status]}
            </span>}
          </div>
        </div>
      ))}
      {!approved && canEdit && onApprove && (
        <button className="btn primary mt-2" onClick={onApprove} type="button">
          Approve Plan
        </button>
      )}
    </div>
  );
}