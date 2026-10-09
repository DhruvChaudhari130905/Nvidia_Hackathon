'use client';

import React, { useEffect } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Share2, Github, ArrowLeft, Trash2, Plug } from 'lucide-react';
import type { User, Room, Membership } from '@/types';
import { BudgetMeter } from './BudgetMeter';
import { Presence } from './Presence';
import { ShareDialog } from './ShareDialog';
import { ToolsDialog } from './ToolsDialog';
import { ExportDialog } from './ExportDialog';
import { DeleteRoomDialog } from './DeleteRoomDialog';
import { NotificationBell } from './Notifications';
import { api } from '@/lib/api';
import { isDemoMode } from '@/lib/demo';

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
  const [showTools, setShowTools] = React.useState(false);
  const [showExport, setShowExport] = React.useState(false);
  const [showDelete, setShowDelete] = React.useState(false);
  const router = useRouter();
  const [checkingGitHub, setCheckingGitHub] = React.useState(false);
  const isOwner = currentUserMembership.permission === 'owner';

  // /room/<id>?export=1 (from the header's Export button, or back from connecting GitHub) opens the
  // export dialog straight away
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get('github') === 'error') alert(params.get('message') ?? 'GitHub connection failed.');
    if (isOwner && params.get('export') && params.get('github') !== 'error') setShowExport(true);
    if (params.has('github')) window.history.replaceState(null, '', window.location.pathname);
  }, [isOwner]);

  // Exporting needs GitHub: without a connection, go to GitHub first and come back to this dialog
  const handleExport = async () => {
    if (isDemoMode()) {
      setShowExport(true);
      return;
    }
    setCheckingGitHub(true);
    try {
      const { connected, username } = await api.githubStatus();
      if (connected && username) {
        setShowExport(true);
        return;
      }
      const { url } = await api.connectGitHub(`${window.location.pathname}?export=1`);
      window.location.href = url;
    } catch (error) {
      alert(error instanceof Error ? error.message : 'Could not reach GitHub. Is the backend running?');
    } finally {
      setCheckingGitHub(false);
    }
  };

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
        <button className="btn flex items-center gap-1.5" onClick={() => setShowTools(true)} type="button" title="MCP tools for the coder">
          <Plug className="w-4 h-4" />
          <span className="hidden sm:inline">Tools</span>
        </button>
        <button className="btn flex items-center gap-1.5" onClick={() => setShowShare(true)} type="button">
          <Share2 className="w-4 h-4" />
          <span className="hidden sm:inline">Share</span>
        </button>
        {isOwner && (
          <button className="btn primary flex items-center gap-1.5" onClick={handleExport} disabled={checkingGitHub} type="button">
            <Github className="w-4 h-4" />
            {checkingGitHub ? 'Checking GitHub…' : 'Export to GitHub'}
          </button>
        )}
        {isOwner && (
          <button
            className="btn p-2 text-[var(--muted)] hover:border-[var(--conflict)] hover:text-[var(--conflict)]"
            onClick={() => setShowDelete(true)}
            type="button"
            aria-label="Delete room"
            title="Delete room"
          >
            <Trash2 className="h-4 w-4" />
          </button>
        )}
      </div>
      <ShareDialog isOpen={showShare} onClose={() => setShowShare(false)} room={room} isOwner={isOwner} />
      <ToolsDialog isOpen={showTools} onClose={() => setShowTools(false)} roomId={room.id} isOwner={isOwner} />
      <ExportDialog isOpen={showExport} onClose={() => setShowExport(false)} room={room} />
      <DeleteRoomDialog
        room={showDelete ? { id: room.id, title: room.title } : null}
        onClose={() => setShowDelete(false)}
        onDeleted={() => router.push('/dashboard')}
      />
    </header>
  );
}