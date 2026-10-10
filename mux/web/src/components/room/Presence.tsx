'use client';

import React from 'react';
import type { User } from '@/types';

interface PresenceUser {
  user: User;
  active: boolean;
  typing?: boolean;
}

interface PresenceProps {
  users: PresenceUser[];
  typingUser?: string;
}

export function Presence({ users, typingUser }: PresenceProps) {
  const activeUsers = users.filter(u => u.active);

  return (
    <>
      <div className="flex -space-x-2">
        {activeUsers.slice(0, 5).map((presence, index) => (
          <span
            key={presence.user.id}
            className="av"
            style={{ background: presence.user.color, zIndex: 5 - index }}
            title={`${presence.user.name} · ${presence.user.id}`}
          >
            {presence.user.initials}
            {presence.active && <span className="dot" />}
          </span>
        ))}
        {activeUsers.length > 5 && (
          <span className="av" style={{ background: 'var(--line)' }}>
            +{activeUsers.length - 5}
          </span>
        )}
      </div>
      {typingUser && (
        <span className="typing">
          {activeUsers.find(u => u.user.id === typingUser)?.user.name || 'Someone'} is typing
          <span className="typing-dots" aria-hidden="true"><i /><i /><i /></span>
        </span>
      )}
    </>
  );
}