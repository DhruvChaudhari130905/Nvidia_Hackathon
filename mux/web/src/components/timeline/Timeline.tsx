'use client';

import React from 'react';
import type { Checkpoint } from '@/types';
import { format } from 'date-fns';

interface TimelineProps {
  checkpoints: Checkpoint[];
  currentCheckpoint: string | null;
  onSelectCheckpoint: (checkpointId: string) => void;
  onReturnToLatest: () => void;
  isRewound: boolean;
}

export function Timeline({
  checkpoints,
  currentCheckpoint,
  onSelectCheckpoint,
  onReturnToLatest,
  isRewound,
}: TimelineProps) {
  const sortedCheckpoints = [...checkpoints].sort((a, b) => a.seq - b.seq);

  return (
    <footer className="timeline">
      <div className="tl-head">
        <span>Timeline</span>
        {isRewound && (
          <>
            <span className="note">Viewing checkpoint {currentCheckpoint}. Later work is greyed out, not deleted.</span>
            <button className="btn" onClick={onReturnToLatest} type="button">Return to latest</button>
          </>
        )}
      </div>
      <div className="track-wrap">
        <div className="track">
          {sortedCheckpoints.length === 0 && (
            <p className="relative z-[1] mx-auto bg-[var(--panel)] px-3 text-xs text-[var(--faint)]">
              No checkpoints yet. Each passing build adds one here, and you can rewind to any of them.
            </p>
          )}
          {sortedCheckpoints.map((checkpoint, index) => {
            const isCurrent = checkpoint.id === currentCheckpoint;
            const isFuture = !!currentCheckpoint && sortedCheckpoints.findIndex(c => c.id === currentCheckpoint) !== -1 && index > sortedCheckpoints.findIndex(c => c.id === currentCheckpoint);
            const isLatest = index === sortedCheckpoints.length - 1;

            return (
              <button
                key={checkpoint.id}
                className={`timeline-node ${isCurrent ? 'now' : ''} ${isLatest && !isRewound ? 'live' : ''} ${isFuture ? 'greyed' : ''}`}
                onClick={() => !isFuture && onSelectCheckpoint(checkpoint.id)}
                disabled={isFuture}
                type="button"
                data-i={index}
              >
                <span className="pt">{index}</span>
                <span className="lb">
                  {checkpoint.plan[checkpoint.plan.length - 1]?.title || `Checkpoint ${index}`}
                  <small>
                    {format(new Date(checkpoint.created_at), 'HH:mm')}
                    {checkpoint.sandbox_snapshot_uuid && ' · Nebius'}
                  </small>
                </span>
              </button>
            );
          })}
        </div>
      </div>
    </footer>
  );
}