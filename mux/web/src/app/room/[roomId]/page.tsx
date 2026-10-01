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
import { api } from '@/lib/api';
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
import type { RoomState, Room, User, Message, PlanItem, Conflict, Question, Checkpoint, Membership } from '@/types';
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
  const [lockedFiles, setLockedFiles] = useState<Set<string>>(new Set());
  const [lockingUser, setLockingUser] = useState<Map<string, string>>(new Map());
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

        // Fetch room data
        const roomData = await api.getRoom(roomId);
        setRoom(roomData);
        setLastRoom(roomData);

        const membership = roomData.members.find(m => m.user_id === user.id);
        if (membership) {
          setCurrentUserMembership(membership);
        }

        // Connect to WebSocket
        const socket = getSocket(roomId);
        socketRef.current = socket;

        await socket.connect();

        // Subscribe to state updates
        const unsubState = socket.onState((newState) => {
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
          setFileVersions(new Map(entries.map(([path, v]) => [path, v.version])));
        });

        const unsubPresence = socket.onPresence((presence) => {
          if (state) {
            setState(prev => prev ? { ...prev, presence } : null);
          }
        });

        // Load initial files (starter template)
        await loadInitialFiles();

        setLoading(false);

        return () => {
          unsubState();
          unsubPresence();
        };
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

  const handleSendMessage = useCallback(async (text: string) => {
    if (!roomId || !currentUser) return;
    try {
      await api.sendMessage(roomId, text);
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

  const handleFileSave = useCallback(async (path: string, content: string, baseVersion: number) => {
    if (!roomId) return;
    try {
      await api.saveFile(roomId, path, content, baseVersion);
      writeLocal([{ path, content, version: baseVersion + 1 }]);
    } catch (error) {
      console.error('Failed to save file:', error);
      alert('Failed to save file. Version may have changed.');
      throw error; // keep the unsaved draft in the editor
    }
  }, [roomId, writeLocal]);

  const handleCreateFile = useCallback((path: string, content = starterContent(path), open = true) => {
    writeLocal([{ path, content, version: 1 }]);
    if (open) setActiveFile(path);
    api.saveFile(roomId, path, content, 0).catch(error => console.error('Failed to create file:', error));
  }, [roomId, writeLocal]);

  const handleUploadFiles = useCallback((uploaded: { path: string; content: string }[]) => {
    if (!uploaded.length) return;
    writeLocal(uploaded.map(f => ({ ...f, version: 1 })));
    setActiveFile(uploaded[uploaded.length - 1].path);
    uploaded.forEach(f => api.saveFile(roomId, f.path, f.content, 0).catch(error => console.error('Failed to upload file:', error)));
  }, [roomId, writeLocal]);

  const handleDeleteFile = useCallback((path: string, isDirectory: boolean) => {
    const targets = isDirectory
      ? Array.from(filesRef.current.keys()).filter(p => p.startsWith(path + '/'))
      : [path];
    removeLocal(targets);
    targets.forEach(p => api.deleteFile(roomId, p).catch(error => console.error('Failed to delete file:', error)));
  }, [roomId, removeLocal]);

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
        .catch(error => console.error('Failed to rename file:', error)),
    );
  }, [roomId, writeLocal, removeLocal]);

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
        nameOf: id => room.members.find(m => m.user_id === id)?.user?.name ?? (id ? id.charAt(0).toUpperCase() + id.slice(1) : 'Someone'),
        planItem: id => stateRef.current?.plan.find(p => p.id === id),
      });
    });
    return () => { unsubscribe(); };
  }, [room, currentUser]);

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
            activeConflict={openConflicts[0] ? { id: openConflicts[0].id, taskId: openConflicts[0].task_id, options: openConflicts[0].options } : undefined}
            activeQuestion={openQuestions[0] ? { id: openQuestions[0].id, taskId: openQuestions[0].task_id } : undefined}
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
