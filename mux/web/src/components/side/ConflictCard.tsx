'use client';

import React, { useMemo, useState } from 'react';
import type { Conflict, DomainRole, Evidence, Membership, User, Vote } from '@/types';
import { formatCountdown, useSecondsUntil } from '@/lib/countdown';

// The domain role whose vote counts double for each conflict domain
const DOMAIN_ROLE_FOR: Record<Conflict['domain'], DomainRole> = {
  ui: 'design',
  architecture: 'eng',
  scope: 'pm',
};

// Same weighting as the backend's vote_weight
const voteWeight = (role: DomainRole, domain: Conflict['domain']) => (DOMAIN_ROLE_FOR[domain] === role ? 2 : 1);

interface ConflictCardProps {
  conflict: Conflict;
  currentUser: User;
  currentUserRole: 'owner' | 'editor' | 'viewer';
  currentUserDomainRole: 'pm' | 'design' | 'eng';
  members: Membership[];
  onVote: (conflictId: string, option: string) => void;
  onOverride: (conflictId: string, option: string) => void;
}

const citationLink = (c: Evidence['citations'][number]) => (typeof c === 'string' ? { title: c, url: c } : c);

export function ConflictCard({
  conflict,
  currentUser,
  currentUserRole,
  currentUserDomainRole,
  members,
  onVote,
  onOverride,
}: ConflictCardProps) {
  const isClosed = conflict.status === 'closed';
  const timeLeft = useSecondsUntil(conflict.expires_at, !isClosed);
  // Our vote, shown right away; the server's conflict.vote event confirms it
  const [pendingVote, setPendingVote] = useState<string | null>(null);
  const [overriding, setOverriding] = useState(false);
  const [overridden, setOverridden] = useState(false);

  // One vote per person (the latest), with our pending vote in place of our old one
  const latestVotes = useMemo(() => {
    const byUser = new Map<string, Vote>();
    conflict.votes.forEach(v => byUser.set(v.user_id, v));
    if (pendingVote) {
      byUser.set(currentUser.id, {
        conflict_id: conflict.id,
        user_id: currentUser.id,
        option: pendingVote,
        weight: voteWeight(currentUserDomainRole, conflict.domain),
      });
    }
    return Array.from(byUser.values());
  }, [conflict, pendingVote, currentUser.id, currentUserDomainRole]);

  const votes: Record<string, number> = {};
  conflict.options.forEach(opt => { votes[opt] = 0; });
  latestVotes.forEach(v => { votes[v.option] = (votes[v.option] || 0) + v.weight; });
  const totalVotes = Object.values(votes).reduce((a, b) => a + b, 0);
  const userVote = latestVotes.find(v => v.user_id === currentUser.id)?.option ?? null;
  const eligibleVoters = members.filter(m => m.permission !== 'viewer').length;

  // Voting stops at the deadline; the result shows only once the server closes the vote
  const votingOpen = !isClosed && !overridden && timeLeft > 0;

  const handleVote = (option: string) => {
    if (!votingOpen || currentUserRole === 'viewer') return;
    onVote(conflict.id, option);
    setPendingVote(option);
  };

  const handleOverride = (option: string) => {
    if (currentUserRole !== 'owner') return;
    onOverride(conflict.id, option);
    setOverriding(false);
    setOverridden(true);
  };

  return (
    <div className="card conflict">
      <div className="card-head">
        <span className="card-kind">Conflict · task {conflict.task_id}</span>
        {!isClosed && <span className="timer mono">{formatCountdown(timeLeft)}</span>}
      </div>
      <h4>{conflict.options.length > 1 ? `What should we do?` : conflict.options[0]}</h4>
      <p className="why">
        {conflict.domain === 'ui' && 'Design decision needed. '}
        {conflict.domain === 'architecture' && 'Architecture decision needed. '}
        {conflict.domain === 'scope' && 'Scope decision needed. '}
        The coder skipped this task until the vote closes.
      </p>

      {isClosed ? (
        <div className="resolved">
          Decided: {conflict.result} ({conflict.resolved_by === currentUser.id ? 'your override' : 'vote closed'}). Pinned in the room log.
        </div>
      ) : (
        <>
          <div className="opts">
            {conflict.options.map(option => (
              <button
                key={option}
                className="opt"
                onClick={() => (overriding ? handleOverride(option) : handleVote(option))}
                aria-pressed={userVote === option}
                disabled={overriding ? false : !votingOpen || currentUserRole === 'viewer'}
                data-opt={option}
                type="button"
              >
                <span className="lbl">{overriding ? `Pick: ${option}` : option}</span>
                <span className="n mono">{votes[option] || 0}</span>
                <span className="meter">
                  <i style={{ width: totalVotes > 0 ? `${((votes[option] || 0) / totalVotes) * 100}%` : '0%' }} />
                </span>
              </button>
            ))}
          </div>
          {!votingOpen && (
            <div className="resolved">{overridden ? 'Override sent. Waiting for the room to update…' : 'Voting time is up. Waiting for the result…'}</div>
          )}
        </>
      )}

      <div className="voters">
        <span>
          {latestVotes.length} of {eligibleVoters} {eligibleVoters === 1 ? 'person' : 'people'} voted{' '}
          {DOMAIN_ROLE_FOR[conflict.domain] === currentUserDomainRole && '· your role counts 2×'}
        </span>
        {currentUserRole === 'owner' && !isClosed && !overridden && (
          <button className="linkbtn" onClick={() => setOverriding(o => !o)} type="button">
            {overriding ? 'Cancel override' : 'Owner override'}
          </button>
        )}
      </div>

      {conflict.evidence.length > 0 && (
        <div className="mt-4 p-3 bg-[var(--panel)] rounded border border-[var(--line)]">
          <p className="text-sm font-medium mb-2">Tavily Evidence</p>
          {conflict.evidence.map((ev, i) => (
            <div key={i} className="text-xs text-[var(--muted)] mb-2">
              {ev.query && <p className="font-mono">{ev.query}</p>}
              <p>{ev.summary}</p>
              {ev.citations.map(citationLink).map((c, j) => (
                <a key={j} href={c.url} title={c.title} target="_blank" rel="noopener noreferrer" className="text-[var(--coord)] underline text-xs mr-1">
                  [{j + 1}]
                </a>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
