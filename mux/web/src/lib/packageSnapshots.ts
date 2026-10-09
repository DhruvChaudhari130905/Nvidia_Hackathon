// Installed npm packages saved in the browser (IndexedDB), so a room's preview installs once and later
// visits, reloads included, restore the packages instead of running npm install again.
// A snapshot is keyed by its package.json: rooms with the same dependencies share one. Only this browser
// sees them; the server never does.

const DB_NAME = 'mux-packages';
const DATA = 'snapshots'; // key -> node_modules as a WebContainer binary snapshot
const META = 'meta'; // key -> SnapshotMeta
const MAX_SNAPSHOTS = 5;
const MAX_TOTAL_BYTES = 1_500_000_000;

export interface PackageSnapshot {
  data: Uint8Array;
  lockfile: string | null; // package-lock.json from the same install
}

interface SnapshotMeta {
  key: string;
  size: number;
  lastUsed: number;
  lockfile: string | null;
  rooms: string[]; // rooms using it; the snapshot goes when the last one is deleted
}

function open(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => {
      req.result.createObjectStore(DATA);
      req.result.createObjectStore(META);
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

function done(tx: IDBTransaction): Promise<void> {
  return new Promise((resolve, reject) => {
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
    tx.onabort = () => reject(tx.error);
  });
}

function request<T>(req: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

// The key for a set of dependencies: a hash of the exact package.json
export async function snapshotKey(packageJson: string): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(packageJson));
  return Array.from(new Uint8Array(digest), b => b.toString(16).padStart(2, '0')).join('');
}

export async function loadSnapshot(key: string, roomId: string): Promise<PackageSnapshot | null> {
  try {
    const db = await open();
    const tx = db.transaction([DATA, META], 'readwrite');
    const meta = await request<SnapshotMeta | undefined>(tx.objectStore(META).get(key));
    const data = await request<Uint8Array | undefined>(tx.objectStore(DATA).get(key));
    if (!meta || !data) return null;
    tx.objectStore(META).put({ ...meta, lastUsed: Date.now(), rooms: Array.from(new Set([...meta.rooms, roomId])) }, key);
    await done(tx);
    return { data, lockfile: meta.lockfile };
  } catch {
    return null; // storage blocked or cleared: the room just installs
  }
}

export async function saveSnapshot(key: string, roomId: string, snapshot: PackageSnapshot): Promise<void> {
  const db = await open();
  const tx = db.transaction([DATA, META], 'readwrite');
  const old = await request<SnapshotMeta | undefined>(tx.objectStore(META).get(key));
  tx.objectStore(DATA).put(snapshot.data, key);
  tx.objectStore(META).put({
    key, size: snapshot.data.byteLength, lastUsed: Date.now(), lockfile: snapshot.lockfile,
    rooms: Array.from(new Set([...(old?.rooms ?? []), roomId])),
  } satisfies SnapshotMeta, key);
  await done(tx);
  await evict(db);
}

// Keeps the most recently used snapshots within the count and size caps (the newest always stays)
async function evict(db: IDBDatabase) {
  const tx = db.transaction([DATA, META], 'readwrite');
  const metas = (await request<SnapshotMeta[]>(tx.objectStore(META).getAll())).sort((a, b) => b.lastUsed - a.lastUsed);
  let total = 0;
  metas.forEach((m, i) => {
    total += m.size;
    if (i > 0 && (i >= MAX_SNAPSHOTS || total > MAX_TOTAL_BYTES)) {
      tx.objectStore(DATA).delete(m.key);
      tx.objectStore(META).delete(m.key);
    }
  });
  await done(tx);
}

// A snapshot that may be broken (the app crashed after using it) is not used again
export async function dropSnapshot(key: string): Promise<void> {
  try {
    const db = await open();
    const tx = db.transaction([DATA, META], 'readwrite');
    tx.objectStore(DATA).delete(key);
    tx.objectStore(META).delete(key);
    await done(tx);
  } catch {
    // nothing stored
  }
}

// A deleted room stops holding its snapshots; one no other room uses is removed
export async function forgetRoomSnapshots(roomId: string): Promise<void> {
  try {
    const db = await open();
    const tx = db.transaction([DATA, META], 'readwrite');
    for (const meta of await request<SnapshotMeta[]>(tx.objectStore(META).getAll())) {
      if (!meta.rooms.includes(roomId)) continue;
      const rooms = meta.rooms.filter(r => r !== roomId);
      if (rooms.length) tx.objectStore(META).put({ ...meta, rooms }, meta.key);
      else {
        tx.objectStore(DATA).delete(meta.key);
        tx.objectStore(META).delete(meta.key);
      }
    }
    await done(tx);
  } catch {
    // nothing stored
  }
}
