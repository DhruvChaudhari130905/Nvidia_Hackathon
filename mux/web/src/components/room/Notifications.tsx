'use client';

import React, { useEffect, useRef, useState } from 'react';
import { Bell, BellRing, X, Settings2, CheckCheck, Trash2, MessageSquare, AtSign, ListChecks, Hammer, Vote, SquareTerminal } from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';
import {
  CATEGORY_LABELS, clearNotifications, dismissToast, markAllRead, markRead, requestDesktopPermission, setCategoryEnabled,
  setDesktopEnabled, useNotifications, type AppNotification, type NotificationCategory,
} from '@/lib/notifications';

const ICONS: Record<NotificationCategory, React.ElementType> = {
  messages: MessageSquare,
  mentions: AtSign,
  tasks: ListChecks,
  builds: Hammer,
  decisions: Vote,
  terminal: SquareTerminal,
};

const TONE: Record<AppNotification['tone'], string> = {
  info: 'text-[var(--coord)]',
  ok: 'text-[var(--coder)]',
  err: 'text-[var(--conflict)]',
};

export function NotificationBell() {
  const { items, settings, permission } = useNotifications();
  const [open, setOpen] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const unread = items.filter(n => !n.read).length;

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false); };
    window.addEventListener('mousedown', close);
    window.addEventListener('keydown', esc);
    return () => {
      window.removeEventListener('mousedown', close);
      window.removeEventListener('keydown', esc);
    };
  }, [open]);

  const desktopOn = settings.desktop && permission === 'granted';

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        className="icon-btn relative"
        onClick={() => setOpen(o => !o)}
        aria-label={unread ? `Notifications, ${unread} unread` : 'Notifications'}
        aria-expanded={open}
        title="Notifications"
      >
        {unread ? <BellRing className="h-4 w-4 text-[var(--ink)]" /> : <Bell className="h-4 w-4" />}
        {unread > 0 && (
          <span className="absolute -right-0.5 -top-0.5 grid h-4 min-w-4 place-items-center rounded-full bg-[var(--conflict)] px-1 font-sans text-[9.5px] font-semibold text-white">
            {unread > 9 ? '9+' : unread}
          </span>
        )}
      </button>

      {open && (
        <div className="item-in absolute right-0 top-full z-50 mt-2 w-80 overflow-hidden rounded-2xl glass-modal font-sans">
          <div className="flex items-center justify-between border-b border-[var(--line)] px-3 py-2">
            <span className="text-[12.5px] font-semibold text-[var(--ink)]">{showSettings ? 'Notification settings' : 'Notifications'}</span>
            <div className="flex items-center gap-0.5">
              {!showSettings && items.length > 0 && (
                <>
                  <button type="button" className="icon-btn" title="Mark all read" aria-label="Mark all read" onClick={markAllRead}><CheckCheck className="h-3.5 w-3.5" /></button>
                  <button type="button" className="icon-btn" title="Clear all" aria-label="Clear all" onClick={clearNotifications}><Trash2 className="h-3.5 w-3.5" /></button>
                </>
              )}
              <button type="button" className={`icon-btn ${showSettings ? 'on' : ''}`} title="Settings" aria-label="Notification settings" aria-pressed={showSettings} onClick={() => setShowSettings(s => !s)}>
                <Settings2 className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>

          {showSettings ? (
            <div className="max-h-96 overflow-auto p-3">
              <div className="mb-3 rounded-md border border-[var(--line)] bg-[var(--bg)] p-2.5">
                <p className="text-[12px] text-[var(--ink)]">Desktop notifications</p>
                <p className="mb-2 text-[11px] leading-snug text-[var(--faint)]">Shown by your OS while this tab is in the background.</p>
                {permission === 'unsupported' ? (
                  <p className="text-[11px] text-[#d29922]">This browser doesn&apos;t support them.</p>
                ) : permission === 'denied' ? (
                  <p className="text-[11px] text-[#d29922]">Blocked for this site. Allow notifications in the browser&apos;s site settings, then reload.</p>
                ) : permission === 'default' ? (
                  <button type="button" className="btn text-[12px]" onClick={() => void requestDesktopPermission()}>Allow desktop notifications</button>
                ) : (
                  <Toggle on={settings.desktop} onChange={setDesktopEnabled} label={desktopOn ? 'On' : 'Off'} />
                )}
              </div>
              <p className="mb-1.5 text-[10.5px] uppercase tracking-[0.1em] text-[var(--faint)]">Notify me about</p>
              <div className="space-y-2">
                {(Object.keys(CATEGORY_LABELS) as NotificationCategory[]).map(c => {
                  const Icon = ICONS[c];
                  return (
                    <div key={c} className="flex items-center gap-2.5">
                      <Icon className="h-3.5 w-3.5 flex-none text-[var(--muted)]" />
                      <span className="min-w-0 flex-1">
                        <span className="block text-[12px] text-[var(--ink)]">{CATEGORY_LABELS[c].label}</span>
                        <span className="block text-[11px] text-[var(--faint)]">{CATEGORY_LABELS[c].detail}</span>
                      </span>
                      <Toggle on={settings.enabled[c]} onChange={on => setCategoryEnabled(c, on)} label={CATEGORY_LABELS[c].label} hideLabel />
                    </div>
                  );
                })}
              </div>
            </div>
          ) : (
            <div className="max-h-96 overflow-auto">
              {permission === 'default' && (
                <button type="button" onClick={() => void requestDesktopPermission()} className="flex w-full items-center gap-2 border-b border-[var(--line)] bg-[var(--coord)]/10 px-3 py-2 text-left text-[11.5px] text-[var(--ink)] hover:bg-[var(--coord)]/15">
                  <BellRing className="h-3.5 w-3.5 flex-none text-[var(--coord)]" /> Get notified when you&apos;re in another tab: allow desktop notifications
                </button>
              )}
              {items.length === 0 ? (
                <p className="px-3 py-8 text-center text-[12px] text-[var(--faint)]">You&apos;re all caught up.</p>
              ) : (
                items.map(n => <Item key={n.id} n={n} onClick={() => { markRead(n.id); n.onClick?.(); }} />)
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Item({ n, onClick }: { n: AppNotification; onClick: () => void }) {
  const Icon = ICONS[n.category];
  return (
    <button type="button" onClick={onClick} className={`flex w-full gap-2.5 border-b border-[var(--line)]/60 px-3 py-2 text-left transition-colors last:border-0 hover:bg-white/5 ${n.read ? 'opacity-70' : ''}`}>
      <Icon className={`mt-0.5 h-3.5 w-3.5 flex-none ${TONE[n.tone]}`} />
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-1.5">
          <span className="truncate text-[12px] text-[var(--ink)]">{n.title}</span>
          {!n.read && <span className="h-1.5 w-1.5 flex-none rounded-full bg-[var(--coord)]" />}
        </span>
        {n.body && <span className="line-clamp-2 block text-[11.5px] leading-snug text-[var(--muted)]">{n.body}</span>}
        <span className="block text-[10.5px] text-[var(--faint)]">{formatDistanceToNow(n.at, { addSuffix: true })}</span>
      </span>
    </button>
  );
}

function Toggle({ on, onChange, label, hideLabel = false }: { on: boolean; onChange: (on: boolean) => void; label: string; hideLabel?: boolean }) {
  return (
    <label className="inline-flex cursor-pointer items-center gap-2 text-[11.5px] text-[var(--muted)]">
      <input type="checkbox" className="peer sr-only" checked={on} onChange={e => onChange(e.target.checked)} aria-label={label} />
      <span className="relative h-4 w-7 rounded-full bg-[var(--line)] transition-colors after:absolute after:left-0.5 after:top-0.5 after:h-3 after:w-3 after:rounded-full after:bg-white after:transition-transform peer-checked:bg-[var(--coord)] peer-checked:after:translate-x-3 peer-focus-visible:ring-2 peer-focus-visible:ring-[var(--coord)]" />
      {!hideLabel && label}
    </label>
  );
}

// Pop-ups in the corner while the tab is visible
export function NotificationToasts() {
  const { toasts } = useNotifications();
  if (!toasts.length) return null;
  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-[60] flex w-80 flex-col gap-2" aria-live="polite">
      {toasts.map(n => {
        const Icon = ICONS[n.category];
        return (
          <div key={n.id} className="item-in pointer-events-auto flex gap-2.5 rounded-2xl glass-modal p-3 font-sans">
            <Icon className={`mt-0.5 h-4 w-4 flex-none ${TONE[n.tone]}`} />
            <button type="button" className="min-w-0 flex-1 text-left" onClick={() => { markRead(n.id); dismissToast(n.id); n.onClick?.(); }}>
              <span className="block text-[12.5px] font-medium text-[var(--ink)]">{n.title}</span>
              {n.body && <span className="line-clamp-2 block text-[11.5px] leading-snug text-[var(--muted)]">{n.body}</span>}
            </button>
            <button type="button" className="icon-btn !h-5 !w-5 flex-none" aria-label="Dismiss" onClick={() => dismissToast(n.id)}><X className="h-3 w-3" /></button>
          </div>
        );
      })}
    </div>
  );
}
