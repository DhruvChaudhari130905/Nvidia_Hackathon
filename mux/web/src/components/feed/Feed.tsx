'use client';

import React from 'react';
import type { Message, MessageTo, User } from '@/types';
import { FeedItem } from './FeedItem';
import { ConflictBanner } from './ConflictBanner';
import { Composer } from './Composer';

interface FeedProps {
  messages: Message[];
  currentUser: User;
  onSendMessage: (text: string, to: MessageTo) => void;
  canPostTeam?: boolean;
  activeConflict?: { id: string; taskId: string; options: string[] };
  activeQuestion?: { id: string; taskId: string };
}

export function Feed({
  messages,
  currentUser,
  onSendMessage,
  canPostTeam,
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

      <Composer onSend={onSendMessage} canPostTeam={canPostTeam} />
    </section>
  );
}
