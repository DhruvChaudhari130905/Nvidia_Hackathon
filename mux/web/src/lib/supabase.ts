// Supabase client for auth only
import { createClient } from '@supabase/supabase-js';
import { DEMO_AUTH_USER, isDemoMode, setDemoMode } from './demo';

// Placeholders keep the build and dev server working before .env.local is filled in; auth calls fail until it is.
const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL || 'http://localhost:54321';
// .env.example names the newer publishable key; older setups use the anon key. Either works.
const configuredKey = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY || process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
const supabaseAnonKey = configuredKey || 'placeholder-anon-key';

export const isSupabaseConfigured = Boolean(process.env.NEXT_PUBLIC_SUPABASE_URL && configuredKey);

if (!isSupabaseConfigured) {
  console.warn('NEXT_PUBLIC_SUPABASE_URL / NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY are not set; copy .env.example to .env.local.');
}

export const supabase = createClient(supabaseUrl, supabaseAnonKey, {
  auth: {
    persistSession: true,
    autoRefreshToken: true,
    detectSessionInUrl: true,
  },
});

// Only same-site paths are allowed as post-login destinations
export function safeNext(next: string | null | undefined, fallback = '/dashboard'): string {
  return next && next.startsWith('/') && !next.startsWith('//') ? next : fallback;
}

// Login URL that returns the user to the current page afterwards
export function loginHref(): string {
  if (typeof window === 'undefined') return '/login';
  return `/login?next=${encodeURIComponent(window.location.pathname + window.location.search)}`;
}

export async function signInWithProvider(provider: 'google' | 'github', next = '/dashboard') {
  const { data, error } = await supabase.auth.signInWithOAuth({
    provider,
    options: {
      redirectTo: `${window.location.origin}/auth/callback?next=${encodeURIComponent(safeNext(next))}`,
      // Ask which account to use instead of silently reusing the one the browser is signed in to
      queryParams: { prompt: 'select_account' },
    },
  });
  if (error) throw error;
  return data;
}

export async function signInWithEmail(email: string, password: string) {
  const { data, error } = await supabase.auth.signInWithPassword({ email, password });
  if (error) throw error;
  return data;
}

// Returns needsConfirmation when the project asks new users to confirm their email first
export async function signUpWithEmail(email: string, password: string, name: string, next = '/dashboard') {
  const { data, error } = await supabase.auth.signUp({
    email,
    password,
    options: {
      data: name ? { full_name: name } : undefined,
      emailRedirectTo: `${window.location.origin}/auth/callback?next=${encodeURIComponent(safeNext(next))}`,
    },
  });
  if (error) throw error;
  return { needsConfirmation: !data.session };
}

export async function signOut() {
  if (isDemoMode()) {
    setDemoMode(false);
    return;
  }
  const { error } = await supabase.auth.signOut();
  if (error) throw error;
}

export async function getSession() {
  if (isDemoMode()) return { access_token: 'demo', user: DEMO_AUTH_USER };
  const { data: { session } } = await supabase.auth.getSession();
  return session;
}

export async function getUser() {
  if (isDemoMode()) return DEMO_AUTH_USER;
  const { data: { user } } = await supabase.auth.getUser();
  return user;
}

export function onAuthStateChange(callback: (event: string, session: any) => void) {
  return supabase.auth.onAuthStateChange(callback);
}

// Store token for API calls
export async function getAccessToken(): Promise<string | null> {
  const { data: { session } } = await supabase.auth.getSession();
  return session?.access_token || null;
}