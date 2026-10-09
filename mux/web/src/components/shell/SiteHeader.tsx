'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { Share2, Code2, User, Menu, X, Check } from 'lucide-react';
import { Logo } from './Logo';
import { formatClock, useTicker } from './Motion';
import { getUser } from '@/lib/supabase';
import { colorForId, getLastRoom, LAST_ROOM_CHANGED, type LastRoom } from '@/lib/preferences';

export type NavKey = 'overview' | 'rooms' | 'sandbox' | 'pricing' | 'docs';

export const NAV_ITEMS: { key: NavKey; label: string; href: string }[] = [
  { key: 'overview', label: 'Overview', href: '/' },
  { key: 'rooms', label: 'Rooms', href: '/dashboard' },
  { key: 'sandbox', label: 'Sandbox', href: '/sandbox' },
  { key: 'pricing', label: 'Pricing', href: '/pricing' },
  { key: 'docs', label: 'Docs', href: '/docs' },
];

// Pill for the last room you opened, with a live "time since opened" clock; links back into it
export function SessionPill() {
  const [last, setLast] = useState<LastRoom | null>(null);
  const [ready, setReady] = useState(false);
  useTicker(1000); // re-render each second for the clock

  useEffect(() => {
    const read = () => setLast(getLastRoom());
    read();
    setReady(true);
    window.addEventListener(LAST_ROOM_CHANGED, read);
    return () => window.removeEventListener(LAST_ROOM_CHANGED, read);
  }, []);

  const pill = 'flex items-center gap-space-sm rounded-lg bg-surface-container px-space-md py-space-xs text-body-sm transition-colors hover:bg-surface-container-high';
  if (!ready) return <span className={`${pill} h-7 w-56 animate-pulse`} aria-hidden="true" />;

  if (!last) {
    return (
      <Link href="/dashboard?new=1" className={pill}>
        <span className="flex h-2 w-2 rounded-full bg-outline" />
        <span className="font-code text-code-sm text-on-surface-variant">No active room</span>
        <span className="rounded bg-primary/20 px-space-xs font-code text-code-sm text-primary">Start one</span>
      </Link>
    );
  }

  const seconds = Math.max(0, Math.floor((Date.now() - last.openedAt) / 1000));
  return (
    <Link href={`/room/${last.id}`} className={pill} title={`Back to ${last.title}`}>
      <span className="flex h-2 w-2 rounded-full bg-primary animate-pulse" />
      <span className="max-w-[180px] truncate font-code text-code-sm text-on-surface">{last.title}</span>
      <span className="font-code text-code-sm tabular-nums text-outline">• {formatClock(seconds % 360000)}</span>
      <span className="rounded bg-primary/20 px-space-xs font-code text-code-sm text-primary">Resume</span>
    </Link>
  );
}

// Signed-in user's initials for the avatar, or null when signed out
function useHeaderUser() {
  const [me, setMe] = useState<{ initials: string; color: string; name: string } | null>(null);
  useEffect(() => {
    let cancelled = false;
    getUser()
      .then(u => {
        if (cancelled || !u) return;
        const name: string = u.user_metadata?.full_name || u.email?.split('@')[0] || 'User';
        const initials = name.split(' ').map(p => p[0]).join('').slice(0, 2).toUpperCase();
        setMe({ initials, color: colorForId(u.id), name });
      })
      .catch(() => {
        // not signed in / auth unavailable: keep the generic avatar
      });
    return () => { cancelled = true; };
  }, []);
  return me;
}

export function HeaderActions({ profileActive = false }: { profileActive?: boolean }) {
  const [copied, setCopied] = useState(false);
  const me = useHeaderUser();

  // Copy the page link; falls back to a hidden textarea where the Clipboard API is unavailable (plain http)
  const handleShare = async () => {
    const url = window.location.href;
    try {
      await navigator.clipboard.writeText(url);
    } catch {
      const area = document.createElement('textarea');
      area.value = url;
      area.style.position = 'fixed';
      area.style.opacity = '0';
      document.body.appendChild(area);
      area.select();
      document.execCommand('copy');
      area.remove();
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="flex items-center gap-space-md">
      <div className="flex items-center gap-space-xs">
        <button
          type="button"
          onClick={handleShare}
          className="flex items-center gap-space-xs rounded-lg bg-surface-container-high px-space-md py-space-sm font-ui text-label-md text-on-surface transition-colors hover:bg-surface-bright hover:shadow-[0_0_15px_rgba(59,130,246,0.3)]"
        >
          {copied ? <Check className="h-4 w-4" /> : <Share2 className="h-4 w-4" />}
          <span className="hidden sm:inline">{copied ? 'Copied' : 'Share'}</span>
        </button>
        <Link
          href="/dashboard?export=1"
          className="flex items-center gap-space-xs rounded-lg bg-primary px-space-md py-space-sm font-ui text-label-md font-bold text-on-primary transition-colors hover:bg-primary/90 hover:shadow-[0_0_20px_rgba(59,130,246,0.5)]"
        >
          <Code2 className="h-4 w-4" />
          <span className="hidden sm:inline">Export to GitHub</span>
        </Link>
      </div>
      <Link
        href={me ? '/profile' : '/login'}
        aria-label={me ? 'Profile' : 'Sign in'}
        title={me ? `${me.name} · Profile` : 'Sign in'}
        aria-current={profileActive ? 'page' : undefined}
        className={`grid h-8 w-8 place-items-center rounded-full font-code text-[11px] font-bold transition-all hover:scale-110 hover:shadow-[0_0_15px_rgba(59,130,246,0.5)] ${
          profileActive ? 'ring-2 ring-secondary ring-offset-2 ring-offset-surface' : ''
        } ${me ? 'text-[#0d1117]' : 'bg-primary'}`}
        style={me ? { background: me.color } : undefined}
      >
        {me ? me.initials : <User className="h-[18px] w-[18px] text-on-primary" />}
      </Link>
    </div>
  );
}

interface SiteHeaderProps {
  active?: NavKey;
  profileActive?: boolean;
}

export function SiteHeader({ active, profileActive = false }: SiteHeaderProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  return (
    <header
      className={`fixed top-0 z-50 w-full border-b font-ui backdrop-blur-xl transition-all duration-300 ${
        scrolled
          ? 'border-outline-variant/40 bg-surface/90 shadow-[0_8px_30px_rgba(0,0,0,0.35)]'
          : 'border-transparent bg-surface/60 shadow-none'
      }`}
    >
      <div className="flex h-16 w-full items-center justify-between px-gutter">
        <div className="flex items-center gap-space-lg">
          <button
            type="button"
            className="-ml-1 rounded-md p-1 text-on-surface-variant hover:text-on-surface md:hidden"
            onClick={() => setMenuOpen(o => !o)}
            aria-label={menuOpen ? 'Close menu' : 'Open menu'}
            aria-expanded={menuOpen}
          >
            {menuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
          <Logo />
          <nav className="hidden items-center gap-space-md md:flex">
            {NAV_ITEMS.map(item => (
              <Link
                key={item.key}
                href={item.href}
                aria-current={item.key === active ? 'page' : undefined}
                className={`group relative rounded-md px-space-sm py-space-xs text-body-md transition-colors ${
                  item.key === active
                    ? 'bg-surface-container-high font-bold text-on-surface'
                    : 'text-on-surface-variant hover:bg-surface-container/60 hover:text-on-surface'
                }`}
              >
                {item.label}
                <span
                  className={`absolute inset-x-2 -bottom-[3px] h-[2px] origin-left rounded-full bg-gradient-to-r from-primary to-secondary transition-transform duration-300 ${
                    item.key === active ? 'scale-x-100' : 'scale-x-0 group-hover:scale-x-100'
                  }`}
                />
              </Link>
            ))}
          </nav>
        </div>
        <div className="flex items-center gap-space-md">
          <div className="hidden lg:block">
            <SessionPill />
          </div>
          <HeaderActions profileActive={profileActive} />
        </div>
      </div>
      {menuOpen && (
        <nav className="grid gap-1 border-t border-outline-variant/30 bg-surface px-gutter py-space-sm md:hidden">
          {NAV_ITEMS.map(item => (
            <Link
              key={item.key}
              href={item.href}
              onClick={() => setMenuOpen(false)}
              className={`rounded-md px-space-sm py-space-sm text-body-md ${
                item.key === active ? 'bg-surface-container-high font-bold text-on-surface' : 'text-on-surface-variant'
              }`}
            >
              {item.label}
            </Link>
          ))}
        </nav>
      )}
    </header>
  );
}
