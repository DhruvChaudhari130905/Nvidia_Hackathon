// Room WebSocket: /ws/rooms/{id}?token=<Supabase JWT>&since=<seq> (mux/server/mux/api/ws.py).
// The server sends every stored event after `since`, then live ones, one envelope per message; presence and
// text deltas carry the last stored seq. The client sends {type: "tab"}, {type: "typing"} and {type: "ping"}.
import type { AppEvent, Presence, Room, RoomState, User } from '@/types';
import { demoRoomEvents, isDemoMode } from './demo';
import { applyEvent, createEmptyState } from './reducer';
import { getAccessToken } from './supabase';

type EventHandler = (event: AppEvent) => void;
type PresenceHandler = (presence: Presence[]) => void;
type StateHandler = (state: RoomState) => void;

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const MAX_RECONNECTS = 5;

export class SocketClient {
  private ws: WebSocket | null = null;
  private roomId: string;
  private since = 0; // the highest stored seq applied; a reconnect resumes after it
  private liveAfter: number; // events up to here are history: they build the state but raise no notifications
  private reconnectAttempts = 0;
  private closedByUs = false;
  private eventHandlers: Set<EventHandler> = new Set();
  private presenceHandlers: Set<PresenceHandler> = new Set();
  private stateHandlers: Set<StateHandler> = new Set();
  private state: RoomState;

  constructor(roomId: string, room?: Room, currentUser?: User) {
    this.roomId = roomId;
    this.liveAfter = room?.last_seq ?? 0;
    this.state = createEmptyState(room, currentUser);
  }

  async connect(): Promise<void> {
    this.closedByUs = false;
    if (isDemoMode()) {
      // Replay a canned room instead of opening a WebSocket
      if (this.since === 0) for (const event of demoRoomEvents(this.roomId)) this.handle(event, false);
      this.notifyState();
      return;
    }
    const token = await getAccessToken();
    const base = API_BASE.replace(/^http/, 'ws');
    const url = `${base}/ws/rooms/${this.roomId}?since=${this.since}${token ? `&token=${encodeURIComponent(token)}` : ''}`;
    return new Promise((resolve, reject) => {
      const ws = new WebSocket(url);
      this.ws = ws;
      let opened = false;
      ws.onopen = () => {
        opened = true;
        this.reconnectAttempts = 0;
        resolve();
      };
      ws.onmessage = message => {
        try {
          const data = JSON.parse(message.data);
          if (typeof data.seq !== 'number') {
            if (data.type === 'error') console.error('[WS] Server error:', data.detail);
            return; // pong and error replies are not events
          }
          this.handle(data as AppEvent, true);
        } catch (e) {
          console.error('[WS] Failed to handle message:', e);
        }
      };
      ws.onclose = event => {
        if (this.ws === ws) this.ws = null;
        if (!opened) reject(new Error(`WebSocket closed before opening (${event.code} ${event.reason})`));
        else if (!this.closedByUs) this.scheduleReconnect();
      };
      ws.onerror = () => {
        if (!opened) console.error('[WS] Connection failed');
      };
    });
  }

  private handle(event: AppEvent, notify: boolean) {
    const stored = !event.type.startsWith('presence.') && event.type !== 'agent.text.delta';
    if (stored && event.seq <= this.since) return; // already applied (a reconnect overlaps)
    this.state = applyEvent(this.state, event);
    if (stored) this.since = event.seq;
    if (notify && (!stored || event.seq > this.liveAfter)) this.eventHandlers.forEach(h => h(event));
    if (notify) this.notifyState();
  }

  private notifyState() {
    this.stateHandlers.forEach(h => h(this.state));
    this.presenceHandlers.forEach(h => h(this.state.presence));
  }

  private scheduleReconnect() {
    if (this.reconnectAttempts >= MAX_RECONNECTS) {
      console.error('[WS] Max reconnect attempts reached');
      return;
    }
    const delay = 1000 * 2 ** this.reconnectAttempts;
    this.reconnectAttempts++;
    setTimeout(() => {
      if (!this.closedByUs) this.connect().catch(() => this.scheduleReconnect());
    }, delay);
  }

  // Apply an event produced locally (demo mode) as if the server had sent it
  injectEvent(event: AppEvent) {
    this.handle(event, true);
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
    handler(this.state);
    return () => this.stateHandlers.delete(handler);
  }

  private send(message: Record<string, unknown>) {
    if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify(message));
  }

  sendPresence(tab: Presence['tab']) {
    this.send({ type: 'tab', tab });
  }

  sendTyping(typing: boolean) {
    this.send({ type: 'typing', typing });
  }

  disconnect() {
    this.closedByUs = true;
    this.ws?.close(1000, 'Client disconnect');
    this.ws = null;
  }

  getState(): RoomState {
    return this.state;
  }

  getSince(): number {
    return this.since;
  }
}

// One socket for the room on screen
let currentSocket: SocketClient | null = null;

export function getSocket(roomId: string, room?: Room, currentUser?: User): SocketClient {
  if (currentSocket && currentSocket['roomId'] === roomId) return currentSocket;
  currentSocket?.disconnect();
  currentSocket = new SocketClient(roomId, room, currentUser);
  return currentSocket;
}

export function clearSocket() {
  currentSocket?.disconnect();
  currentSocket = null;
}
