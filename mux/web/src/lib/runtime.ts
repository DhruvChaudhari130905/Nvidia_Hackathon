// Keeps the room's files and the in-browser WebContainer in step, so a real shell (jsh, npm, node, npx)
// can run against them. Room edits are written into the container; files that shell commands create,
// change or delete are sent back to the room. Dependencies and build output stay in the container.
import type { WebContainer } from '@webcontainer/api';
import { initWebContainer } from './webcontainer';
import { notify } from './notifications';

export interface RoomFs {
  files: Map<string, { content: string }>;
  write: (path: string, content: string) => void | Promise<void>;
  remove: (paths: string[]) => void;
}

// Never synced back into the room
const IGNORED_DIRS = new Set(['node_modules', '.git', 'dist', 'build', '.next', '.cache', '.npm', '.vite', 'coverage', '.turbo']);
const BINARY = /\.(png|jpe?g|gif|webp|ico|bmp|woff2?|ttf|otf|eot|zip|gz|tgz|pdf|mp[34]|wav|webm|mov|sqlite3?|db|wasm|node)$/i;
const MAX_BYTES = 1_000_000;

export function webContainersSupported(): { ok: true } | { ok: false; reason: string } {
  if (typeof window === 'undefined') return { ok: false, reason: 'Not in a browser' };
  if (!window.crossOriginIsolated) return { ok: false, reason: 'This page isn’t cross-origin isolated (COOP/COEP headers missing)' };
  if (typeof SharedArrayBuffer === 'undefined') return { ok: false, reason: 'This browser has no SharedArrayBuffer support' };
  return { ok: true };
}

function ignored(path: string): boolean {
  const parts = path.split('/');
  if (parts.some(p => IGNORED_DIRS.has(p))) return true;
  const name = parts[parts.length - 1];
  return BINARY.test(name) || name === '.DS_Store' || name.endsWith('.log');
}

// ───────────── State shared by every terminal on the page ─────────────

let mountedRoom: string | null = null;
let synced = new Map<string, string>(); // what the container holds for each room-tracked file
let roomFs: RoomFs | null = null;
let watcherStarted = false;
let pushChain: Promise<void> = Promise.resolve();
const serverListeners = new Set<(port: number, url: string) => void>();
const openServers = new Map<number, string>();

async function container(): Promise<WebContainer> {
  const wc = (await initWebContainer()) as WebContainer | null;
  if (!wc) throw new Error('WebContainers only run in the browser');
  return wc;
}

async function ensureDir(wc: WebContainer, path: string) {
  const dir = path.split('/').slice(0, -1).join('/');
  if (dir) await wc.fs.mkdir(dir, { recursive: true });
}

// Boots the container (once) and makes it hold exactly this room's files
export async function attachRoom(roomId: string, fs: RoomFs): Promise<WebContainer> {
  const wc = await container();
  roomFs = fs;
  if (mountedRoom !== roomId) {
    // Another room was mounted earlier in this tab: start from an empty project
    if (mountedRoom !== null) {
      for (const entry of await wc.fs.readdir('.')) await wc.fs.rm(entry, { recursive: true, force: true });
    }
    mountedRoom = roomId;
    synced = new Map();
    dirWatchers.forEach(w => w.close());
    dirWatchers.clear();
    openServers.clear();
  }
  startWatcher(wc);
  startServerEvents(wc);
  await pushRoomFiles(fs.files);
  await watchTopLevelDirs(wc);
  return wc;
}

export function updateRoomFs(fs: RoomFs) {
  roomFs = fs;
}

// Room → container: write what changed since the last sync, delete what the room no longer has
export function pushRoomFiles(files: Map<string, { content: string }>): Promise<void> {
  pushChain = pushChain.then(async () => {
    if (!mountedRoom) return;
    const wc = await container();
    for (const [path, { content }] of Array.from(files)) {
      if (synced.get(path) === content) continue;
      synced.set(path, content);
      await ensureDir(wc, path);
      await wc.fs.writeFile(path, content);
    }
    for (const path of Array.from(synced.keys())) {
      if (files.has(path)) continue;
      synced.delete(path);
      await wc.fs.rm(path, { force: true });
    }
  }).catch(err => console.warn('WebContainer sync failed:', err));
  return pushChain;
}

// Writes straight into the container; the watcher then copies the file into the room like any shell edit
export async function writeContainerFile(path: string, content: string): Promise<void> {
  const wc = await container();
  await ensureDir(wc, path);
  await wc.fs.writeFile(path, content);
}

// ───────────── Container → room ─────────────

let pending = new Set<string>();
let flushTimer: ReturnType<typeof setTimeout> | null = null;

// Watching the project root recursively would stream an event for every file npm writes into
// node_modules, so the root is watched shallowly and each top-level folder (except ignored ones) recursively.
const dirWatchers = new Map<string, { close(): void }>();

function queue(wc: WebContainer, path: string) {
  if (!path || ignored(path)) return;
  pending.add(path);
  if (flushTimer) clearTimeout(flushTimer);
  flushTimer = setTimeout(() => void flush(wc), 150);
}

const decode = (name: string | Uint8Array) => (typeof name === 'string' ? name : new TextDecoder().decode(name)).replace(/^\.?\//, '');

function watchDir(wc: WebContainer, dir: string) {
  if (dirWatchers.has(dir) || IGNORED_DIRS.has(dir)) return;
  try {
    dirWatchers.set(dir, wc.fs.watch(dir, { recursive: true }, (_event, filename) => queue(wc, `${dir}/${decode(filename)}`)));
  } catch {
    // folder vanished before we could watch it
  }
}

async function watchTopLevelDirs(wc: WebContainer) {
  for (const entry of await wc.fs.readdir('.', { withFileTypes: true })) {
    if (entry.isDirectory()) watchDir(wc, entry.name);
  }
}

function startWatcher(wc: WebContainer) {
  if (watcherStarted) return;
  watcherStarted = true;
  wc.fs.watch('.', (_event, filename) => {
    const name = decode(filename);
    if (!name || IGNORED_DIRS.has(name)) return;
    queue(wc, name);
    // A new top-level folder needs its own watcher; a removed one drops it
    void wc.fs.readdir(name).then(
      () => watchDir(wc, name),
      () => { dirWatchers.get(name)?.close(); dirWatchers.delete(name); },
    );
  });
  void watchTopLevelDirs(wc);
}

async function readText(wc: WebContainer, path: string): Promise<{ kind: 'file'; content: string } | { kind: 'dir' } | { kind: 'missing' } | { kind: 'skip' }> {
  try {
    const bytes = await wc.fs.readFile(path);
    if (bytes.length > MAX_BYTES) return { kind: 'skip' };
    return { kind: 'file', content: new TextDecoder().decode(bytes) };
  } catch (err) {
    const msg = String((err as Error)?.message ?? err);
    if (/EISDIR|illegal operation on a directory/i.test(msg)) return { kind: 'dir' };
    if (/ENOENT|no such file/i.test(msg)) return { kind: 'missing' };
    return { kind: 'skip' };
  }
}

async function listFiles(wc: WebContainer, dir: string, out: string[] = [], depth = 0): Promise<string[]> {
  if (depth > 12 || out.length > 2000) return out;
  for (const entry of await wc.fs.readdir(dir, { withFileTypes: true })) {
    const path = `${dir}/${entry.name}`;
    if (ignored(path)) continue;
    if (entry.isDirectory()) await listFiles(wc, path, out, depth + 1);
    else if (entry.isFile()) out.push(path);
  }
  return out;
}

async function flush(wc: WebContainer) {
  const paths = Array.from(pending);
  pending = new Set();
  const fs = roomFs;
  if (!fs || !mountedRoom) return;

  const removed: string[] = [];
  const check = async (path: string) => {
    const r = await readText(wc, path);
    if (r.kind === 'file') {
      // package-lock.json is big and noisy; only sync it if the room already tracks one
      if (path === 'package-lock.json' && !synced.has(path)) return;
      if (synced.get(path) === r.content) return;
      synced.set(path, r.content);
      await fs.write(path, r.content);
    } else if (r.kind === 'dir') {
      // A folder appeared (mkdir, mv, git clone…): sync whatever files it holds
      for (const f of await listFiles(wc, path)) await check(f);
    } else if (r.kind === 'missing') {
      // The path, or a folder containing tracked files, was deleted
      for (const p of Array.from(synced.keys())) {
        if (p === path || p.startsWith(`${path}/`)) {
          synced.delete(p);
          removed.push(p);
        }
      }
    }
  };
  for (const p of paths) await check(p);
  if (removed.length) fs.remove(removed);
}

// ───────────── Dev servers ─────────────

let serverEventsStarted = false;

function startServerEvents(wc: WebContainer) {
  if (serverEventsStarted) return;
  serverEventsStarted = true;
  wc.on('server-ready', (port, url) => {
    openServers.set(port, url);
    notify({ category: 'terminal', tone: 'ok', title: `Dev server ready on port ${port}`, body: url, onClick: () => window.open(url, '_blank', 'noopener') });
    serverListeners.forEach(l => l(port, url));
  });
  wc.on('port', (port, type) => {
    if (type === 'close') openServers.delete(port);
  });
}

export function onServerReady(listener: (port: number, url: string) => void): () => void {
  serverListeners.add(listener);
  return () => serverListeners.delete(listener);
}

export function runningServers(): [number, string][] {
  return Array.from(openServers);
}
