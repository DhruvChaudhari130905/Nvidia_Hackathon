'use client';

import React, { useEffect, useState, useRef, useCallback } from 'react';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { TopBar } from '@/components/room';
import { Feed } from '@/components/feed';
import { CenterTabs } from '@/components/center';
import { SidePanel } from '@/components/side';
import { Timeline } from '@/components/timeline';
import { ShaderBackground } from '@/components/shell';
import { api } from '@/lib/api';
import { getDemoFiles, isDemoMode, isSampleRoom } from '@/lib/demo';
import { loadRoomFiles, saveRoomFiles } from '@/lib/roomFiles';
import { takeStashedImport } from '@/lib/projectImport';
import { colorForId, getDefaultRole, setLastRoom } from '@/lib/preferences';
import { starterProjectFiles } from '@/lib/starterProject';
import { getSocket, type SocketStatus } from '@/lib/socket';
import { createEmptyState } from '@/lib/reducer';
import { notifyForEvent } from '@/lib/roomNotifications';
import { notify } from '@/lib/notifications';
import { resolveUser } from '@/lib/users';
import { NotificationToasts } from '@/components/room/Notifications';
import { getUser, loginHref } from '@/lib/supabase';
import type { RoomState, Room, User, PlanItem, Membership } from '@/types';

export default function RoomPage() {
  const params = useParams();
  const router = useRouter();
  const roomId = params.roomId as string;

  const [room, setRoom] = useState<Room | null>(null);
  const [state, setState] = useState<RoomState | null>(null);
  const [currentUser, setCurrentUser] = useState<User | null>(null);
  const [currentUserMembership, setCurrentUserMembership] = useState<Membership | null>(null);
  const [activeTab, setActiveTab] = useState<'preview' | 'code'>('preview');
  const [activeFile, setActiveFile] = useState<string | null>(null);
  // Which room the files in state belong to; saving waits until they've loaded
  const filesRoom = useRef<string | null>(null);
  const [files, setFiles] = useState<Map<string, { content: string }>>(new Map());
  const [fileVersions, setFileVersions] = useState<Map<string, number>>(new Map());
  const [lockedFiles, setLockedFiles] = useState<Set<string>>(new Set());
  const [lockingUser, setLockingUser] = useState<Map<string, string>>(new Map());
  const [isRewound, setIsRewound] = useState(false);
  const [currentCheckpoint, setCurrentCheckpoint] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  // Set when the room loaded but the user can't open it
  const [accessError, setAccessError] = useState<string | null>(null);
  const [socketStatus, setSocketStatus] = useState<SocketStatus>('connecting');

  const socketRef = useRef<ReturnType<typeof getSocket> | null>(null);

  // Initialize room data
  useEffect(() => {
    // initRoom is async: anything it subscribes to is collected here so the cleanup can undo it
    let cancelled = false;
    const unsubscribers: (() => void)[] = [];
    setLoading(true);
    setAccessError(null);
    setState(null);

    const initRoom = async () => {
      // Nothing from the previous room carries over
      filesRoom.current = null;
      setFiles(new Map());
      setFileVersions(new Map());
      setActiveFile(null);
      try {
        const user = await getUser();
        if (cancelled) return;
        if (!user) {
          router.replace(loginHref());
          return;
        }

        const userData: User = {
          id: user.id,
          email: user.email || '',
          name: user.user_metadata.full_name || user.email?.split('@')[0] || 'User',
          avatar_url: user.user_metadata.avatar_url,
          initials: (user.user_metadata.full_name || user.email || 'U').slice(0, 2).toUpperCase(),
          color: colorForId(user.id),
        };
        setCurrentUser(userData);

        // Fetch room data
        const roomData = await api.getRoom(roomId);
        if (cancelled) return;
        setRoom(roomData);
        setLastRoom(roomData);

        // Not a member yet: a room shared with "anyone with the link" lets them in with the link's permission
        let membership = roomData.members.find(m => m.user_id === user.id);
        if (!membership && roomData.link_access === 'anyone') {
          membership = { user_id: user.id, room_id: roomId, permission: roomData.link_permission === 'owner' ? 'editor' : roomData.link_permission, domain_role: getDefaultRole(), user: userData };
        }
        if (!membership) {
          setAccessError('You don’t have access to this room. Ask the owner to invite you or share the link with “Anyone with the link”.');
          setLoading(false);
          return;
        }
        setCurrentUserMembership(membership);

        // Connect to WebSocket. Subscribing first means the history replayed on connect reaches us.
        const socket = getSocket(roomId);
        socketRef.current = socket;
        unsubscribers.push(socket.onStatus(setSocketStatus));

        // Subscribe to state updates
        unsubscribers.push(socket.onState((newState) => {
          setState(newState);
          // files may arrive as a Map or as a plain object after JSON transport
          const entries: [string, { hash: string; version: number }][] =
            newState.files instanceof Map ? Array.from(newState.files.entries()) : Object.entries(newState.files ?? {});
          setFiles(prev => {
            const next = new Map(prev);
            for (const [path] of entries) {
              if (!next.has(path)) next.set(path, { content: '' });
            }
            return next;
          });
          if (entries.length) {
            setFileVersions(prev => {
              const next = new Map(prev);
              entries.forEach(([path, v]) => next.set(path, v.version));
              return next;
            });
          }
        }));

        try {
          await socket.connect();
        } catch (error) {
          // The socket keeps retrying in the background; the banner below shows that we're offline
          console.error('Room socket failed to connect:', error);
        }
        if (cancelled) return;
        // No events yet (new room, or offline): show an empty room rather than a spinner
        setState(prev => prev ?? createEmptyState(roomId));

        // Load initial files (starter template)
        await loadInitialFiles();
        if (cancelled) return;

        setLoading(false);
      } catch (error) {
        if (cancelled) return;
        console.error('Failed to load room:', error);
        router.push('/dashboard');
      }
    };

    void initRoom();

    return () => {
      cancelled = true;
      unsubscribers.forEach(unsub => unsub());
      socketRef.current?.disconnect();
    };
    // loadInitialFiles only reads roomId, which is already a dependency
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [roomId, router]);

  // A room opens with the files it had last time in this browser. New rooms start empty (the Explorer offers
  // import, the starter template or a new file); sample demo rooms start from the starter plus their own files.
  // TODO: load from the backend files API once it exists.
  const loadInitialFiles = async () => {
    let initial = await loadRoomFiles(roomId);
    if (!initial) {
      initial = new Map();
      if (isDemoMode() && isSampleRoom(roomId)) {
        initial = starterProjectFiles();
        Object.entries(getDemoFiles(roomId)).forEach(([path, content]) => initial!.set(path, { content }));
      }
    }

    // A project picked on the dashboard ("Import project") replaces the empty room's files
    const imported = takeStashedImport(roomId);
    if (imported) initial = new Map(imported.files.map(f => [f.path, { content: f.content }]));

    setFiles(initial);
    setFileVersions(new Map(Array.from(initial.keys(), path => [path, 1])));
    setActiveFile(['README.md', 'src/App.tsx', 'package.json', 'index.html'].find(p => initial!.has(p)) ?? null);
    filesRoom.current = roomId;
    if (imported) void saveRoomFiles(roomId, initial);
  };

  // Keep this room's files in the browser so they're still here next time. Saves are batched, but a
  // pending save is flushed (never dropped) when leaving the room or hiding/closing the tab.
  const pendingSave = useRef<(() => void) | null>(null);
  useEffect(() => {
    if (filesRoom.current !== roomId) return;
    const snapshot = files;
    const flush = () => {
      clearTimeout(t);
      if (pendingSave.current === flush) pendingSave.current = null;
      void saveRoomFiles(roomId, snapshot);
    };
    const t = setTimeout(flush, 400);
    pendingSave.current = flush;
    return () => clearTimeout(t);
  }, [files, roomId]);
  useEffect(() => {
    const flushNow = () => pendingSave.current?.();
    const onHide = () => { if (document.visibilityState === 'hidden') flushNow(); };
    window.addEventListener('pagehide', flushNow);
    document.addEventListener('visibilitychange', onHide);
    return () => {
      flushNow(); // leaving the room
      window.removeEventListener('pagehide', flushNow);
      document.removeEventListener('visibilitychange', onHide);
    };
  }, [roomId]);

  // Message will appear via WebSocket; a failure is thrown so the composer can put the text back
  const handleSendMessage = useCallback(async (text: string) => {
    if (!roomId || !currentUser) return;
    await api.sendMessage(roomId, text);
  }, [roomId, currentUser]);

  // File changes are kept locally (and in IndexedDB) first; server sync failures are reported once, not per file
  const syncErrorShown = useRef(false);
  const reportSyncError = useCallback((action: string, error: unknown) => {
    console.error(`Failed to ${action}:`, error);
    if (syncErrorShown.current) return;
    syncErrorShown.current = true;
    notify({
      category: 'terminal',
      tone: 'err',
      title: 'Files aren’t syncing to the room server',
      body: 'Your changes are saved in this browser. Teammates won’t see them until the connection works again.',
    });
  }, []);
  const syncOk = useCallback(() => { syncErrorShown.current = false; }, []);

  // Other actions (votes, answers, plan) tell the user when they fail
  const reportActionError = useCallback((title: string, error: unknown) => {
    console.error(`${title}:`, error);
    notify({ category: 'decisions', tone: 'err', title, body: error instanceof Error ? error.message : undefined });
  }, []);

  // Latest files for callbacks that need to read them (rename/delete/upload)
  const filesRef = useRef(files);
  filesRef.current = files;

  const handleFileSelect = useCallback((path: string | null) => {
    setActiveFile(path);
  }, []);

  // Put files into local state (content + version) immediately; the server write follows
  const writeLocal = useCallback((entries: { path: string; content: string; version: number }[]) => {
    setFiles(prev => {
      const next = new Map(prev);
      entries.forEach(e => next.set(e.path, { content: e.content }));
      return next;
    });
    setFileVersions(prev => {
      const next = new Map(prev);
      entries.forEach(e => next.set(e.path, e.version));
      return next;
    });
  }, []);

  const removeLocal = useCallback((paths: string[]) => {
    setFiles(prev => {
      const next = new Map(prev);
      paths.forEach(p => next.delete(p));
      return next;
    });
    setFileVersions(prev => {
      const next = new Map(prev);
      paths.forEach(p => next.delete(p));
      return next;
    });
  }, []);

  // Saved locally first, like creating a file, so edits work offline too
  const handleFileSave = useCallback(async (path: string, content: string, baseVersion: number) => {
    if (!roomId) return;
    writeLocal([{ path, content, version: baseVersion + 1 }]);
    try {
      const res = await api.saveFile(roomId, path, content, baseVersion);
      syncOk();
      // The server's version wins over our guess
      if (typeof res?.version === 'number' && res.version !== baseVersion + 1) {
        setFileVersions(prev => new Map(prev).set(path, res.version));
      }
    } catch (error) {
      reportSyncError('save file', error);
    }
  }, [roomId, writeLocal, reportSyncError, syncOk]);

  const handleCreateFile = useCallback((path: string, content = starterContent(path), open = true) => {
    writeLocal([{ path, content, version: 1 }]);
    if (open) setActiveFile(path);
    api.saveFile(roomId, path, content, 0).then(syncOk, error => reportSyncError('create file', error));
  }, [roomId, writeLocal, reportSyncError, syncOk]);

  const handleUploadFiles = useCallback((uploaded: { path: string; content: string }[]) => {
    if (!uploaded.length) return;
    writeLocal(uploaded.map(f => ({ ...f, version: 1 })));
    setActiveFile(uploaded[uploaded.length - 1].path);
    uploaded.forEach(f => api.saveFile(roomId, f.path, f.content, 0).then(syncOk, error => reportSyncError('upload file', error)));
  }, [roomId, writeLocal, reportSyncError, syncOk]);

  const handleDeleteFile = useCallback((path: string, isDirectory: boolean) => {
    const targets = isDirectory
      ? Array.from(filesRef.current.keys()).filter(p => p.startsWith(path + '/'))
      : [path];
    removeLocal(targets);
    targets.forEach(p => api.deleteFile(roomId, p).then(syncOk, error => reportSyncError('delete file', error)));
  }, [roomId, removeLocal, reportSyncError, syncOk]);

  const handleRenameFile = useCallback((from: string, to: string, isDirectory: boolean) => {
    const moves = (isDirectory
      ? Array.from(filesRef.current.keys()).filter(p => p.startsWith(from + '/'))
      : [from]
    ).map(oldPath => ({ oldPath, newPath: to + oldPath.slice(from.length), content: filesRef.current.get(oldPath)?.content ?? '' }));
    writeLocal(moves.map(m => ({ path: m.newPath, content: m.content, version: 1 })));
    removeLocal(moves.map(m => m.oldPath));
    setActiveFile(current => moves.find(m => m.oldPath === current)?.newPath ?? current);
    moves.forEach(m =>
      api.saveFile(roomId, m.newPath, m.content, 0)
        .then(() => api.deleteFile(roomId, m.oldPath))
        .then(syncOk, error => reportSyncError('rename file', error)),
    );
  }, [roomId, writeLocal, removeLocal, reportSyncError, syncOk]);

  const handleVote = useCallback(async (conflictId: string, option: string) => {
    if (!roomId) return;
    try {
      await api.voteConflict(roomId, conflictId, option);
    } catch (error) {
      reportActionError('Your vote wasn’t recorded', error);
    }
  }, [roomId, reportActionError]);

  const handleOverride = useCallback(async (conflictId: string, option: string) => {
    if (!roomId) return;
    try {
      await api.overrideConflict(roomId, conflictId, option);
    } catch (error) {
      reportActionError('Override failed', error);
    }
  }, [roomId, reportActionError]);

  const handleAnswer = useCallback(async (questionId: string, answer: string) => {
    if (!roomId) return;
    try {
      await api.answerQuestion(roomId, questionId, answer);
    } catch (error) {
      reportActionError('Your answer wasn’t sent', error);
    }
  }, [roomId, reportActionError]);

  // These rethrow so the plan editor keeps unsaved edits when the request fails
  const handlePlanUpdate = useCallback(async (items: PlanItem[]) => {
    if (!roomId) return;
    try {
      await api.updatePlan(roomId, items);
    } catch (error) {
      reportActionError('Plan wasn’t saved', error);
      throw error;
    }
  }, [roomId, reportActionError]);

  const handlePlanApprove = useCallback(async () => {
    if (!roomId) return;
    try {
      await api.approvePlan(roomId);
    } catch (error) {
      reportActionError('Plan wasn’t approved', error);
      throw error;
    }
  }, [roomId, reportActionError]);

  const handleRewind = useCallback(async (checkpointId: string) => {
    if (!roomId) return;
    try {
      await api.rewind(roomId, checkpointId);
      setIsRewound(true);
      setCurrentCheckpoint(checkpointId);
    } catch (error) {
      reportActionError('Rewind failed', error);
    }
  }, [roomId, reportActionError]);

  // Live events (not the history replayed on connect) become notifications
  const stateRef = useRef(state);
  stateRef.current = state;
  useEffect(() => {
    const socket = socketRef.current;
    if (!socket || !room || !currentUser) return;
    const unsubscribe = socket.onEvent(event => {
      notifyForEvent(event, {
        roomTitle: room.title,
        currentUser,
        nameOf: id => resolveUser(id, room.members).name,
        planItem: id => stateRef.current?.plan.find(p => p.id === id),
      });
    });
    return () => { unsubscribe(); };
  }, [room, currentUser]);

  // Who is editing which file (the coder locks files while it writes them)
  useEffect(() => {
    const socket = socketRef.current;
    if (!socket || !room) return;
    return socket.onEvent(event => {
      if (event.type !== 'file.locked' && event.type !== 'file.unlocked') return;
      const { path, user_id } = event.payload as { path: string; user_id?: string };
      const locked = event.type === 'file.locked';
      setLockedFiles(prev => {
        const next = new Set(prev);
        if (locked) next.add(path);
        else next.delete(path);
        return next;
      });
      setLockingUser(prev => {
        const next = new Map(prev);
        if (locked) next.set(path, resolveUser(user_id ?? 'agent', room.members).name);
        else next.delete(path);
        return next;
      });
    });
  }, [room]);

  const handleReturnToLatest = useCallback(() => {
    setIsRewound(false);
    setCurrentCheckpoint(null);
  }, []);

  if (accessError) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center gap-4 bg-[var(--bg)] p-6 text-center">
        <p className="max-w-md text-[var(--ink)]">{accessError}</p>
        <Link href="/dashboard" className="btn primary">Back to rooms</Link>
      </div>
    );
  }

  if (loading || !room || !state || !currentUser || !currentUserMembership) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[var(--bg)]">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[var(--coord)]" />
      </div>
    );
  }

  const openConflicts = state.conflicts.filter(c => c.status === 'open' || c.status === 'voting');

  const presenceData = state.presence.map(p => ({
    user: resolveUser(p.user_id, room.members, p.user),
    active: p.active,
    typing: !!p.typing,
  }));

  return (
    <>
      <ShaderBackground className="shader-bg" />
      <div className="app h-screen">
        <TopBar
          room={room}
          currentUserMembership={currentUserMembership}
          budget={state.budget}
          presence={presenceData}
        />

        <main className="main">
          {/* Left: Agent Feed */}
          <Feed
            messages={state.messages}
            members={room.members}
            onSendMessage={handleSendMessage}
            activeConflict={openConflicts[0] ? { id: openConflicts[0].id, taskId: openConflicts[0].task_id, options: openConflicts[0].options } : undefined}
          />

          {/* Center: Preview / Code */}
          <CenterTabs
            key={roomId}
            roomId={roomId}
            roomTitle={room.title}
            roomDescription={room.description}
            plan={state.plan}
            checkpointCount={state.checkpoints.length}
            activeTab={activeTab}
            onTabChange={setActiveTab}
            files={files}
            activeFile={activeFile}
            onFileSelect={handleFileSelect}
            onFileEdit={handleFileSave}
            onCreateFile={handleCreateFile}
            onDeleteFile={handleDeleteFile}
            onRenameFile={handleRenameFile}
            onUploadFiles={handleUploadFiles}
            fileVersions={fileVersions}
            lockedFiles={lockedFiles}
            lockingUser={lockingUser}
          />

          {/* Right: Cards + Plan */}
          <SidePanel
            state={state}
            currentUser={currentUser}
            members={room.members}
            currentUserRole={currentUserMembership.permission}
            currentUserDomainRole={currentUserMembership.domain_role}
            onVote={handleVote}
            onOverride={handleOverride}
            onAnswer={handleAnswer}
            onPlanUpdate={handlePlanUpdate}
            onPlanApprove={handlePlanApprove}
          />
        </main>
        <NotificationToasts />

        {(socketStatus === 'reconnecting' || socketStatus === 'offline') && (
          <div role="status" className="fixed bottom-16 left-1/2 z-50 -translate-x-1/2 flex items-center gap-3 rounded-lg border border-[var(--line)] bg-[var(--panel)] px-4 py-2 text-sm shadow-lg">
            {socketStatus === 'reconnecting'
              ? 'Connection lost. Reconnecting…'
              : 'You’re offline from the room. Live updates are paused.'}
            {socketStatus === 'offline' && (
              <button className="btn primary" type="button" onClick={() => socketRef.current?.reconnect()}>
                Reconnect
              </button>
            )}
          </div>
        )}

        <Timeline
          checkpoints={state.checkpoints}
          currentCheckpoint={currentCheckpoint}
          onSelectCheckpoint={handleRewind}
          onReturnToLatest={handleReturnToLatest}
          isRewound={isRewound}
        />
      </div>
    </>
  );
}

// Sensible first contents for a new file, by extension
function starterContent(path: string): string {
  const file = path.split('/').pop() || '';
  const base = file.replace(/\.[^.]+$/, '');
  const component = base.replace(/(^|[-_ ])(\w)/g, (_, __, c: string) => c.toUpperCase()).replace(/[^A-Za-z0-9]/g, '') || 'Component';
  if (/\.(tsx|jsx)$/.test(file)) return `export function ${component}() {\n  return <div>${component}</div>;\n}\n`;
  if (/\.(ts|js)$/.test(file)) return `export {};\n`;
  if (file.endsWith('.json')) return '{\n}\n';
  if (file.endsWith('.css')) return `/* ${file} */\n`;
  if (file.endsWith('.md')) return `# ${base}\n`;
  if (file.endsWith('.html')) return '<!DOCTYPE html>\n<html lang="en">\n  <head>\n    <meta charset="UTF-8" />\n  </head>\n  <body></body>\n</html>\n';
  return '';
}
