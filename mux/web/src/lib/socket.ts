// WebSocket client for real-time events and presence
import type { AppEvent, Presence, RoomState } from '@/types';
import { demoRoomEvents, isDemoMode } from './demo';
import { getAccessToken } from './supabase';

type EventHandler = (event: AppEvent) => void;
type PresenceHandler = (presence: Presence[]) => void;
type StateHandler = (state: RoomState) => void;

export class SocketClient {
  private ws: WebSocket | null = null;
  private apiHost: string;
  private roomId: string;
  private since: number;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 1000;
  private eventHandlers: Set<EventHandler> = new Set();
  private presenceHandlers: Set<PresenceHandler> = new Set();
  private stateHandlers: Set<StateHandler> = new Set();
  private pendingEvents: AppEvent[] = [];
  private currentState: RoomState | null = null;
  private isConnected = false;

  constructor(roomId: string, since: number = 0) {
    this.roomId = roomId;
    this.since = since;
    this.apiHost = process.env.NEXT_PUBLIC_API_URL?.replace(/^http/, 'ws') || 'ws://localhost:8000';
  }

  async connect(): Promise<void> {
    if (isDemoMode()) {
      // Replay a canned room instead of opening a WebSocket
      if (!this.currentState) this.handleMessage(demoRoomEvents(this.roomId));
      this.isConnected = true;
      return;
    }
    const token = await getAccessToken();
    // Resume from the last seq seen, so a reconnect replays only what was missed
    const url = `${this.apiHost}/rooms/${this.roomId}/ws?since=${this.since}`;
    return new Promise((resolve, reject) => {
      try {
        this.ws = new WebSocket(url);

        this.ws.onopen = () => {
          console.log('[WS] Connected');
          // The first message authenticates the socket (docs/06-event-catalog.md)
          this.ws?.send(JSON.stringify({ type: 'auth', payload: { token } }));
          this.isConnected = true;
          this.reconnectAttempts = 0;
          this.flushPendingEvents();
          resolve();
        };

        this.ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            this.handleMessage(data);
          } catch (e) {
            console.error('[WS] Failed to parse message:', e);
          }
        };

        this.ws.onclose = (event) => {
          console.log('[WS] Disconnected:', event.code, event.reason);
          this.isConnected = false;
          this.scheduleReconnect();
        };

        this.ws.onerror = (error) => {
          console.error('[WS] Error:', error);
          if (!this.isConnected) {
            reject(new Error('WebSocket connection failed'));
          }
        };
      } catch (e) {
        reject(e);
      }
    });
  }

  private handleMessage(data: unknown) {
    // Handle initial state dump (array of events)
    if (Array.isArray(data)) {
      for (const event of data) {
        this.applyEvent(event as AppEvent);
      }
      this.notifyState();
      return;
    }

    // Handle single event
    const event = data as AppEvent;
    this.applyEvent(event);
    this.notifyEvent(event);
    this.notifyState();
  }

  private applyEvent(event: AppEvent) {
    this.since = event.seq;

    if (!this.currentState) {
      // Initialize minimal state - will be hydrated by initial dump
      this.currentState = {
        room: { id: this.roomId } as any,
        plan: [],
        messages: [],
        conflicts: [],
        questions: [],
        files: new Map(),
        checkpoints: [],
        budget: { tokens_used: 0, runs_used: 0, tokens_cap: 2000000, runs_cap: 100 },
        presence: [],
        current_user: {} as any,
        current_user_membership: {} as any,
      };
    }

    const state = this.currentState;

    switch (event.type) {
      case 'message.posted':
        state.messages.push(event.payload);
        break;
      case 'message.labeled': {
        const msg = state.messages.find(m => m.id === event.payload.message_id);
        if (msg) {
          msg.label = event.payload.label;
          msg.rationale = event.payload.rationale;
          msg.domain = event.payload.domain as any;
        }
        break;
      }
      case 'plan.item_added':
        state.plan.push(event.payload);
        break;
      case 'plan.item_updated': {
        const item = state.plan.find(p => p.id === event.payload.id);
        if (item) Object.assign(item, event.payload.changes);
        break;
      }
      case 'plan.approved': {
        state.plan.forEach(p => { if (p.status === 'draft') p.status = 'todo'; });
        break;
      }
      case 'conflict.opened':
        state.conflicts.push(event.payload);
        break;
      case 'conflict.vote': {
        const conflict = state.conflicts.find(c => c.id === event.payload.conflict_id);
        if (conflict) {
          conflict.votes.push({
            conflict_id: event.payload.conflict_id,
            user_id: event.payload.user_id,
            option: event.payload.option,
            weight: event.payload.weight,
          });
        }
        break;
      }
      case 'conflict.closed': {
        const conflict = state.conflicts.find(c => c.id === event.payload.conflict_id);
        if (conflict) {
          conflict.status = 'closed';
          conflict.result = event.payload.result;
          conflict.resolved_by = event.payload.resolved_by;
        }
        // Unblock the task
        const task = state.plan.find(p => p.id === conflict?.task_id);
        if (task) {
          task.status = 'todo';
          task.notes = `unblocked · ${event.payload.result}`;
        }
        break;
      }
      case 'question.opened':
        state.questions.push(event.payload);
        break;
      case 'question.answered': {
        const q = state.questions.find(q => q.id === event.payload.question_id);
        if (q) {
          q.status = 'answered';
          q.answer = event.payload.answer;
        }
        const task = state.plan.find(p => p.id === q?.task_id);
        if (task) {
          task.status = 'todo';
          task.notes = `unblocked · ${event.payload.answer.toLowerCase()}`;
        }
        break;
      }
      case 'question.defaulted': {
        const q = state.questions.find(q => q.id === event.payload.question_id);
        if (q) {
          q.status = 'defaulted';
          q.answer = q.default_option;
        }
        break;
      }
      case 'task.started': {
        const task = state.plan.find(p => p.id === event.payload.task_id);
        if (task) task.status = 'doing';
        break;
      }
      case 'task.finished': {
        const task = state.plan.find(p => p.id === event.payload.task_id);
        if (task) task.status = 'done';
        break;
      }
      case 'file.changed': {
        state.files.set(event.payload.path, { hash: event.payload.hash, version: event.payload.version });
        break;
      }
      case 'checkpoint.created':
        state.checkpoints.push(event.payload);
        break;
      case 'room.rewound': {
        // State will be rebuilt from events after rewind
        // For now, just update checkpoints
        state.checkpoints = state.checkpoints.filter(c => c.seq <= event.payload.seq);
        break;
      }
      case 'budget.updated':
        state.budget = event.payload;
        break;
      case 'presence.join':
        state.presence.push(event.payload);
        break;
      case 'presence.leave':
        state.presence = state.presence.filter(p => p.user_id !== event.payload.user_id);
        break;
      case 'presence.typing': {
        const p = state.presence.find(p => p.user_id === event.payload.user_id);
        if (p) p.typing = event.payload.typing;
        break;
      }
      case 'presence.tab': {
        const p = state.presence.find(p => p.user_id === event.payload.user_id);
        if (p) p.tab = event.payload.tab;
        break;
      }
    }
  }

  private flushPendingEvents() {
    // Events that arrived before connection
  }

  private notifyEvent(event: AppEvent) {
    this.eventHandlers.forEach(h => h(event));
  }

  private notifyState() {
    if (this.currentState) {
      // State is mutated in place, so hand out a fresh snapshot or React won't re-render
      const s = this.currentState;
      const snapshot: RoomState = {
        ...s,
        plan: s.plan.map(p => ({ ...p })),
        messages: [...s.messages],
        conflicts: s.conflicts.map(c => ({ ...c, votes: [...c.votes] })),
        questions: s.questions.map(q => ({ ...q })),
        files: new Map(s.files),
        checkpoints: [...s.checkpoints],
        presence: s.presence.map(p => ({ ...p })),
      };
      this.stateHandlers.forEach(h => h(snapshot));
      // Also compute presence for convenience
      this.presenceHandlers.forEach(h => h(this.currentState!.presence));
    }
  }

  private scheduleReconnect() {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error('[WS] Max reconnect attempts reached');
      return;
    }
    const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts);
    this.reconnectAttempts++;
    setTimeout(() => this.connect(), delay);
  }

  // Apply an event produced locally (demo mode) as if the server had sent it
  injectEvent(event: AppEvent) {
    this.handleMessage(event);
  }

  onEvent(handler: EventHandler) {
    this.eventHandlers.add(handler);
    return () => this.eventHandlers.delete(handler);
  }

  onPresence(handler: PresenceHandler) {
    this.presenceHandlers.add(handler);
    return () => this.presenceHandlers.delete(handler);
  }

  onState(handler: StateHandler) {
    this.stateHandlers.add(handler);
    if (this.currentState) handler(this.currentState);
    return () => this.stateHandlers.delete(handler);
  }

  send(event: { type: string; payload: unknown }) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(event));
    }
  }

  sendPresence(tab: Presence['tab']) {
    this.send({ type: 'presence.tab', payload: { tab } });
  }

  sendTyping(typing: boolean) {
    this.send({ type: 'presence.typing', payload: { typing } });
  }

  disconnect() {
    this.ws?.close(1000, 'Client disconnect');
    this.ws = null;
    this.isConnected = false;
  }

  getState(): RoomState | null {
    return this.currentState;
  }

  getSince(): number {
    return this.since;
  }
}

// Singleton for the current room
let currentSocket: SocketClient | null = null;

export function getSocket(roomId: string, since?: number): SocketClient {
  if (currentSocket && currentSocket['roomId'] === roomId) {
    return currentSocket;
  }
  if (currentSocket) {
    currentSocket.disconnect();
  }
  currentSocket = new SocketClient(roomId, since);
  return currentSocket;
}

export function clearSocket() {
  if (currentSocket) {
    currentSocket.disconnect();
    currentSocket = null;
  }
}