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
  const isCurrentUser = message.user_id === currentUser.id;
  const isAgent = message.user_id === 'agent' || message.user_id === 'mux';

  return (
    <div className="msg">
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
          {message.label && <LabelChip label={message.label} />}
        </div>
        <p>{message.text}</p>
      </div>
    </div>
  );
}