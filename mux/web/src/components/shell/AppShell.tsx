'use client';

import React from 'react';
import { ShaderBackground } from './ShaderBackground';
import { SiteHeader, type NavKey } from './SiteHeader';
import { SiteFooter } from './SiteFooter';

interface AppShellProps {
  // 'profile' has no nav item; it's reached from the avatar in the header
  active: NavKey | 'profile';
  children: React.ReactNode;
  hero?: React.ReactNode; // full-width band above the content column
}

// Layout for the signed-in screens (Rooms, Sandbox, Profile): the same top menu bar as the
// Overview / Pricing / Docs pages, with the live wallpaper behind a centered content column.
export function AppShell({ active, children, hero }: AppShellProps) {
  return (
    <div className="relative flex min-h-screen flex-col bg-surface font-ui text-body-md text-on-surface">
      <ShaderBackground className="fixed inset-0 z-0 opacity-20" />
      <SiteHeader active={active === 'profile' ? undefined : active} profileActive={active === 'profile'} />
      <main className="relative z-10 flex w-full flex-1 flex-col pt-16">
        {hero}
        {hero ? (
          // Padding outside the max-width so the column lines up with the hero's
          <div className="flex w-full flex-1 flex-col px-gutter pb-24 md:px-space-xl">
            <div className="mx-auto flex w-full max-w-6xl flex-1 flex-col">{children}</div>
          </div>
        ) : (
          <div className="mx-auto flex w-full max-w-7xl flex-1 flex-col px-gutter py-space-xl md:px-space-xl">{children}</div>
        )}
      </main>
      <SiteFooter />
    </div>
  );
}
