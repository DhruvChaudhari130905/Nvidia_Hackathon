'use client';

import React from 'react';

interface ConflictBannerProps {
  conflictId: string;
  taskId: string;
  options: string[];
}

// Pinned above the feed while a vote is open: what's being decided, and that the coder skipped it
export function ConflictBanner({ taskId, options }: ConflictBannerProps) {
  const choices = options.length > 1 ? `${options.slice(0, -1).join(', ')} or ${options[options.length - 1]}` : options[0];
  return (
    <div className="banner item-in" id="banner">
      <b>Vote open</b> {choices ? `${choices}? ` : ''}Coder skipped task {taskId.replace(/^t/, '')} until it closes.
    </div>
  );
}
