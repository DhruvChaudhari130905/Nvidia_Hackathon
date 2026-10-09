// Hand a room's files to desktop VS Code: save them into a local folder (File System Access API,
// Chromium only) or download a .zip, and read edits made in VS Code back from that folder.
import { BINARY_ASSET, bytesToDataUrl, fileBytes, maxBytesFor } from './binaryFiles';

export type FileContents = Map<string, string>;

// Folders never copied back into the room
const SKIP_DIRS = new Set(['node_modules', '.git', 'dist', 'build', '.next', '.turbo', '.cache', 'coverage']);
const BINARY_EXT = /\.(png|jpe?g|gif|webp|ico|bmp|woff2?|ttf|otf|eot|zip|gz|tgz|pdf|mp[34]|wav|webm|mov|sqlite|db|lock)$/i;
export const EXTENSIONS_FILE = '.vscode/extensions.json';

export function projectSlug(title: string): string {
  return title.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '') || 'mux-room';
}

// ───────────── Recommended extensions ─────────────

// VS Code shows an "install recommended extensions" prompt when it opens a folder with this file
export function recommendedExtensions(files: FileContents): string[] {
  const recs = new Set<string>(['esbenp.prettier-vscode']);
  let deps: Record<string, string> = {};
  try {
    const pkg = JSON.parse(files.get('package.json') ?? '{}');
    deps = { ...pkg.dependencies, ...pkg.devDependencies };
  } catch {
    // no or invalid package.json
  }
  const has = (name: string) => Object.keys(deps).some(d => d === name || d.startsWith(`${name}/`));
  const anyFile = (re: RegExp) => Array.from(files.keys()).some(p => re.test(p));

  if (has('eslint') || anyFile(/(^|\/)(\.eslintrc[^/]*|eslint\.config\.[cm]?js)$/)) recs.add('dbaeumer.vscode-eslint');
  if (has('tailwindcss') || anyFile(/(^|\/)tailwind\.config\.[cm]?[jt]s$/)) recs.add('bradlc.vscode-tailwindcss');
  if (has('vitest')) recs.add('vitest.explorer');
  if (has('@playwright/test')) recs.add('ms-playwright.playwright');
  if (has('prisma') || has('@prisma/client')) recs.add('Prisma.prisma');
  if (has('vue')) recs.add('Vue.volar');
  if (has('svelte')) recs.add('svelte.svelte-vscode');
  if (has('astro')) recs.add('astro-build.astro-vscode');
  if (has('better-sqlite3') || has('sqlite3') || has('sql.js') || anyFile(/\.(sqlite|db)$/)) recs.add('qwtel.sqlite-viewer');
  if (anyFile(/\.py$/)) recs.add('ms-python.python');
  if (anyFile(/(^|\/)Dockerfile$/)) recs.add('ms-azuretools.vscode-docker');
  recs.add('usernamehw.errorlens');
  return Array.from(recs);
}

// The room's files plus an extensions.json (unless the room already has its own)
export function exportFiles(files: FileContents): FileContents {
  const out = new Map(files);
  if (!out.has(EXTENSIONS_FILE)) {
    out.set(EXTENSIONS_FILE, `${JSON.stringify({ recommendations: recommendedExtensions(files) }, null, 2)}\n`);
  }
  return out;
}

// ───────────── Zip (stored, no compression) ─────────────

const CRC_TABLE = (() => {
  const t = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    t[n] = c >>> 0;
  }
  return t;
})();

function crc32(bytes: Uint8Array): number {
  let c = 0xffffffff;
  for (let i = 0; i < bytes.length; i++) c = CRC_TABLE[(c ^ bytes[i]) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

export function zipFiles(files: FileContents, rootFolder: string): Blob {
  const enc = new TextEncoder();
  const parts: Uint8Array[] = [];
  const central: Uint8Array[] = [];
  let offset = 0;

  const now = new Date();
  const dosTime = (now.getHours() << 11) | (now.getMinutes() << 5) | (now.getSeconds() >> 1);
  const dosDate = ((now.getFullYear() - 1980) << 9) | ((now.getMonth() + 1) << 5) | now.getDate();

  for (const [path, content] of Array.from(files).sort(([a], [b]) => a.localeCompare(b))) {
    const name = enc.encode(`${rootFolder}/${path}`);
    const bytes = fileBytes(content);
    const data = typeof bytes === 'string' ? enc.encode(bytes) : bytes;
    const crc = crc32(data);

    const local = new DataView(new ArrayBuffer(30));
    local.setUint32(0, 0x04034b50, true);
    local.setUint16(4, 20, true);
    local.setUint16(6, 0x0800, true); // UTF-8 names
    local.setUint16(8, 0, true); // stored
    local.setUint16(10, dosTime, true);
    local.setUint16(12, dosDate, true);
    local.setUint32(14, crc, true);
    local.setUint32(18, data.length, true);
    local.setUint32(22, data.length, true);
    local.setUint16(26, name.length, true);
    parts.push(new Uint8Array(local.buffer), name, data);

    const cen = new DataView(new ArrayBuffer(46));
    cen.setUint32(0, 0x02014b50, true);
    cen.setUint16(4, 20, true);
    cen.setUint16(6, 20, true);
    cen.setUint16(8, 0x0800, true);
    cen.setUint16(10, 0, true);
    cen.setUint16(12, dosTime, true);
    cen.setUint16(14, dosDate, true);
    cen.setUint32(16, crc, true);
    cen.setUint32(20, data.length, true);
    cen.setUint32(24, data.length, true);
    cen.setUint16(28, name.length, true);
    cen.setUint32(42, offset, true);
    central.push(new Uint8Array(cen.buffer), name);

    offset += 30 + name.length + data.length;
  }

  const centralSize = central.reduce((n, p) => n + p.length, 0);
  const end = new DataView(new ArrayBuffer(22));
  end.setUint32(0, 0x06054b50, true);
  end.setUint16(8, files.size, true);
  end.setUint16(10, files.size, true);
  end.setUint32(12, centralSize, true);
  end.setUint32(16, offset, true);

  return new Blob([...parts, ...central, new Uint8Array(end.buffer)] as BlobPart[], { type: 'application/zip' });
}

export function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// ───────────── Local folder (File System Access API) ─────────────

// Minimal typings; lib.dom doesn't ship the directory picker or async iteration yet
interface DirHandle {
  name: string;
  kind: 'directory';
  getDirectoryHandle(name: string, opts?: { create?: boolean }): Promise<DirHandle>;
  getFileHandle(name: string, opts?: { create?: boolean }): Promise<FileHandle>;
  values(): AsyncIterable<DirHandle | FileHandle>;
  queryPermission?(opts: { mode: 'readwrite' }): Promise<PermissionState>;
  requestPermission?(opts: { mode: 'readwrite' }): Promise<PermissionState>;
}
interface FileHandle {
  name: string;
  kind: 'file';
  getFile(): Promise<File>;
  createWritable(): Promise<{ write(data: string | Uint8Array): Promise<void>; close(): Promise<void> }>;
}

export function canUseFolders(): boolean {
  return typeof window !== 'undefined' && 'showDirectoryPicker' in window;
}

// Chosen folder per room, kept for this tab so "Bring changes back" can read it again
const folders = new Map<string, DirHandle>();

export function linkedFolderName(roomId: string): string | null {
  return folders.get(roomId)?.name ?? null;
}

async function ensurePermission(dir: DirHandle): Promise<boolean> {
  if (!dir.queryPermission || !dir.requestPermission) return true;
  if ((await dir.queryPermission({ mode: 'readwrite' })) === 'granted') return true;
  return (await dir.requestPermission({ mode: 'readwrite' })) === 'granted';
}

// Asks for a folder (or reuses the linked one) and writes every file into it. Returns the folder name.
export async function saveToFolder(roomId: string, files: FileContents, pickNew = false): Promise<string> {
  let dir = pickNew ? undefined : folders.get(roomId);
  if (!dir) {
    const picker = (window as unknown as { showDirectoryPicker: (o: object) => Promise<DirHandle> }).showDirectoryPicker;
    dir = await picker({ id: `mux-${roomId}`, mode: 'readwrite' });
    folders.set(roomId, dir);
  }
  if (!(await ensurePermission(dir))) throw new Error('Permission to write to the folder was denied');

  for (const [path, content] of Array.from(files)) {
    const parts = path.split('/');
    let d = dir;
    for (const part of parts.slice(0, -1)) d = await d.getDirectoryHandle(part, { create: true });
    const w = await (await d.getFileHandle(parts[parts.length - 1], { create: true })).createWritable();
    await w.write(fileBytes(content));
    await w.close();
  }
  return dir.name;
}

// Reads text files back from the linked folder, skipping dependencies, build output and binaries
export async function readFolder(roomId: string): Promise<{ files: FileContents; skipped: number }> {
  const dir = folders.get(roomId);
  if (!dir) throw new Error('No folder linked yet: save the room to a folder first');
  if (!(await ensurePermission(dir))) throw new Error('Permission to read the folder was denied');

  const files: FileContents = new Map();
  let skipped = 0;
  const walk = async (d: DirHandle, prefix: string) => {
    for await (const entry of d.values()) {
      const path = prefix ? `${prefix}/${entry.name}` : entry.name;
      if (entry.kind === 'directory') {
        if (!SKIP_DIRS.has(entry.name)) await walk(entry, path);
        continue;
      }
      if (entry.name === '.DS_Store') continue;
      const file = await entry.getFile();
      if ((BINARY_EXT.test(entry.name) && !BINARY_ASSET.test(entry.name)) || file.size > maxBytesFor(entry.name)) {
        skipped++;
        continue;
      }
      files.set(path, BINARY_ASSET.test(entry.name) ? bytesToDataUrl(new Uint8Array(await file.arrayBuffer()), path) : await file.text());
    }
  };
  await walk(dir, '');
  return { files, skipped };
}

// What changed in the folder compared with the room
export function diffFolder(room: FileContents, folder: FileContents) {
  const changed: string[] = [];
  const added: string[] = [];
  folder.forEach((content, path) => {
    if (!room.has(path)) {
      // Our generated extensions.json isn't part of the room unless the user edited it there
      if (path !== EXTENSIONS_FILE) added.push(path);
    } else if (room.get(path) !== content) changed.push(path);
  });
  const missing = Array.from(room.keys()).filter(p => !folder.has(p));
  return { changed: changed.sort(), added: added.sort(), missing: missing.sort() };
}
