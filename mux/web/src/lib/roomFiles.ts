// Per-room file storage in the browser (IndexedDB), so each room keeps its own files across reloads.
// Stands in for the backend files API, which isn't implemented yet; only this browser sees these files.

const DB_NAME = 'mux';
const STORE = 'room-files';

function open(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => req.result.createObjectStore(STORE);
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function tx<T>(mode: IDBTransactionMode, fn: (store: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  const db = await open();
  return new Promise((resolve, reject) => {
    const req = fn(db.transaction(STORE, mode).objectStore(STORE));
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

// null when this room has never saved files in this browser
export async function loadRoomFiles(roomId: string): Promise<Map<string, { content: string }> | null> {
  try {
    const saved = await tx<Record<string, string> | undefined>('readonly', s => s.get(roomId));
    return saved ? new Map(Object.entries(saved).map(([p, content]) => [p, { content }])) : null;
  } catch {
    return null; // storage blocked (private window, etc.)
  }
}

export async function saveRoomFiles(roomId: string, files: Map<string, { content: string }>): Promise<void> {
  try {
    await tx('readwrite', s => s.put(Object.fromEntries(Array.from(files, ([p, f]) => [p, f.content])), roomId));
  } catch {
    // storage full or blocked; the room still works for this session
  }
}

export async function deleteRoomFiles(roomId: string): Promise<void> {
  try {
    await tx('readwrite', s => s.delete(roomId));
  } catch {
    // storage blocked; nothing was saved for this room anyway
  }
}
