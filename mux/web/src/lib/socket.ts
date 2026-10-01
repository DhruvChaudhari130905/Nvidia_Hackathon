// WebSocket client for real-time events and presence
import type { AppEvent, Presence, RoomState } from '@/types';
import { demoRoomEvents, isDemoMode } from './demo';
import { applyEvent, createEmptyState } from './reducer';
import { getAccessToken } from './supabase';

export type SocketStatus = 'connecting' | 'open' | 'reconnecting' | 'offline';

type EventHandler = (event: AppEvent) => void;
type PresenceHandler = (presence: Presence[]) => void;
type StateHandler = (state: RoomState) => void;
type StatusHandler = (status: SocketStatus) => void;

export class SocketClient {
  private ws: WebSocket | null = null;
  private apiHost: string;
  private roomId: string;
  private since: number;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 1000;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  // Set by disconnect() so the close it causes doesn't start a reconnect
  private closedByClient = false;
  private eventHandlers: Set<EventHandler> = new Set();
  private presenceHandlers: Set<PresenceHandler> = new Set();
  private stateHandlers: Set<StateHandler> = new Set();
  private statusHandlers: Set<StatusHandler> = new Set();
  private currentState: RoomState | null = null;
  private status: SocketStatus = 'connecting';

  constructor(roomId: string, since: number = 0) {
    this.roomId = roomId;
    this.since = since;
    this.apiHost = process.env.NEXT_PUBLIC_API_URL?.replace(/^http/, 'ws') || 'ws://localhost:8000';
  }

  get id(): string {
    return this.roomId;
  }

  connect(): Promise<void> {
    this.closedByClient = false;
    if (isDemoMode()) {
      // Replay a canned room instead of opening a WebSocket
      if (!this.currentState) this.handleMessage(demoRoomEvents(this.roomId));
      this.setStatus('open');
      return Promise.resolve();
    }
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
      return Promise.resolve();
    }
    return this.open();
  }

  private async open(): Promise<void> {
    const token = await getAccessToken();
    if (this.closedByClient) return;
    // Built on every (re)connect so the server only replays what we haven't seen
    const url = `${this.apiHost}/rooms/${this.roomId}/ws?since=${this.since}`;

    return new Promise((resolve, reject) => {
      let settled = false;
      try {
        const ws = new WebSocket(url);
        this.ws = ws;

        ws.onopen = () => {
          // The first message authenticates the socket (the JWT isn't put in the URL, where it would be logged)
          if (token) ws.send(JSON.stringify({ type: 'auth', payload: { token } }));
          this.reconnectAttempts = 0;
          this.setStatus('open');
          settled = true;
          resolve();
        };

        ws.onmessage = (event) => {
          try {
            this.handleMessage(JSON.parse(event.data));
          } catch (e) {
            console.error('[WS] Failed to parse message:', e);
          }
        };

        ws.onclose = (event) => {
          if (this.ws !== ws) return; // an old socket we already replaced
          this.ws = null;
          if (this.closedByClient) return;
          console.log('[WS] Disconnected:', event.code, event.reason);
          if (!settled) {
            settled = true;
            reject(new Error('WebSocket connection failed'));
          }
          this.scheduleReconnect();
        };

        ws.onerror = (error) => {
          console.error('[WS] Error:', error);
        };
      } catch (e) {
        reject(e);
      }
    });
  }

  private handleMessage(data: unknown) {
    // Handle initial state dump (array of events)
    if (Array.isArray(data)) {
      for (const event of data) this.applyEvent(event as AppEvent);
      this.notifyState();
      return;
    }

    // Handle single event
    const event = data as AppEvent;
    if (!this.applyEvent(event)) return;
    this.notifyEvent(event);
    this.notifyState();
  }

  // Returns false for an event we've already applied (a replay after reconnect)
  private applyEvent(event: AppEvent): boolean {
    if (typeof event.seq === 'number') {
      if (event.seq <= this.since && this.currentState) return false;
      this.since = Math.max(this.since, event.seq);
    }
    this.currentState = applyEvent(this.currentState ?? createEmptyState(this.roomId), event);
    return true;
  }

  private notifyEvent(event: AppEvent) {
    this.eventHandlers.forEach(h => h(event));
  }

  private notifyState() {
    const state = this.currentState;
    if (!state) return;
    // The reducer returns a new object for every change, so handing out the state itself re-renders React
    this.stateHandlers.forEach(h => h(state));
    this.presenceHandlers.forEach(h => h(state.presence));
  }

  private setStatus(status: SocketStatus) {
    if (this.status === status) return;
    this.status = status;
    this.statusHandlers.forEach(h => h(status));
  }

  private scheduleReconnect() {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error('[WS] Max reconnect attempts reached');
      this.setStatus('offline');
      return;
    }
    this.setStatus('reconnecting');
    const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts);
    this.reconnectAttempts++;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      // A failed attempt closes the socket, which schedules the next one
      this.open().catch(() => {});
    }, delay);
  }

  // Try again after giving up (the "Reconnect" button)
  reconnect() {
    this.reconnectAttempts = 0;
    this.closedByClient = false;
    this.setStatus('connecting');
    this.open().catch(() => {});
  }

  // Apply an event produced locally (demo mode) as if the server had sent it
  injectEvent(event: AppEvent) {
    this.handleMessage(event);
  }

  onEvent(handler: EventHandler) {
    this.eventHandlers.add(handler);
    return () => { this.eventHandlers.delete(handler); };
  }

  onPresence(handler: PresenceHandler) {
    this.presenceHandlers.add(handler);
    return () => { this.presenceHandlers.delete(handler); };
  }

  onState(handler: StateHandler) {
    this.stateHandlers.add(handler);
    if (this.currentState) handler(this.currentState);
    return () => { this.stateHandlers.delete(handler); };
  }

  onStatus(handler: StatusHandler) {
    this.statusHandlers.add(handler);
    handler(this.status);
    return () => { this.statusHandlers.delete(handler); };
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
    this.closedByClient = true;
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.reconnectTimer = null;
    const ws = this.ws;
    this.ws = null;
    if (ws) {
      ws.onclose = null;
      ws.close(1000, 'Client disconnect');
    }
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
  if (currentSocket && currentSocket.id === roomId) {
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
