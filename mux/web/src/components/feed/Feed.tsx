'use client';

import React from 'react';
import type { Message, User } from '@/types';
import { LabelChip } from './LabelChip';
import { ConflictBanner } from './ConflictBanner';
import { Composer } from './Composer';
import { format } from 'date-fns';

interface FeedProps {
  messages: Message[];
  currentUser: User;
  onSendMessage: (text: string) => void;
  activeConflict?: { id: string; taskId: string; options: string[] };
  activeQuestion?: { id: string; taskId: string };
}

export function Feed({
  messages,
  currentUser,
  onSendMessage,
  activeConflict,
  activeQuestion,
}: FeedProps) {
  const feedEndRef = React.useRef<HTMLDivElement>(null);
  const scrollAreaRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    feedEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  return (
    <section className="col flex flex-col" aria-label="Agent feed">
      <div className="col-head">
        <span>Feed</span>
        <span className="mono">coder · Super</span>
      </div>

      {activeConflict && (
        <ConflictBanner
          conflictId={activeConflict.id}
          taskId={activeConflict.taskId}
          options={activeConflict.options}
        />
      )}

      <div className="scroll" ref={scrollAreaRef}>
        <div className="feed">
          {messages.map((message) => (
            <FeedItem key={message.id} message={message} currentUser={currentUser} />
          ))}
          <div ref={feedEndRef} />
        </div>
      </div>

      <Composer onSend={onSendMessage} />
    </section>
  );
}

interface FeedItemProps {
  message: Message;
  currentUser: User;
}

function FeedItem({ message, currentUser }: FeedItemProps) {
  const isCurrentUser = message.user_id === currentUser.id;
  const isAgent = message.user_id === 'agent';

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
          <LabelChip label={message.label} />
        </div>
        <p>{message.text}</p>
      </div>
    </div>
  );
}