'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { formatDistanceToNow, format } from 'date-fns';
import { UserCircle, DoorOpen, Users, Coins, Crown, Github, LogOut, ArrowRight, Check, Mail, Sparkles } from 'lucide-react';
import { getUser, loginHref, signOut } from '@/lib/supabase';
import { isDemoMode } from '@/lib/demo';
import { api } from '@/lib/api';
import { colorForId, getDefaultRole, setDefaultRole } from '@/lib/preferences';
import { AppShell, CountUp, Reveal, Spotlight } from '@/components/shell';
import type { DomainRole, Room, User } from '@/types';

// Profile screen. No stitch screen exists for it; it follows the Active Rooms layout.

const FREE_ROOM_LIMIT = 3;

const ROLE_OPTIONS: { value: DomainRole; label: string; detail: string }[] = [
  { value: 'pm', label: 'Product Manager', detail: 'Your vote counts 2× on scope conflicts' },
  { value: 'design', label: 'Designer', detail: 'Your vote counts 2× on UI conflicts' },
  { value: 'eng', label: 'Engineer', detail: 'Your vote counts 2× on architecture conflicts' },
];

function lastActivity(room: Room): number {
  return new Date(room.updated_at || room.created_at).getTime();
}

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${Math.round(n / 1_000)}K`;
  return String(n);
}

export default function ProfilePage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [provider, setProvider] = useState('email');
  const [joinedAt, setJoinedAt] = useState<string | null>(null);
  const [rooms, setRooms] = useState<Room[]>([]);
  const [loading, setLoading] = useState(true);
  const [defaultRole, setDefaultRoleState] = useState<DomainRole>('pm');
  const [savedRole, setSavedRole] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [github, setGithub] = useState<{ connected: boolean; login: string | null } | null>(null);
  const [githubNote, setGithubNote] = useState<string | null>(null);
  const [barReady, setBarReady] = useState(false); // lets the plan bar grow from 0 after first paint

  useEffect(() => {
    const load = async () => {
      try {
        const authUser = await getUser();
        if (!authUser) {
          router.push(loginHref());
          return;
        }
        const name = authUser.user_metadata.full_name || authUser.email?.split('@')[0] || 'User';
        setUser({
          id: authUser.id,
          email: authUser.email || '',
          name,
          avatar_url: authUser.user_metadata.avatar_url,
          initials: name.split(' ').map((p: string) => p[0]).join('').slice(0, 2).toUpperCase(),
          color: colorForId(authUser.id),
        });

        // Supabase users carry provider and signup time; the demo user has neither
        const meta = authUser as { app_metadata?: { provider?: string }; created_at?: string };
        setProvider(isDemoMode() ? 'demo' : meta.app_metadata?.provider || 'email');
        setJoinedAt(meta.created_at ?? null);
        setDefaultRoleState(getDefaultRole());

        setRooms(await api.listRooms());
        // GitHub sends the browser back here with ?github=connected or ?github=error&detail=...
        const params = new URLSearchParams(window.location.search);
        if (params.get('github') === 'error') setGithubNote(`GitHub was not connected: ${params.get('detail') ?? 'unknown error'}`);
        api.githubStatus().then(setGithub).catch(() => setGithub(null));
        requestAnimationFrame(() => setTimeout(() => setBarReady(true), 150));
      } catch (error) {
        console.error('Failed to load profile:', error);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [router]);

  const handleSignOut = async () => {
    await signOut();
    router.push('/login');
  };

  const handleRoleChange = (role: DomainRole) => {
    setDefaultRoleState(role);
    setDefaultRole(role);
    setSavedRole(true);
    setTimeout(() => setSavedRole(false), 1500);
  };

  const handleConnectGitHub = async () => {
    setConnecting(true);
    try {
      const { url } = await api.connectGitHub();
      window.location.href = url;
    } catch (error) {
      console.error('Failed to connect GitHub:', error);
      alert('Could not start the GitHub connection. Is the backend running?');
      setConnecting(false);
    }
  };

  if (loading || !user) {
    return (
      <AppShell active="profile">
        <div className="flex flex-1 items-center justify-center">
          <div className="h-8 w-8 animate-spin rounded-full border-b-2 border-primary" />
        </div>
      </AppShell>
    );
  }

  const owned = rooms.filter(r => r.owner_id === user.id);
  const shared = rooms.filter(r => r.owner_id !== user.id);
  const collaborators = new Map<string, User>();
  rooms.forEach(r => r.members.forEach(m => { if (m.user_id !== user.id) collaborators.set(m.user_id, m.user); }));
  const tokenBudget = owned.reduce((sum, r) => sum + r.budget_tokens_cap, 0);
  const roomUsage = Math.min(100, (owned.length / FREE_ROOM_LIMIT) * 100);
  const sortedRooms = [...rooms].sort((a, b) => lastActivity(b) - lastActivity(a));

  const stats = [
    { icon: Crown, label: 'Rooms owned', value: owned.length, color: 'text-primary' },
    { icon: DoorOpen, label: 'Shared with you', value: shared.length, color: 'text-secondary' },
    { icon: Users, label: 'Collaborators', value: collaborators.size, color: 'text-primary' },
    { icon: Coins, label: 'Token budget', value: formatTokens(tokenBudget), color: 'text-tertiary' },
  ];

  return (
    <AppShell active="profile">
      {/* Identity */}
      <Spotlight className="relative mb-space-xl animate-fade-up overflow-hidden rounded-lg border border-surface-container-highest bg-surface-container/90 p-space-xl shadow-md backdrop-blur-md">
        <div className="float-slow pointer-events-none absolute -right-16 -top-16 h-64 w-64 rounded-full bg-primary/10 blur-3xl" />
        <div className="relative z-10 flex flex-col items-start gap-space-lg md:flex-row md:items-center">
          <div
            className="relative grid h-20 w-20 flex-none place-items-center rounded-full border-2 border-primary/40 font-headline text-2xl font-bold text-[#0d1117] shadow-[0_0_25px_rgba(59,130,246,0.3)]"
            style={{ background: user.color }}
          >
            <span className="absolute -inset-1.5 animate-spin rounded-full border-2 border-transparent border-r-secondary/70 border-t-primary/70 [animation-duration:4s]" aria-hidden="true" />
            {user.initials}
            <span className="absolute bottom-0.5 right-0.5 h-4 w-4 rounded-full border-2 border-surface-container bg-primary" title="Online" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="mb-space-xs flex flex-wrap items-center gap-space-sm">
              <h1 className="font-headline text-headline-lg text-on-surface">{user.name}</h1>
              <span className="rounded bg-primary/20 px-space-sm py-0.5 font-code text-code-sm uppercase tracking-wider text-primary">
                {provider === 'demo' ? 'Demo account' : 'Free Developer'}
              </span>
            </div>
            <p className="mb-space-sm flex items-center gap-space-xs text-body-md text-on-surface-variant">
              <Mail className="h-4 w-4" />
              {user.email}
            </p>
            <p className="font-code text-code-sm text-outline">
              Signed in with {provider === 'demo' ? 'demo mode' : provider}
              {joinedAt && ` · member since ${format(new Date(joinedAt), 'MMM yyyy')}`}
            </p>
          </div>
          <Link
            href="/dashboard"
            className="btn-shine flex items-center gap-space-sm rounded-lg bg-primary px-space-lg py-space-md font-headline text-headline-sm text-on-primary shadow-md transition-all hover:-translate-y-0.5 hover:bg-primary/90 hover:shadow-[0_0_20px_rgba(59,130,246,0.5)]"
          >
            <DoorOpen className="h-[18px] w-[18px]" />
            My Rooms
          </Link>
        </div>
      </Spotlight>

      {/* Stats */}
      <div className="mb-space-xl grid grid-cols-2 gap-space-lg lg:grid-cols-4">
        {stats.map((stat, i) => {
          const Icon = stat.icon;
          return (
            <Reveal key={stat.label} delay={i * 80} className="h-full">
              <Spotlight className="group h-full rounded-lg border border-surface-container-highest bg-surface-container/90 p-space-lg backdrop-blur-md transition-all duration-300 hover:-translate-y-1">
                <Icon className={`mb-space-sm h-5 w-5 transition-transform duration-300 group-hover:scale-125 ${stat.color}`} />
                <p className={`font-headline text-3xl font-bold ${stat.color}`}>
                  <CountUp value={stat.value} duration={1100} />
                </p>
                <p className="text-body-sm uppercase tracking-wider text-on-surface-variant">{stat.label}</p>
              </Spotlight>
            </Reveal>
          );
        })}
      </div>

      <Reveal delay={120}>
      <div className="grid grid-cols-1 gap-space-lg lg:grid-cols-3">
        {/* Rooms */}
        <div className="rounded-lg border border-surface-container-highest bg-surface-container/90 p-space-lg shadow-sm backdrop-blur-md lg:col-span-2">
          <div className="mb-space-lg flex items-center justify-between">
            <h2 className="flex items-center gap-space-sm font-headline text-headline-md text-on-surface">
              <DoorOpen className="h-5 w-5 text-primary" />
              Your Rooms
            </h2>
            <span className="font-code text-code-sm text-outline">{rooms.length} total</span>
          </div>
          {sortedRooms.length === 0 ? (
            <p className="font-code text-code-md text-outline">
              You&apos;re not in any rooms yet.{' '}
              <Link href="/dashboard?new=1" className="text-primary hover:underline">Create one →</Link>
            </p>
          ) : (
            <div className="space-y-space-md">
              {sortedRooms.map(room => {
                const me = room.members.find(m => m.user_id === user.id);
                return (
                  <Link
                    key={room.id}
                    href={`/room/${room.id}`}
                    className="group flex items-center justify-between gap-space-md rounded-lg border border-surface-container-highest bg-surface/80 p-space-md transition-all hover:translate-x-1 hover:border-primary/40"
                  >
                    <div className="min-w-0">
                      <div className="truncate font-headline text-headline-sm text-on-surface group-hover:text-primary">{room.title}</div>
                      <div className="truncate font-code text-code-sm text-outline">
                        {room.members.length} member{room.members.length === 1 ? '' : 's'} · active{' '}
                        {formatDistanceToNow(lastActivity(room), { addSuffix: true })}
                      </div>
                    </div>
                    <div className="flex flex-none items-center gap-space-sm">
                      {me && (
                        <>
                          <span className={`rounded px-space-sm py-0.5 font-code text-code-sm capitalize ${me.permission === 'owner' ? 'bg-primary/20 text-primary' : 'bg-surface-container-high text-on-surface-variant'}`}>
                            {me.permission}
                          </span>
                          <span className="rounded border border-outline-variant/40 px-space-sm py-0.5 font-code text-code-sm uppercase text-secondary">
                            {me.domain_role}
                          </span>
                        </>
                      )}
                      <ArrowRight className="h-4 w-4 text-outline transition-transform group-hover:translate-x-1 group-hover:text-primary" />
                    </div>
                  </Link>
                );
              })}
            </div>
          )}

          {collaborators.size > 0 && (
            <div className="mt-space-lg border-t border-surface-container-highest pt-space-lg">
              <div className="mb-space-sm font-code text-label-md uppercase tracking-wider text-outline">Frequent collaborators</div>
              <div className="flex flex-wrap gap-space-sm">
                {Array.from(collaborators.values()).map(c => (
                  <span key={c.id} className="flex items-center gap-space-sm rounded-full border border-surface-container-highest bg-surface/80 py-1 pl-1 pr-space-md">
                    <span className="grid h-6 w-6 place-items-center rounded-full font-code text-[11px] font-bold text-[#0d1117]" style={{ background: c.color }}>
                      {c.initials}
                    </span>
                    <span className="text-body-sm text-on-surface">{c.name}</span>
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="space-y-space-lg">
          {/* Plan */}
          <div className="rounded-lg border border-surface-container-highest bg-surface-container/90 p-space-lg shadow-sm backdrop-blur-md">
            <h2 className="mb-space-md flex items-center gap-space-sm font-headline text-headline-md text-on-surface">
              <Sparkles className="h-5 w-5 text-primary" />
              Plan
            </h2>
            <div className="mb-space-xs flex items-baseline justify-between">
              <span className="font-headline text-headline-sm text-on-surface">Free Developer</span>
              <span className="font-code text-code-sm text-outline">$0 / month</span>
            </div>
            <div className="mb-1 mt-space-md flex items-center justify-between text-body-sm text-on-surface-variant">
              <span>Rooms owned</span>
              <span className="font-code font-bold text-primary">{owned.length} / {FREE_ROOM_LIMIT}</span>
            </div>
            <div className="mb-space-lg h-1.5 w-full overflow-hidden rounded-full bg-surface-container-high">
              <div
                className={`h-full rounded-full transition-[width] duration-1000 ease-out ${roomUsage >= 100 ? 'bg-error-strong' : 'bg-gradient-to-r from-primary to-secondary'}`}
                style={{ width: barReady ? `${roomUsage}%` : '0%' }}
              />
            </div>
            <Link
              href="/pricing"
              className="block w-full rounded-lg bg-primary py-space-sm text-center text-label-md font-bold text-on-primary transition-colors hover:bg-primary/90"
            >
              Upgrade to Team Pro
            </Link>
          </div>

          {/* Preferences */}
          <div className="rounded-lg border border-surface-container-highest bg-surface-container/90 p-space-lg shadow-sm backdrop-blur-md">
            <div className="mb-space-md flex items-center justify-between">
              <h2 className="flex items-center gap-space-sm font-headline text-headline-md text-on-surface">
                <UserCircle className="h-5 w-5 text-primary" />
                Default role
              </h2>
              {savedRole && (
                <span className="flex items-center gap-1 font-code text-code-sm text-primary">
                  <Check className="h-3.5 w-3.5" /> Saved
                </span>
              )}
            </div>
            <p className="mb-space-md text-body-sm text-on-surface-variant">Used when you create a new room.</p>
            <div className="space-y-space-sm" role="radiogroup" aria-label="Default role">
              {ROLE_OPTIONS.map(opt => {
                const selected = defaultRole === opt.value;
                return (
                  <button
                    key={opt.value}
                    type="button"
                    role="radio"
                    aria-checked={selected}
                    onClick={() => handleRoleChange(opt.value)}
                    className={`flex w-full items-start gap-space-sm rounded-lg border p-space-sm text-left transition-colors ${
                      selected ? 'border-primary bg-primary/10' : 'border-surface-container-highest bg-surface/80 hover:border-outline'
                    }`}
                  >
                    <span className={`mt-0.5 grid h-3.5 w-3.5 flex-none place-items-center rounded-full border ${selected ? 'border-primary bg-primary' : 'border-outline'}`}>
                      {selected && <span className="h-1.5 w-1.5 rounded-full bg-white" />}
                    </span>
                    <span>
                      <span className="block text-body-md text-on-surface">{opt.label}</span>
                      <span className="block text-body-sm text-outline">{opt.detail}</span>
                    </span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Account */}
          <div className="rounded-lg border border-surface-container-highest bg-surface-container/90 p-space-lg shadow-sm backdrop-blur-md">
            <h2 className="mb-space-md font-headline text-headline-md text-on-surface">Account</h2>
            <div className="space-y-space-sm">
              <button
                type="button"
                onClick={handleConnectGitHub}
                disabled={connecting}
                className="flex w-full items-center justify-center gap-space-sm rounded-lg bg-surface-container-high py-space-sm text-label-md text-on-surface transition-colors hover:bg-surface-bright disabled:opacity-50"
              >
                <Github className="h-4 w-4" />
                {connecting
                  ? 'Connecting…'
                  : github?.connected
                    ? `GitHub connected${github.login ? ` as @${github.login}` : ''} · reconnect`
                    : 'Connect GitHub for export'}
              </button>
              {githubNote && <p className="text-body-sm text-error">{githubNote}</p>}
              <button
                type="button"
                onClick={handleSignOut}
                className="flex w-full items-center justify-center gap-space-sm rounded-lg border border-error-strong/40 py-space-sm text-label-md text-error transition-colors hover:bg-error-strong/10"
              >
                <LogOut className="h-4 w-4" />
                Sign out
              </button>
            </div>
          </div>
        </div>
      </div>
      </Reveal>
    </AppShell>
  );
}
