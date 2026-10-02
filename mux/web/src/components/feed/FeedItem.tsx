'use client';

import React from 'react';
import type { Message, User } from '@/types';
import { LabelChip } from './LabelChip';
import { format } from 'date-fns';

interface FeedItemProps {
  message: Message;
  currentUser: User;
}

export function FeedItem({ message, currentUser }: FeedItemProps) {
  const isAgent = message.user_id === 'agent' || message.user_id === 'mux';
  const isNote = message.to === 'team';

  return (
    <div className={`msg ${isNote ? 'note' : ''}`}>
      <span
        className={`av ${isAgent ? 'agent-av' : ''}`}
        style={{ background: isAgent ? undefined : message.user.color }}
      >
        {isAgent ? 'H' : message.user.initials}
      </span>
      <div>
        <div className="who">
          {isAgent ? 'MUX' : message.user.name}{' '}
          <time className="mono">{format(new Date(message.created_at), 'HH:mm')}</time>
          {isNote ? (
            <span className="note-tag mono">team</span>
          ) : message.label ? (
            <LabelChip label={message.label} />
          ) : (
            !isAgent && <span className="chip pending">waiting for coordinator</span>
          )}
        </div>
        <p>{message.text}</p>
      </div>
    </div>
  );
}
