import React from 'react';
import Link from 'next/link';

// MUX wordmark with a small multiplexer glyph (several inputs merging into one output)
export function Logo({ href = '/' }: { href?: string }) {
  return (
    <Link href={href} className="flex items-center gap-space-sm" aria-label="MUX home">
      <span className="grid h-8 w-8 place-items-center rounded-lg border border-outline-variant/60 bg-surface-container-high">
        <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" strokeWidth="2" strokeLinecap="round">
          <path d="M4 6h5l6 6M4 12h11M4 18h5l6-6" stroke="#3b82f6" />
          <path d="M15 12h5" stroke="#06b6d4" />
          <circle cx="20" cy="12" r="1.5" fill="#06b6d4" stroke="none" />
        </svg>
      </span>
      <span className="font-code text-headline-md font-bold tracking-tight text-on-surface">MUX</span>
    </Link>
  );
}
