'use client';

import React from 'react';
import type { RoomState, Conflict, Question, PlanItem } from '@/types';
import { ConflictCard } from './ConflictCard';
import { QuestionCard } from './QuestionCard';
import { PlanList } from './PlanList';
import { PlanApproval } from './PlanApproval';

interface SidePanelProps {
  state: RoomState;
  currentUserRole: 'owner' | 'editor' | 'viewer';
  currentUserDomainRole: 'pm' | 'design' | 'eng';
  onVote: (conflictId: string, option: string) => void;
  onOverride: (conflictId: string, option: string) => void;
  onAnswer: (questionId: string, answer: string) => void;
  onPlanUpdate: (items: PlanItem[]) => void;
  onPlanApprove: () => void;
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
}: SidePanelProps) {
  const openConflicts = state.conflicts.filter(c => c.status === 'open' || c.status === 'voting');
  const openQuestions = state.questions.filter(q => q.status === 'open');
  const isPlanApproved = state.plan.some(p => p.status !== 'draft');

  return (
    <aside className="col flex flex-col" aria-label="Decisions and plan">
      <div className="col-head">
        <span>Decisions & plan</span>
        <span>{openConflicts.length + openQuestions.length} open</span>
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

          {isPlanApproved ? (
            <PlanList
              plan={state.plan}
              approved={true}
              canEdit={currentUserRole !== 'viewer'}
            />
          ) : (
            <PlanApproval
              plan={state.plan}
              onUpdate={onPlanUpdate}
              onApprove={onPlanApprove}
            />
          )}
        </div>
      </div>
    </aside>
  );
}