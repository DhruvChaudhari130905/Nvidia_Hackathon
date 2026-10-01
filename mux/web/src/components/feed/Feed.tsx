'use client';

import React from 'react';
import type { Membership, Message } from '@/types';
import { ConflictBanner } from './ConflictBanner';
import { Composer } from './Composer';
import { FeedItem } from './FeedItem';

interface FeedProps {
  messages: Message[];
  members: Membership[];
  onSendMessage: (text: string) => Promise<void>;
  activeConflict?: { id: string; taskId: string; options: string[] };
}

export function Feed({
  messages,
  members,
  onSendMessage,
  activeConflict,
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
        <span className="mono">coder</span>
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
            <FeedItem key={message.id} message={message} members={members} />
          ))}
          <div ref={feedEndRef} />
        </div>
      </div>

      <Composer onSend={onSendMessage} />
    </section>
  );
}
