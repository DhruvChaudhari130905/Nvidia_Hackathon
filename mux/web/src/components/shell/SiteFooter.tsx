import React from 'react';
import Link from 'next/link';
import { Logo } from './Logo';

const COLUMNS = [
  { title: 'Product', links: [['Overview', '/'], ['Rooms', '/dashboard'], ['Sandbox', '/sandbox'], ['Pricing', '/pricing']] },
  { title: 'Learn', links: [['How rooms work', '/docs#rooms'], ['Votes & conflicts', '/docs#conflicts'], ['Checkpoints', '/docs#checkpoints'], ['GitHub export', '/docs#export']] },
  { title: 'Account', links: [['Sign in', '/login'], ['Profile', '/profile'], ['Contact sales', '/pricing#contact']] },
];

export function SiteFooter() {
  return (
    <footer className="relative z-10 w-full shrink-0 overflow-hidden border-t border-white/5 bg-surface-container-lowest/90 font-ui backdrop-blur">
      <div className="pointer-events-none absolute -top-24 left-1/2 h-48 w-[70%] -translate-x-1/2 rounded-full bg-primary/10 blur-3xl" />
      <div className="relative mx-auto grid max-w-6xl grid-cols-2 gap-space-xl px-gutter pb-space-lg pt-16 md:grid-cols-5 md:px-space-xl">
        <div className="col-span-2">
          <Logo />
          <p className="mt-space-md max-w-xs text-body-md text-on-surface-variant">
            Collaborative real-time coding rooms. Eight people steering, one agent building.
          </p>
          <div className="mt-space-lg inline-flex items-center gap-space-sm rounded-full bg-white/[0.04] px-space-md py-1.5 font-code text-code-sm text-on-surface-variant ring-1 ring-white/10">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[#3fb950] opacity-75" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-[#3fb950]" />
            </span>
            All systems operational
          </div>
        </div>
        {COLUMNS.map(col => (
          <div key={col.title}>
            <h4 className="mb-space-md font-code text-label-md uppercase tracking-wider text-outline">{col.title}</h4>
            <ul className="space-y-space-sm">
              {col.links.map(([label, href]) => (
                <li key={href}>
                  <Link href={href} className="group inline-flex items-center gap-1 text-body-md text-on-surface-variant transition-colors hover:text-on-surface">
                    <span className="h-px w-0 bg-secondary transition-all duration-300 group-hover:w-3" />
                    {label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      <div
        className="pointer-events-none relative select-none text-center font-headline text-[18vw] font-bold leading-[0.8] tracking-tighter text-transparent md:text-[14vw]"
        style={{ WebkitTextStroke: '1px rgba(59,130,246,0.18)' }}
        aria-hidden="true"
      >
        MUX
      </div>
      <div className="relative border-t border-white/5 px-gutter py-space-md text-center text-body-sm text-outline">
        © {new Date().getFullYear()} MUX Inc. Collaborative Real-Time Coding Workspace. All rights reserved.
      </div>
    </footer>
  );
}
