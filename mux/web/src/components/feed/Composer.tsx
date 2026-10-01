'use client';

import React, { useState, FormEvent } from 'react';

interface ComposerProps {
  onSend: (text: string) => void | Promise<void>;
  disabled?: boolean;
}

export function Composer({ onSend, disabled }: ComposerProps) {
  const [text, setText] = useState('');
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const trimmed = text.trim();
    if (!trimmed || disabled || sending) return;
    // Cleared right away so the box feels instant; put back if the send fails
    setText('');
    setError(null);
    setSending(true);
    try {
      await onSend(trimmed);
    } catch (err) {
      setText(current => current || trimmed);
      setError(err instanceof Error && err.message ? `Message not sent: ${err.message}` : 'Message not sent. Try again.');
    } finally {
      setSending(false);
    }
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
          aria-invalid={!!error}
          aria-describedby={error ? 'msgError' : undefined}
        />
        <button className="btn primary" type="submit" disabled={disabled || sending || !text.trim()}>
          Send
        </button>
      </form>
      {error && (
        <div id="msgError" role="alert" className="hint" style={{ color: 'var(--conflict)' }}>
          {error}
        </div>
      )}
      <div className="hint">
        Try &ldquo;add a pricing page&rdquo;, &ldquo;stop&rdquo;, or &ldquo;make headings bigger&rdquo;. The coordinator labels each message.
      </div>
    </div>
  );
}