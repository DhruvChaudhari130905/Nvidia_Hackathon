'use client';

import React, { useEffect, useState, useRef, useCallback } from 'react';
import { useParams, useRouter } from 'next/navigation';
import {
  TopBar,
  BudgetMeter,
  Presence,
} from '@/components/room';
import { Feed } from '@/components/feed';
import { CenterTabs } from '@/components/center';
import { SidePanel } from '@/components/side';
import { Timeline } from '@/components/timeline';
import { ShaderBackground } from '@/components/shell';
import { api, ApiError } from '@/lib/api';
import { getDemoFiles, isDemoMode, isSampleRoom } from '@/lib/demo';
import { loadRoomFiles, saveRoomFiles } from '@/lib/roomFiles';
import { takeStashedImport } from '@/lib/projectImport';
import { setLastRoom } from '@/lib/preferences';
import { starterProjectFiles } from '@/lib/starterProject';
import { getSocket } from '@/lib/socket';
import { notifyForEvent } from '@/lib/roomNotifications';
import { NotificationToasts } from '@/components/room/Notifications';
import { reduce } from '@/lib/reducer';
import { supabase, getUser, loginHref } from '@/lib/supabase';
import type { RoomState, Room, User, Message, MessageTo, PlanItem, Conflict, Question, Checkpoint, Membership } from '@/types';
import { format } from 'date-fns';

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
  const [isRewound, setIsRewound] = useState(false);
  const [currentCheckpoint, setCurrentCheckpoint] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const socketRef = useRef<ReturnType<typeof getSocket> | null>(null);

  // Initialize room data
  useEffect(() => {
    const initRoom = async () => {
      // Nothing from the previous room carries over
      filesRoom.current = null;
      setFiles(new Map());
      setFileVersions(new Map());
      setActiveFile(null);
      try {
        const user = await getUser();
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
          color: `hsl(${Math.random() * 360}, 70%, 60%)`,
        };
        setCurrentUser(userData);

        // Fetch room data. Someone who opened the room's link becomes a member first.
        let roomData = await api.getRoom(roomId, userData);
        let membership = roomData.members.find(m => m.user_id === user.id);
        if (!membership && !isDemoMode()) {
          await api.joinRoom(roomId).catch(() => undefined); // a private room stays read-only (viewer)
          roomData = await api.getRoom(roomId, userData);
          membership = roomData.members.find(m => m.user_id === user.id);
        }
        setRoom(roomData);
        setLastRoom(roomData);
        setCurrentUserMembership(membership ?? {
          user_id: user.id, room_id: roomId, permission: roomData.my_permission ?? 'viewer', domain_role: 'eng', user: userData,
        });

        // Connect to WebSocket; it replays the room's events, then streams live ones
        const socket = getSocket(roomId, roomData, userData);
        socketRef.current = socket;
        socket.onState(setState);
        await socket.connect();

        // Load the room's files
        await loadInitialFiles();

        setLoading(false);
      } catch (error) {
        console.error('Failed to load room:', error);
        router.push('/dashboard');
      }
    };

    initRoom();

    return () => {
      if (socketRef.current) {
        socketRef.current.disconnect();
      }
    };
  }, [roomId, router]);

  // The room's live files from the server. Binary files (415) are left out of the editor.
  const loadServerFiles = useCallback(async () => {
    const entries = await api.listFiles(roomId);
    const read = await Promise.all(entries.map(e => api.readFile(roomId, e.path).catch(() => null)));
    const loaded = read.filter((f): f is NonNullable<typeof f> => f !== null);
    return {
      files: new Map(loaded.map(f => [f.path, { content: f.content }])),
      versions: new Map(loaded.map(f => [f.path, f.version])),
    };
  }, [roomId]);

  // Demo rooms open with the files they had last time in this browser; sample rooms start from the starter plus
  // their own files. Real rooms load the server's files (every room starts from the template, checkpoint C0).
  const loadInitialFiles = async () => {
    if (!isDemoMode()) {
      const { files: initial, versions } = await loadServerFiles();
      setFiles(initial);
      setFileVersions(versions);
      setActiveFile(['README.md', 'src/App.tsx', 'package.json', 'index.html'].find(p => initial.has(p)) ?? null);
      filesRoom.current = roomId;
      return;
    }
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
    if (filesRoom.current !== roomId || !isDemoMode()) return; // real rooms keep their files on the server
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

  const handleSendMessage = useCallback(async (text: string, to: MessageTo) => {
    if (!roomId || !currentUser) return;
    try {
      await api.sendMessage(roomId, text, to);
      // Message will appear via WebSocket
    } catch (error) {
      console.error('Failed to send message:', error);
    }
  }, [roomId, currentUser]);

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

  // Every write holds the file's soft lock for the save, so the coder and other people wait for it (§9).
  // base null creates the file, content null deletes it. Returns the new version (null once deleted).
  const versionsRef = useRef(fileVersions);
  versionsRef.current = fileVersions;
  const writeFile = useCallback(async (path: string, content: string | null, base: number | null) => {
    await api.lockFile(roomId, path);
    try {
      return (await api.saveFile(roomId, path, content, base)).version;
    } finally {
      await api.unlockFile(roomId, path).catch(() => undefined);
    }
  }, [roomId]);

  const reportWriteError = (what: string, error: unknown) => {
    console.error(`Failed to ${what}:`, error);
    if (error instanceof ApiError && error.status === 409) alert(`Could not ${what}: ${error.message}. Reload the file and try again.`);
  };

  const handleFileSave = useCallback(async (path: string, content: string, baseVersion: number) => {
    if (!roomId) return;
    try {
      const version = await writeFile(path, content, baseVersion);
      writeLocal([{ path, content, version: version ?? baseVersion + 1 }]);
    } catch (error) {
      reportWriteError('save the file', error);
      throw error; // keep the unsaved draft in the editor
    }
  }, [roomId, writeLocal, writeFile]);

  const handleCreateFile = useCallback((path: string, content = starterContent(path), open = true) => {
    writeLocal([{ path, content, version: 1 }]);
    if (open) setActiveFile(path);
    writeFile(path, content, null)
      .then(version => version && writeLocal([{ path, content, version }]))
      .catch(error => reportWriteError('create the file', error));
  }, [writeLocal, writeFile]);

  const handleUploadFiles = useCallback((uploaded: { path: string; content: string }[]) => {
    if (!uploaded.length) return;
    writeLocal(uploaded.map(f => ({ ...f, version: 1 })));
    setActiveFile(uploaded[uploaded.length - 1].path);
    uploaded.forEach(f => {
      const base = versionsRef.current.get(f.path) ?? null; // an upload over an existing file replaces it
      writeFile(f.path, f.content, base)
        .then(version => version && writeLocal([{ ...f, version }]))
        .catch(error => reportWriteError('upload the file', error));
    });
  }, [writeLocal, writeFile]);

  const deleteOnServer = useCallback((path: string) => {
    if (isDemoMode()) return Promise.resolve(null);
    return writeFile(path, null, versionsRef.current.get(path) ?? null);
  }, [writeFile]);

  const handleDeleteFile = useCallback((path: string, isDirectory: boolean) => {
    const targets = isDirectory
      ? Array.from(filesRef.current.keys()).filter(p => p.startsWith(path + '/'))
      : [path];
    targets.forEach(p => deleteOnServer(p).catch(error => reportWriteError('delete the file', error)));
    removeLocal(targets);
  }, [removeLocal, deleteOnServer]);

  const handleRenameFile = useCallback((from: string, to: string, isDirectory: boolean) => {
    const moves = (isDirectory
      ? Array.from(filesRef.current.keys()).filter(p => p.startsWith(from + '/'))
      : [from]
    ).map(oldPath => ({ oldPath, newPath: to + oldPath.slice(from.length), content: filesRef.current.get(oldPath)?.content ?? '' }));
    writeLocal(moves.map(m => ({ path: m.newPath, content: m.content, version: 1 })));
    removeLocal(moves.map(m => m.oldPath));
    setActiveFile(current => moves.find(m => m.oldPath === current)?.newPath ?? current);
    moves.forEach(m =>
      writeFile(m.newPath, m.content, null)
        .then(() => deleteOnServer(m.oldPath))
        .catch(error => reportWriteError('rename the file', error)),
    );
  }, [writeLocal, removeLocal, writeFile, deleteOnServer]);

  const handleVote = useCallback(async (conflictId: string, option: string) => {
    if (!roomId) return;
    try {
      await api.voteConflict(roomId, conflictId, option);
    } catch (error) {
      console.error('Failed to vote:', error);
    }
  }, [roomId]);

  const handleOverride = useCallback(async (conflictId: string, option: string) => {
    if (!roomId) return;
    try {
      await api.overrideConflict(roomId, conflictId, option);
    } catch (error) {
      console.error('Failed to override:', error);
    }
  }, [roomId]);

  const handleAnswer = useCallback(async (questionId: string, answer: string) => {
    if (!roomId) return;
    try {
      await api.answerQuestion(roomId, questionId, answer);
    } catch (error) {
      console.error('Failed to answer:', error);
    }
  }, [roomId]);

  const handlePlanUpdate = useCallback(async (items: PlanItem[]) => {
    if (!roomId) return;
    try {
      await api.updatePlan(roomId, items);
    } catch (error) {
      console.error('Failed to update plan:', error);
    }
  }, [roomId]);

  const handlePlanApprove = useCallback(async () => {
    if (!roomId) return;
    try {
      await api.approvePlan(roomId);
    } catch (error) {
      console.error('Failed to approve plan:', error);
    }
  }, [roomId]);

  const handleRewind = useCallback(async (checkpointId: string) => {
    if (!roomId) return;
    try {
      await api.rewind(roomId, checkpointId);
      setIsRewound(true);
      setCurrentCheckpoint(checkpointId);
    } catch (error) {
      console.error('Failed to rewind:', error);
    }
  }, [roomId]);

  // Live events (not the history replayed on connect) become notifications, and keep the editor's files current:
  // a file someone else (or the coder) changed is read again, and a rewind reloads them all
  const stateRef = useRef(state);
  stateRef.current = state;
  useEffect(() => {
    const socket = socketRef.current;
    if (!socket || !room || !currentUser) return;
    const unsubscribe = socket.onEvent(event => {
      notifyForEvent(event, {
        roomTitle: room.title,
        currentUser,
        nameOf: id => stateRef.current?.people[id]?.name ?? 'Someone',
        planItem: id => stateRef.current?.plan.find(p => p.id === id),
      });
      if (isDemoMode()) return;
      if (event.type === 'file.changed') {
        const { path, version, deleted } = event.payload;
        if (deleted) removeLocal([path]);
        else if (versionsRef.current.get(path) !== version) {
          api.readFile(roomId, path).then(f => writeLocal([f])).catch(() => undefined);
        }
      } else if (event.type === 'room.rewound') {
        loadServerFiles().then(({ files: fresh, versions }) => { setFiles(fresh); setFileVersions(versions); }).catch(() => undefined);
      }
    });
    return () => { unsubscribe(); };
  }, [room, currentUser, roomId, writeLocal, removeLocal, loadServerFiles]);

  const handleReturnToLatest = useCallback(() => {
    setIsRewound(false);
    setCurrentCheckpoint(null);
  }, []);

  if (loading || !room || !state || !currentUser || !currentUserMembership) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[var(--bg)]">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[var(--coord)]" />
      </div>
    );
  }

  // Files someone else is editing by hand are read-only here (the server's soft locks)
  const lockedFiles = new Set([...state.locks].filter(([, user]) => user !== currentUser.id).map(([path]) => path));
  const lockingUser = new Map([...state.locks].map(([path, user]) => [path, state.people[user]?.name ?? 'Someone'] as [string, string]));

  const openConflicts = state.conflicts.filter(c => c.status === 'open' || c.status === 'voting');
  const openQuestions = state.questions.filter(q => q.status === 'open');

  const presenceData = state.presence.map(p => ({
    user: p.user,
    active: p.active,
    typing: !!p.typing,
  }));

  const typingUser = state.presence.find(p => p.typing)?.user.id;

  return (
    <>
      <ShaderBackground className="shader-bg" />
      <div className="app h-screen">
        <TopBar
          room={room}
          currentUser={currentUser}
          currentUserMembership={currentUserMembership}
          budget={state.budget}
          presence={presenceData}
        />

        <main className="main">
          {/* Left: Agent Feed */}
          <Feed
            messages={state.messages}
            currentUser={currentUser}
            onSendMessage={handleSendMessage}
            canPostTeam={currentUserMembership.permission !== 'viewer'}
            activeConflict={openConflicts[0] ? { id: openConflicts[0].id, taskId: openConflicts[0].task_id, options: openConflicts[0].options } : undefined}
            activeQuestion={openQuestions[0] ? { id: openQuestions[0].id, taskId: openQuestions[0].task_id ?? '' } : undefined}
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
