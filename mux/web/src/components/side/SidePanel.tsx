'use client';

import React from 'react';
import type { RoomState, Conflict, Question, PlanItem } from '@/types';
import { ConflictCard } from './ConflictCard';
import { QuestionCard } from './QuestionCard';
import { PlanList } from './PlanList';
import { CollapseButton } from '@/components/room/PanelRail';

interface SidePanelProps {
  state: RoomState;
  currentUserRole: 'owner' | 'editor' | 'viewer';
  currentUserDomainRole: 'pm' | 'design' | 'eng';
  onVote: (conflictId: string, option: string) => void;
  onOverride: (conflictId: string, option: string) => void;
  onAnswer: (questionId: string, answer: string) => void;
  onPlanUpdate: (items: PlanItem[]) => void;
  onPlanApprove: () => void;
  // Hidden (still mounted) while collapsed to its rail
  collapsed?: boolean;
  onCollapse?: () => void;
}

export function SidePanel({
  state,
  currentUserRole,
  currentUserDomainRole,
  onVote,
  onOverride,
  onAnswer,
  onPlanUpdate,
  onPlanApprove,
  collapsed,
  onCollapse,
}: SidePanelProps) {
  const openConflicts = state.conflicts.filter(c => c.status === 'open' || c.status === 'voting');
  const openQuestions = state.questions.filter(q => q.status === 'open');

  return (
    <aside className="col flex flex-col" aria-label="Decisions and plan" hidden={collapsed}>
      <div className="col-head">
        <span>Decisions & plan</span>
        <span className="flex items-center gap-2">
          <span>{openConflicts.length + openQuestions.length} open</span>
          {onCollapse && <CollapseButton side="right" label="decisions and plan" onCollapse={onCollapse} />}
        </span>
      </div>
      <div className="scroll">
        <div className="side">
          {openConflicts.map(conflict => (
            <ConflictCard
              key={conflict.id}
              conflict={conflict}
              currentUser={state.current_user}
              currentUserRole={currentUserRole}
              currentUserDomainRole={currentUserDomainRole}
              onVote={onVote}
              onOverride={onOverride}
            />
          ))}

          {openQuestions.map(question => (
            <QuestionCard
              key={question.id}
              question={question}
              currentUser={state.current_user}
              currentUserRole={currentUserRole}
              onAnswer={onAnswer}
            />
          ))}

          <PlanList
            plan={state.plan}
            canEdit={currentUserRole !== 'viewer'}
            canApprove={currentUserRole === 'owner'}
            onUpdate={onPlanUpdate}
            onApprove={onPlanApprove}
          />
        </div>
      </div>
    </aside>
  );
}