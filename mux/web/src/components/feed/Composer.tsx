'use client';

import React, { useState, FormEvent } from 'react';

interface ComposerProps {
  onSend: (text: string) => void;
  disabled?: boolean;
}

export function Composer({ onSend, disabled }: ComposerProps) {
  const [text, setText] = useState('');

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    const trimmed = text.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setText('');
  };

  return (
    <div className="composer">
      <form onSubmit={handleSubmit}>
        <label htmlFor="msgInput" className="mono" hidden>
          Message
        </label>
        <input
          id="msgInput"
          autoComplete="off"
          placeholder="Message the room…"
          value={text}
          onChange={(e) => setText(e.target.value)}
          disabled={disabled}
        />
        <button className="btn primary" type="submit" disabled={disabled || !text.trim()}>
          Send
        </button>
      </form>
      <div className="hint">
        Try "add a pricing page", "stop", or "make headings bigger". The coordinator labels each message.
      </div>
    </div>
  );
}