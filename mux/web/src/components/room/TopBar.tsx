'use client';

import React, { useEffect } from 'react';
import Link from 'next/link';
import { Share2, Github, ArrowLeft } from 'lucide-react';
import type { User, Room, Membership } from '@/types';
import { BudgetMeter } from './BudgetMeter';
import { Presence } from './Presence';
import { ShareDialog } from './ShareDialog';
import { ExportDialog } from './ExportDialog';
import { NotificationBell } from './Notifications';

interface TopBarProps {
  room: Room;
  currentUser: User;
  currentUserMembership: Membership;
  budget: { tokens_used: number; tokens_cap: number; runs_used: number; runs_cap: number };
  presence: Array<{ user: User; active: boolean; typing: boolean }>;
}

export function TopBar({
  room,
  currentUser,
  currentUserMembership,
  budget,
  presence,
}: TopBarProps) {
  const [showShare, setShowShare] = React.useState(false);
  const [showExport, setShowExport] = React.useState(false);
  const isOwner = currentUserMembership.permission === 'owner';

  // /room/<id>?export=1 (from the header's Export button) opens the export dialog straight away
  useEffect(() => {
    if (isOwner && new URLSearchParams(window.location.search).get('export')) setShowExport(true);
  }, [isOwner]);

  return (
    <header className="top">
      <Link href="/dashboard" className="brand group flex items-center gap-1.5" title="Back to rooms">
        <ArrowLeft className="h-4 w-4 text-[var(--muted)] transition-transform group-hover:-translate-x-0.5" />
        MUX
      </Link>
      <div className="room">
        <span className="name">{room.title}</span>
        <span className="sub mono">
          room · {room.members.length} members · 8 steering seats
        </span>
      </div>
      <div className="spacer" />
      <div className="presence" aria-label="People in the room">
        <Presence users={presence} typingUser={presence.find(p => p.typing)?.user.id} />
      </div>
      <BudgetMeter
        tokensUsed={budget.tokens_used}
        tokensCap={budget.tokens_cap}
        runsUsed={budget.runs_used}
        runsCap={budget.runs_cap}
      />
      <div className="flex items-center gap-2">
        <NotificationBell />
        <button className="btn flex items-center gap-1.5" onClick={() => setShowShare(true)} type="button">
          <Share2 className="w-4 h-4" />
          <span className="hidden sm:inline">Share</span>
        </button>
        {isOwner && (
          <button className="btn primary flex items-center gap-1.5" onClick={() => setShowExport(true)} type="button">
            <Github className="w-4 h-4" />
            Export to GitHub
          </button>
        )}
      </div>
      <ShareDialog isOpen={showShare} onClose={() => setShowShare(false)} room={room} />
      <ExportDialog isOpen={showExport} onClose={() => setShowExport(false)} room={room} />
    </header>
  );
}