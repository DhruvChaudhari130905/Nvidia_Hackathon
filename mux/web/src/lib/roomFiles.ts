// Per-room file storage in the browser (IndexedDB), so each room keeps its own files across reloads.
// Stands in for the backend files API, which isn't implemented yet; only this browser sees these files.

const DB_NAME = 'mux';
const STORE = 'room-files';

// One connection for the page, opened on first use
let dbPromise: Promise<IDBDatabase> | null = null;

function open(): Promise<IDBDatabase> {
  if (!dbPromise) {
    dbPromise = new Promise<IDBDatabase>((resolve, reject) => {
      const req = indexedDB.open(DB_NAME, 1);
      req.onupgradeneeded = () => req.result.createObjectStore(STORE);
      req.onsuccess = () => {
        const db = req.result;
        // Another tab upgrading the database needs this one closed; reopen on next use
        db.onversionchange = () => {
          db.close();
          dbPromise = null;
        };
        db.onclose = () => { dbPromise = null; };
        resolve(db);
      };
      req.onerror = () => reject(req.error);
    }).catch(err => {
      dbPromise = null;
      throw err;
    });
  }
  return dbPromise;
}

// Resolves once the transaction commits (not just when the request succeeds), so a write is really stored
async function tx<T>(mode: IDBTransactionMode, fn: (store: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  const db = await open();
  return new Promise((resolve, reject) => {
    const transaction = db.transaction(STORE, mode);
    const req = fn(transaction.objectStore(STORE));
    transaction.oncomplete = () => resolve(req.result);
    transaction.onerror = () => reject(transaction.error ?? req.error);
    transaction.onabort = () => reject(transaction.error ?? new Error('IndexedDB transaction aborted'));
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
