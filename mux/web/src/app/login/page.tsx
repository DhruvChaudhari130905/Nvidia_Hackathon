'use client';

import React, { useEffect, useState } from 'react';
import { Github, Chrome, PlayCircle, Terminal } from 'lucide-react';
import { getSession, signInWithProvider, isSupabaseConfigured, safeNext } from '@/lib/supabase';
import { setDemoMode } from '@/lib/demo';
import { onAuthStateChange } from '@/lib/supabase';
import { useRouter } from 'next/navigation';
import { ShaderBackground, SiteFooter, SiteHeader } from '@/components/shell';

// Sign-in screen, built in the stitch Developer Workspace style (no stitch screen exists for it)

export default function LoginPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  // Set by /auth/callback when the sign-in didn't complete
  const [authError, setAuthError] = useState<string | null>(null);
  // Where to go after signing in (e.g. the room or template the user was opening)
  const nextPath = () => safeNext(new URLSearchParams(window.location.search).get('next'));

  useEffect(() => {
    setAuthError(new URLSearchParams(window.location.search).get('error'));
    const { data: { subscription } } = onAuthStateChange((event, session) => {
      if (session) {
        router.push(nextPath());
      }
    });

    // Check for existing session
    getSession().then((session) => {
      if (session) {
        router.push(nextPath());
      } else {
        setLoading(false);
      }
    });

    return () => subscription.unsubscribe();
  }, [router]);

  const handleSignIn = async (provider: 'google' | 'github') => {
    // Without real Supabase settings the OAuth redirect points at a placeholder host that doesn't exist
    if (!isSupabaseConfigured) return;
    setLoading(true);
    try {
      await signInWithProvider(provider, nextPath());
    } catch (error) {
      console.error('Sign in error:', error);
      setLoading(false);
      alert('Failed to sign in. Please try again.');
    }
  };

  const handleDemo = () => {
    setDemoMode(true);
    router.push(nextPath());
  };

  const providerButton =
    'flex w-full items-center justify-center gap-space-sm rounded-lg border border-outline-variant/40 bg-surface-container-high px-space-md py-space-md text-label-md font-medium text-on-surface transition-all hover:border-primary/50 hover:bg-surface-bright disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:border-outline-variant/40 disabled:hover:bg-surface-container-high';

  return (
    <div className="relative flex min-h-screen flex-col bg-surface font-ui text-body-md text-on-surface">
      <ShaderBackground interactive className="fixed inset-0 z-0 opacity-60" />
      <div className="pointer-events-none fixed inset-0 z-0 bg-gradient-to-b from-primary/10 via-transparent to-transparent" />
      <div className="float-slow pointer-events-none fixed left-[10%] top-1/4 z-0 h-72 w-72 rounded-full bg-primary/10 blur-3xl" />
      <div className="float-slower pointer-events-none fixed bottom-1/4 right-[10%] z-0 h-80 w-80 rounded-full bg-secondary/10 blur-3xl" />

      <SiteHeader />

      <main className="relative z-10 flex flex-1 items-center justify-center px-gutter pb-space-xl pt-24">
        {loading ? (
          <div className="h-8 w-8 animate-spin rounded-full border-b-2 border-primary" />
        ) : (
          <div className="relative w-full max-w-md overflow-hidden rounded-2xl border border-outline-variant/40 bg-surface-container/90 p-space-xl shadow-2xl backdrop-blur-xl animate-fade-up">
            <div className="float-slow pointer-events-none absolute -bottom-24 -right-24 h-64 w-64 rounded-full bg-primary/10 blur-3xl" />

            <div className="relative mb-space-xl text-center">
              <div className="mb-space-md inline-flex items-center gap-space-sm rounded-full border border-outline-variant/30 bg-surface-container-high px-space-md py-space-xs text-body-sm text-on-surface-variant">
                <span className="flex h-2 w-2 rounded-full bg-primary animate-pulse" />
                <span className="font-code text-code-sm text-primary">Multiplayer rooms</span>
              </div>
              <h1 className="mb-space-sm font-headline text-headline-lg font-bold">
                Welcome to <span className="text-shimmer">MUX</span>
              </h1>
              <p className="text-body-md text-on-surface-variant">Eight people steering, one agent building</p>
            </div>

            {authError && (
              <div role="alert" className="relative mb-space-md rounded-lg border border-error/40 bg-error/10 p-space-md text-body-sm text-on-surface">
                Sign-in didn&apos;t complete: {authError}
              </div>
            )}

            {!isSupabaseConfigured && (
              <div className="relative mb-space-md rounded-lg border border-outline-variant/40 bg-surface-container-lowest p-space-md text-body-sm text-on-surface-variant">
                Sign-in isn&apos;t configured, but you can try the demo below. To enable sign-in, copy{' '}
                <code className="font-code text-secondary">.env.example</code> to <code className="font-code text-secondary">.env.local</code>, set{' '}
                <code className="font-code text-secondary">NEXT_PUBLIC_SUPABASE_URL</code> and{' '}
                <code className="font-code text-secondary">NEXT_PUBLIC_SUPABASE_ANON_KEY</code>, then restart the dev server.
              </div>
            )}

            <div className="relative space-y-space-sm">
              <button
                className={providerButton}
                onClick={() => handleSignIn('google')}
                disabled={loading || !isSupabaseConfigured}
                type="button"
              >
                <Chrome className="h-5 w-5" />
                Continue with Google
              </button>

              <button
                className={providerButton}
                onClick={() => handleSignIn('github')}
                disabled={loading || !isSupabaseConfigured}
                type="button"
              >
                <Github className="h-5 w-5" />
                Continue with GitHub
              </button>

              <div className="flex items-center gap-space-sm py-space-xs font-code text-code-sm text-outline">
                <span className="h-px flex-1 bg-outline-variant/40" />
                or
                <span className="h-px flex-1 bg-outline-variant/40" />
              </div>

              <button
                className="btn-shine flex w-full items-center justify-center gap-space-sm rounded-lg bg-primary px-space-md py-space-md text-label-md font-bold text-on-primary shadow-lg shadow-primary/20 transition-all hover:-translate-y-0.5 hover:bg-primary/90 hover:shadow-[0_0_25px_rgba(59,130,246,0.6)]"
                onClick={handleDemo}
                type="button"
              >
                <PlayCircle className="h-5 w-5" />
                Try the demo (sample data, no sign-in)
              </button>
            </div>

            <div className="relative mt-space-lg flex items-center justify-center gap-space-xs font-code text-code-sm text-outline">
              <Terminal className="h-3.5 w-3.5" />
              Free tier includes 3 active rooms
            </div>

            <p className="relative mt-space-md text-center text-body-sm text-on-surface-variant">
              By continuing, you agree to our Terms of Service and Privacy Policy.
            </p>
          </div>
        )}
      </main>

      <SiteFooter />
    </div>
  );
}
