'use client';

import React from 'react';
import type { PlanItem } from '@/types';

interface PlanListProps {
  plan: PlanItem[];
  approved: boolean;
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

export function PlanList({ plan, approved }: PlanListProps) {
  return (
    <div className="plan">
      <div className="plan-head">
        <span>Plan</span>
        <span>{approved ? 'approved · ready' : 'draft · waiting for the owner'}</span>
      </div>
      {plan.length === 0 && <span className="m">No plan yet. The coordinator drafts one from the room&apos;s messages.</span>}
      {plan.map(item => (
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
    </div>
  );
}