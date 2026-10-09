'use client';

import React from 'react';
import type { Checkpoint } from '@/types';
import { format } from 'date-fns';
import { PanelBottomClose, PanelBottomOpen } from 'lucide-react';

interface TimelineProps {
  checkpoints: Checkpoint[];
  currentCheckpoint: string | null;
  onSelectCheckpoint: (checkpointId: string) => void;
  onReturnToLatest: () => void;
  isRewound: boolean;
  // Collapsed, only the header row shows and Preview/Code gets the height
  collapsed?: boolean;
  onToggle?: (open: boolean) => void;
}

export function Timeline({
  checkpoints,
  currentCheckpoint,
  onSelectCheckpoint,
  onReturnToLatest,
  isRewound,
  collapsed,
  onToggle,
}: TimelineProps) {
  const sortedCheckpoints = [...checkpoints].sort((a, b) => a.seq - b.seq);

  return (
    <footer className={`timeline${collapsed ? ' collapsed' : ''}`}>
      <div className="tl-head">
        <span>Timeline</span>
        {collapsed && <span>{sortedCheckpoints.length} checkpoint{sortedCheckpoints.length === 1 ? '' : 's'}</span>}
        {isRewound && (
          <>
            <span className="note">Viewing checkpoint {currentCheckpoint}. Later work is greyed out, not deleted.</span>
            <button className="btn" onClick={onReturnToLatest} type="button">Return to latest</button>
          </>
        )}
        {onToggle && (
          <button
            className="panel-collapse ml-auto"
            onClick={() => onToggle(!!collapsed)}
            type="button"
            aria-expanded={!collapsed}
            aria-label={collapsed ? 'Show timeline' : 'Hide timeline'}
            title={collapsed ? 'Show timeline' : 'Hide timeline'}
          >
            {collapsed ? <PanelBottomOpen className="h-3.5 w-3.5" /> : <PanelBottomClose className="h-3.5 w-3.5" />}
          </button>
        )}
      </div>
      <div className="track-wrap" hidden={collapsed}>
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