'use client';

import React, { useEffect, useState } from 'react';
import { FlaskConical, LogOut } from 'lucide-react';
import { exitDemo, isBrowserDemo } from '@/lib/demo';

// Shown while this browser is in demo mode. Demo mode swaps the whole app onto sample data, so
// rooms made here are local samples; this makes that visible and gives a one-click way out.
export function DemoBanner({ inline = false }: { inline?: boolean }) {
  const [on, setOn] = useState(false);
  useEffect(() => setOn(isBrowserDemo()), []);
  if (!on) return null;

  if (inline) {
    return (
      <button
        type="button"
        onClick={exitDemo}
        className="btn flex items-center gap-1.5 whitespace-nowrap !border-[#d29922]/50 !text-[#e3b341]"
        title="This room is sample data that lives in this browser. Exit to get back to your real rooms."
      >
        <FlaskConical className="h-4 w-4" />
        <span className="hidden sm:inline">Demo · Exit</span>
      </button>
    );
  }

  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-4 z-[55] flex justify-center px-4">
      <div role="status" className="glass-modal pointer-events-auto flex items-center gap-3 rounded-full py-1.5 pl-4 pr-1.5 text-body-sm text-on-surface-variant">
        <FlaskConical className="h-4 w-4 flex-none text-[#e3b341]" aria-hidden="true" />
        <span>
          <span className="font-semibold text-on-surface">You&apos;re exploring the demo.</span>{' '}
          <span className="hidden sm:inline">Rooms here are samples that stay in this browser.</span>
        </span>
        <button
          type="button"
          onClick={exitDemo}
          className="flex items-center gap-1.5 rounded-full bg-white/10 px-3 py-1.5 font-semibold text-on-surface transition-colors hover:bg-white/15"
        >
          <LogOut className="h-3.5 w-3.5" aria-hidden="true" /> Exit demo
        </button>
      </div>
    </div>
  );
}
