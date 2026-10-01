'use client';

import React from 'react';
import type { RoomState, PlanItem, User, Membership } from '@/types';
import { ConflictCard } from './ConflictCard';
import { QuestionCard } from './QuestionCard';
import { PlanList } from './PlanList';
import { PlanApproval } from './PlanApproval';

interface SidePanelProps {
  state: RoomState;
  currentUser: User;
  members: Membership[];
  currentUserRole: 'owner' | 'editor' | 'viewer';
  currentUserDomainRole: 'pm' | 'design' | 'eng';
  onVote: (conflictId: string, option: string) => void;
  onOverride: (conflictId: string, option: string) => void;
  onAnswer: (questionId: string, answer: string) => void;
  onPlanUpdate: (items: PlanItem[]) => void | Promise<void>;
  onPlanApprove: () => void | Promise<void>;
}

export function SidePanel({
  state,
  currentUser,
  members,
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
  const isPlanApproved = state.plan.length > 0 && state.plan.some(p => p.status !== 'draft');

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
              currentUser={currentUser}
              currentUserRole={currentUserRole}
              currentUserDomainRole={currentUserDomainRole}
              members={members}
              onVote={onVote}
              onOverride={onOverride}
            />
          ))}

          {openQuestions.map(question => (
            <QuestionCard
              key={question.id}
              question={question}
              currentUserRole={currentUserRole}
              onAnswer={onAnswer}
            />
          ))}

          {/* Only the owner edits and approves the draft; everyone else sees it read-only */}
          {!isPlanApproved && currentUserRole === 'owner' ? (
            <PlanApproval
              plan={state.plan}
              onUpdate={onPlanUpdate}
              onApprove={onPlanApprove}
            />
          ) : (
            <PlanList plan={state.plan} approved={isPlanApproved} />
          )}
        </div>
      </div>
    </aside>
  );
}
