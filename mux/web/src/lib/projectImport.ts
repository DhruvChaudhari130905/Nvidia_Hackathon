// Importing a project from the user's computer: a folder (any browser), a .zip (e.g. a GitHub download)
// or files/folders dropped on the page. Dependencies, build output, VCS data and binaries are left out;
// the room holds source text only.

export interface ImportedFile {
  path: string;
  content: string;
}

export interface ImportResult {
  name: string; // project name (folder or zip name)
  files: ImportedFile[];
  skipped: { ignored: number; binary: number; tooLarge: number; overLimit: number; secrets: number };
}

const IGNORED_DIRS = new Set([
  'node_modules', '.git', '.svn', '.hg', 'dist', 'build', 'out', '.next', '.nuxt', '.svelte-kit', '.turbo', '.cache',
  '.parcel-cache', '.vercel', '.expo', 'coverage', '__pycache__', '.venv', 'venv', '.mypy_cache', '.pytest_cache',
  'target', 'bin', 'obj', '.gradle', '.idea', 'Pods', 'DerivedData', '__MACOSX',
]);
// .env files usually hold secrets and the room is shared, so only templates like .env.example come along
const SECRET_FILES = /^\.env(\..+)?$/;
const SECRET_TEMPLATES = /\.(example|sample|template|defaults?)$/i;
const IGNORED_FILES = /^(\.DS_Store|Thumbs\.db|desktop\.ini)$|\.log$/i;
const BINARY = /\.(png|jpe?g|gif|webp|avif|ico|bmp|tiff?|psd|woff2?|ttf|otf|eot|zip|gz|tgz|rar|7z|tar|pdf|mp[34]|wav|ogg|webm|mov|avi|sqlite3?|db|wasm|node|exe|dll|so|dylib|class|jar|pyc|o|a|lockb)$/i;

export const MAX_FILE_BYTES = 1_000_000;
export const MAX_FILES = 2000;
export const MAX_TOTAL_BYTES = 25_000_000;

function emptySkipped(): ImportResult['skipped'] {
  return { ignored: 0, binary: 0, tooLarge: 0, overLimit: 0, secrets: 0 };
}

function isIgnoredPath(path: string): boolean {
  const parts = path.split('/');
  return parts.slice(0, -1).some(p => IGNORED_DIRS.has(p)) || IGNORED_FILES.test(parts[parts.length - 1]);
}

// Text heuristic for files without a telling extension: NUL bytes mean binary
function looksBinary(bytes: Uint8Array): boolean {
  const n = Math.min(bytes.length, 8000);
  for (let i = 0; i < n; i++) if (bytes[i] === 0) return true;
  return false;
}

// If every path shares one top folder (my-app/…), drop it so the project lands at the room root
function stripCommonRoot(paths: string[]): { root: string | null; strip: (p: string) => string } {
  const first = paths[0]?.split('/')[0];
  const shared = first && paths.length > 0 && paths.every(p => p.includes('/') && p.split('/')[0] === first);
  return shared ? { root: first!, strip: p => p.slice(first!.length + 1) } : { root: null, strip: p => p };
}

type Source = { path: string; size: number; read: () => Promise<Uint8Array> };

async function collect(sources: Source[], fallbackName: string): Promise<ImportResult> {
  const skipped = emptySkipped();
  const { root, strip } = stripCommonRoot(sources.map(s => s.path));
  const files: ImportedFile[] = [];
  let total = 0;
  const decoder = new TextDecoder('utf-8', { fatal: false });

  // Decide what to keep from names and sizes alone, then read the kept files in parallel
  const keep: { path: string; source: Source }[] = [];
  for (const s of sources.sort((a, b) => a.path.localeCompare(b.path))) {
    const path = strip(s.path).replace(/^\/+/, '');
    if (!path) continue;
    if (isIgnoredPath(path)) { skipped.ignored++; continue; }
    const base = path.split('/').pop()!;
    if (SECRET_FILES.test(base) && !SECRET_TEMPLATES.test(base)) { skipped.secrets++; continue; }
    if (BINARY.test(path)) { skipped.binary++; continue; }
    if (s.size > MAX_FILE_BYTES) { skipped.tooLarge++; continue; }
    if (keep.length >= MAX_FILES || total + s.size > MAX_TOTAL_BYTES) { skipped.overLimit++; continue; }
    keep.push({ path, source: s });
    total += s.size;
  }

  const contents = new Array<string | null>(keep.length);
  let next = 0;
  const worker = async () => {
    while (next < keep.length) {
      const i = next++;
      const bytes = await keep[i].source.read();
      contents[i] = looksBinary(bytes) ? null : decoder.decode(bytes);
    }
  };
  await Promise.all(Array.from({ length: Math.min(16, keep.length) }, worker));
  keep.forEach(({ path }, i) => {
    const content = contents[i];
    if (content === null) skipped.binary++;
    else files.push({ path, content });
  });
  return { name: root ?? fallbackName, files, skipped };
}

// ───────────── Folder (input[webkitdirectory]) ─────────────

// Chromium's directory picker hands back a handle we walk ourselves, so node_modules/.git are skipped
// without being opened. The <input webkitdirectory> fallback makes the browser list every file first
// (it can take minutes on a project with node_modules installed).
interface DirHandle {
  kind: 'directory';
  name: string;
  values(): AsyncIterable<DirHandle | FileHandle>;
}
interface FileHandle {
  kind: 'file';
  name: string;
  getFile(): Promise<File>;
}

export function hasFolderPicker(): boolean {
  return typeof window !== 'undefined' && 'showDirectoryPicker' in window;
}

async function walkHandle(dir: DirHandle, prefix: string, out: Source[], counts: { ignoredDirs: number }) {
  const subdirs: Promise<void>[] = [];
  for await (const entry of dir.values()) {
    const path = prefix ? `${prefix}/${entry.name}` : entry.name;
    if (entry.kind === 'directory') {
      if (IGNORED_DIRS.has(entry.name)) counts.ignoredDirs++;
      else subdirs.push(walkHandle(entry, path, out, counts));
    } else {
      const handle = entry;
      const file = await handle.getFile();
      out.push({ path, size: file.size, read: async () => new Uint8Array(await file.arrayBuffer()) });
    }
  }
  await Promise.all(subdirs);
}

// Opens the OS folder picker and reads the project. Must be called from a click handler.
// Resolves null when the user cancels.
export async function importFolder(): Promise<ImportResult | null> {
  if (hasFolderPicker()) {
    let dir: DirHandle;
    try {
      dir = await (window as unknown as { showDirectoryPicker: (o: object) => Promise<DirHandle> }).showDirectoryPicker({ mode: 'read' });
    } catch (e) {
      if ((e as Error).name === 'AbortError') return null;
      throw e;
    }
    const sources: Source[] = [];
    const counts = { ignoredDirs: 0 };
    await walkHandle(dir, '', sources, counts);
    const result = await collect(sources, dir.name);
    // Paths have no shared root here (we walked from inside the folder), so keep the folder's own name
    result.name = dir.name;
    result.skipped.ignored += counts.ignoredDirs;
    return result;
  }
  const files = await pickFiles({ directory: true });
  return files ? importFromFileList(files) : null;
}

export function pickZip(): Promise<File[] | null> {
  return pickFiles({ accept: '.zip,application/zip' });
}

function pickFiles({ directory = false, accept }: { directory?: boolean; accept?: string }): Promise<File[] | null> {
  return new Promise(resolve => {
    const input = document.createElement('input');
    input.type = 'file';
    if (directory) input.setAttribute('webkitdirectory', '');
    else input.multiple = false;
    if (accept) input.accept = accept;
    input.style.display = 'none';
    document.body.appendChild(input); // Safari ignores pickers on detached inputs
    const done = (files: File[] | null) => { input.remove(); resolve(files); };
    input.onchange = () => done(input.files?.length ? Array.from(input.files) : null);
    input.oncancel = () => done(null);
    input.click();
  });
}

export function importFromFileList(files: File[]): Promise<ImportResult> {
  const sources: Source[] = files.map(f => ({
    path: (f as File & { webkitRelativePath?: string }).webkitRelativePath || f.name,
    size: f.size,
    read: async () => new Uint8Array(await f.arrayBuffer()),
  }));
  return collect(sources, 'project');
}

// ───────────── Drag and drop (folders included) ─────────────

async function walkEntry(entry: FileSystemEntry, out: Source[]) {
  if (entry.isFile) {
    const file = await new Promise<File>((res, rej) => (entry as FileSystemFileEntry).file(res, rej));
    out.push({ path: entry.fullPath.replace(/^\//, ''), size: file.size, read: async () => new Uint8Array(await file.arrayBuffer()) });
    return;
  }
  if (!entry.isDirectory || IGNORED_DIRS.has(entry.name)) return; // don't even walk node_modules
  const reader = (entry as FileSystemDirectoryEntry).createReader();
  // readEntries returns results in batches until it hands back an empty one
  for (;;) {
    const batch = await new Promise<FileSystemEntry[]>((res, rej) => reader.readEntries(res, rej));
    if (!batch.length) break;
    for (const e of batch) await walkEntry(e, out);
  }
}

// True when the drop contains a folder or a .zip, i.e. should be treated as a project import
export function isProjectDrop(items: DataTransferItemList): boolean {
  return Array.from(items).some(item => {
    const entry = item.webkitGetAsEntry();
    return entry?.isDirectory || /\.zip$/i.test(item.getAsFile()?.name ?? '');
  });
}

export async function importFromDrop(items: DataTransferItemList): Promise<ImportResult> {
  // Entries must be grabbed synchronously, before the drop event ends
  const entries = Array.from(items)
    .map(item => item.webkitGetAsEntry())
    .filter((e): e is FileSystemEntry => !!e);
  const zips = Array.from(items).map(i => i.getAsFile()).filter((f): f is File => !!f && /\.zip$/i.test(f.name));
  if (zips.length === 1 && entries.length === 1) return importFromZip(zips[0]);

  const sources: Source[] = [];
  for (const e of entries) await walkEntry(e, sources);
  return collect(sources, entries.length === 1 && entries[0].isDirectory ? entries[0].name : 'project');
}

// ───────────── Zip ─────────────

async function inflateRaw(data: Uint8Array): Promise<Uint8Array> {
  const stream = new Blob([data as BlobPart]).stream().pipeThrough(new DecompressionStream('deflate-raw'));
  return new Uint8Array(await new Response(stream).arrayBuffer());
}

export async function importFromZip(file: File): Promise<ImportResult> {
  const buf = new Uint8Array(await file.arrayBuffer());
  const view = new DataView(buf.buffer, buf.byteOffset, buf.byteLength);

  // End of central directory record: scan back from the end (it may be followed by a comment)
  let eocd = -1;
  for (let i = buf.length - 22; i >= Math.max(0, buf.length - 65_557); i--) {
    if (view.getUint32(i, true) === 0x06054b50) { eocd = i; break; }
  }
  if (eocd < 0) throw new Error('This file isn’t a valid .zip archive');
  const count = view.getUint16(eocd + 10, true);
  let p = view.getUint32(eocd + 16, true);
  if (count === 0xffff || p === 0xffffffff) throw new Error('ZIP64 archives aren’t supported; unzip it and import the folder instead');

  const utf8 = new TextDecoder();
  const sources: Source[] = [];
  for (let i = 0; i < count; i++) {
    if (view.getUint32(p, true) !== 0x02014b50) throw new Error('The .zip archive looks damaged');
    const flags = view.getUint16(p + 8, true);
    const method = view.getUint16(p + 10, true);
    const compressedSize = view.getUint32(p + 20, true);
    const size = view.getUint32(p + 24, true);
    const nameLen = view.getUint16(p + 28, true);
    const extraLen = view.getUint16(p + 30, true);
    const commentLen = view.getUint16(p + 32, true);
    const localOffset = view.getUint32(p + 42, true);
    const name = utf8.decode(buf.subarray(p + 46, p + 46 + nameLen));
    p += 46 + nameLen + extraLen + commentLen;

    if (name.endsWith('/')) continue; // folder entry
    if (flags & 0x1) throw new Error('Password-protected archives aren’t supported');
    sources.push({
      path: name.replace(/\\/g, '/'),
      size,
      read: async () => {
        const localNameLen = view.getUint16(localOffset + 26, true);
        const localExtraLen = view.getUint16(localOffset + 28, true);
        const start = localOffset + 30 + localNameLen + localExtraLen;
        const raw = buf.subarray(start, start + compressedSize);
        if (method === 0) return raw;
        if (method === 8) return inflateRaw(raw);
        throw new Error(`${name}: unsupported compression`);
      },
    });
  }
  return collect(sources, file.name.replace(/\.zip$/i, ''));
}

// ───────────── Hand-off from the dashboard to a new room ─────────────

// Client-side navigation keeps this module alive, so the dashboard can pick a project (which needs a
// click) and the room page can apply it once it has loaded.
const pending = new Map<string, ImportResult>();

export function stashImport(roomId: string, result: ImportResult) {
  pending.set(roomId, result);
}

export function takeStashedImport(roomId: string): ImportResult | null {
  const r = pending.get(roomId) ?? null;
  pending.delete(roomId);
  return r;
}

export function describeSkipped(s: ImportResult['skipped']): string {
  const parts = [
    s.secrets && `${s.secrets} .env file${s.secrets === 1 ? '' : 's'} (secrets)`,
    s.ignored && `${s.ignored} item${s.ignored === 1 ? '' : 's'} in node_modules/.git/build folders`,
    s.binary && `${s.binary} binary`,
    s.tooLarge && `${s.tooLarge} over 1 MB`,
    s.overLimit && `${s.overLimit} over the ${MAX_FILES}-file limit`,
  ].filter(Boolean);
  return parts.length ? `Skipped ${parts.join(', ')}` : '';
}
