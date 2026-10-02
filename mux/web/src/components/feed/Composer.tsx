'use client';

import React, { useState, FormEvent } from 'react';
import type { MessageTo } from '@/types';

interface ComposerProps {
  onSend: (text: string, to: MessageTo) => void;
  disabled?: boolean;
  // Viewers can't post team notes (the server enforces this too)
  canPostTeam?: boolean;
}

// "@sam can you check this" reads as a note to a person, not an instruction for the agent
const MENTION_START = /^@\w/;

export function Composer({ onSend, disabled, canPostTeam = true }: ComposerProps) {
  const [text, setText] = useState('');
  const [to, setTo] = useState<MessageTo>('agent');
  // Set once the person picks a side themselves, so the @mention switch doesn't fight them
  const [picked, setPicked] = useState(false);

  const target: MessageTo = canPostTeam ? to : 'agent';

  const handleChange = (value: string) => {
    setText(value);
    if (!value) setPicked(false);
    if (canPostTeam && !picked && MENTION_START.test(value)) setTo('team');
  };

  const pick = (next: MessageTo) => {
    setTo(next);
    setPicked(true);
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    const trimmed = text.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed, target);
    setText('');
    setTo('agent');
    setPicked(false);
  };

  return (
    <div className="composer">
      {canPostTeam && (
        <div className="tabs to-toggle" role="tablist" aria-label="Send to">
          <button type="button" role="tab" className="tab" aria-selected={target === 'agent'} onClick={() => pick('agent')}>
            Agent
          </button>
          <button type="button" role="tab" className="tab" aria-selected={target === 'team'} onClick={() => pick('team')}>
            Team
          </button>
        </div>
      )}
      <form onSubmit={handleSubmit}>
        <label htmlFor="msgInput" className="mono" hidden>
          Message
        </label>
        <input
          id="msgInput"
          autoComplete="off"
          placeholder={target === 'team' ? 'Note to the team…' : 'Message the agent…'}
          value={text}
          onChange={(e) => handleChange(e.target.value)}
          disabled={disabled}
        />
        <button className="btn primary" type="submit" disabled={disabled || !text.trim()}>
          Send
        </button>
      </form>
      <div className="hint">
        {target === 'team'
          ? 'Team notes go to people in the room only. The agent never sees them.'
          : 'Try "add a pricing page", "stop", or "make headings bigger". The coordinator labels each message.'}
      </div>
    </div>
  );
}
