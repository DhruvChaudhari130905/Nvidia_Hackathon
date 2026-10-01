// Notification hub for the room. Anything worth telling the user about (team messages, finished tasks,
// builds, agent questions, terminal commands) goes through notify(). It is always kept in the bell's list;
// it pops a toast while the tab is visible and a desktop notification while it's in the background.
import { useSyncExternalStore } from 'react';

export type NotificationCategory = 'messages' | 'mentions' | 'tasks' | 'builds' | 'decisions' | 'terminal';

export const CATEGORY_LABELS: Record<NotificationCategory, { label: string; detail: string }> = {
  mentions: { label: 'Mentions', detail: 'Someone @mentions you' },
  messages: { label: 'Team messages', detail: 'New messages from people in the room' },
  tasks: { label: 'Agent tasks', detail: 'A plan item finishes or gets skipped' },
  builds: { label: 'Builds', detail: 'A build passes or fails' },
  decisions: { label: 'Questions & votes', detail: 'The agent asks something or a vote opens' },
  terminal: { label: 'Terminal', detail: 'Long commands finish or a dev server starts' },
};

export interface AppNotification {
  id: string;
  category: NotificationCategory;
  title: string;
  body?: string;
  tone: 'info' | 'ok' | 'err';
  at: number;
  read: boolean;
  // Runs when the notification (toast, bell item or desktop notification) is clicked
  onClick?: () => void;
}

interface Settings {
  enabled: Record<NotificationCategory, boolean>;
  desktop: boolean; // user wants desktop notifications (browser permission is separate)
}

const SETTINGS_KEY = 'mux_notification_settings';
const MAX_ITEMS = 50;
const DEFAULT_SETTINGS: Settings = {
  enabled: { mentions: true, messages: true, tasks: true, builds: true, decisions: true, terminal: true },
  desktop: true,
};

interface Store {
  items: AppNotification[];
  toasts: AppNotification[];
  settings: Settings;
  permission: NotificationPermission | 'unsupported';
}

let store: Store = {
  items: [],
  toasts: [],
  settings: DEFAULT_SETTINGS,
  permission: 'default',
};
let loaded = false;
const listeners = new Set<() => void>();

function set(patch: Partial<Store>) {
  store = { ...store, ...patch };
  listeners.forEach(l => l());
  updateTitleBadge();
}

function load() {
  if (loaded || typeof window === 'undefined') return;
  loaded = true;
  try {
    const saved = JSON.parse(localStorage.getItem(SETTINGS_KEY) || 'null');
    if (saved) store.settings = { ...DEFAULT_SETTINGS, ...saved, enabled: { ...DEFAULT_SETTINGS.enabled, ...saved.enabled } };
  } catch {
    // storage unavailable or corrupt; keep defaults
  }
  store.permission = 'Notification' in window ? Notification.permission : 'unsupported';
  document.addEventListener('visibilitychange', updateTitleBadge);
}

function saveSettings(settings: Settings) {
  try {
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
  } catch {
    // storage unavailable
  }
  set({ settings });
}

// ───────────── Tab title badge: "(3) Lotus Yoga · MUX" while unread ─────────────

let baseTitle: string | null = null;
function updateTitleBadge() {
  if (typeof document === 'undefined') return;
  const unread = store.items.filter(n => !n.read).length;
  const current = document.title.replace(/^\(\d+\+?\)\s/, '');
  if (baseTitle === null || current !== baseTitle) baseTitle = current;
  document.title = unread ? `(${unread > 9 ? '9+' : unread}) ${baseTitle}` : baseTitle;
}

// ───────────── Public API ─────────────

export function notify(n: Omit<AppNotification, 'id' | 'at' | 'read' | 'tone'> & { tone?: AppNotification['tone'] }) {
  load();
  const { settings } = store;
  if (!settings.enabled[n.category]) return;

  const item: AppNotification = { tone: 'info', ...n, id: Math.random().toString(36).slice(2), at: Date.now(), read: false };
  const visible = document.visibilityState === 'visible' && document.hasFocus();

  set({ items: [item, ...store.items].slice(0, MAX_ITEMS) });

  if (visible) {
    // The feed already shows team messages, so only mentions pop a toast for chat
    if (item.category !== 'messages') {
      set({ toasts: [...store.toasts, item].slice(-4) });
      setTimeout(() => dismissToast(item.id), 6000);
    }
    return;
  }

  if (settings.desktop && store.permission === 'granted') {
    try {
      const desktop = new Notification(item.title, { body: item.body, tag: `mux-${item.category}`, icon: '/favicon.ico' });
      desktop.onclick = () => {
        window.focus();
        item.onClick?.();
        markRead(item.id);
        desktop.close();
      };
    } catch {
      // Some browsers only allow notifications from a service worker; the bell still has it
    }
  }
}

export function dismissToast(id: string) {
  if (store.toasts.some(t => t.id === id)) set({ toasts: store.toasts.filter(t => t.id !== id) });
}

export function markRead(id: string) {
  set({ items: store.items.map(n => (n.id === id ? { ...n, read: true } : n)) });
}

export function markAllRead() {
  if (store.items.some(n => !n.read)) set({ items: store.items.map(n => ({ ...n, read: true })) });
}

export function clearNotifications() {
  set({ items: [], toasts: [] });
}

export function setCategoryEnabled(category: NotificationCategory, on: boolean) {
  saveSettings({ ...store.settings, enabled: { ...store.settings.enabled, [category]: on } });
}

export function setDesktopEnabled(on: boolean) {
  saveSettings({ ...store.settings, desktop: on });
}

// Must be called from a click: browsers ignore permission requests that aren't user-initiated
export async function requestDesktopPermission(): Promise<NotificationPermission | 'unsupported'> {
  load();
  if (!('Notification' in window)) return 'unsupported';
  const permission = await Notification.requestPermission();
  set({ permission });
  if (permission === 'granted') setDesktopEnabled(true);
  return permission;
}

function subscribe(listener: () => void) {
  load();
  listeners.add(listener);
  return () => listeners.delete(listener);
}

const serverSnapshot = store;
export function useNotifications(): Store {
  return useSyncExternalStore(subscribe, () => store, () => serverSnapshot);
}
