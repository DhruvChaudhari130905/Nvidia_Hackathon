'use client';

import React from 'react';
import type { Membership, Message } from '@/types';
import { LabelChip } from './LabelChip';
import { format } from 'date-fns';
import { resolveUser } from '@/lib/users';

interface FeedItemProps {
  message: Message;
  members: Membership[];
}

export function FeedItem({ message, members }: FeedItemProps) {
  const isAgent = message.user_id === 'agent' || message.user_id === 'mux' || message.user_id === 'coordinator';
  // Real events carry only user_id; the demo embeds the user
  const user = resolveUser(message.user_id, members, message.user);
  const at = new Date(message.created_at);

  return (
    <div className="msg">
      <span
        className={`av ${isAgent ? 'agent-av' : ''}`}
        style={{ background: isAgent ? undefined : user.color }}
      >
        {isAgent ? 'H' : user.initials}
      </span>
      <div>
        <div className="who">
          {isAgent ? 'MUX' : user.name}{' '}
          {!Number.isNaN(at.getTime()) && <time className="mono">{format(at, 'HH:mm')}</time>}
          {message.label && <LabelChip label={message.label} />}
        </div>
        <p>{message.text}</p>
      </div>
    </div>
  );
}
