// SQLite via sql.js (WebAssembly), so it runs anywhere Node does, including the browser sandbox.
// The database lives in memory and is saved to DB_FILE (app.db) after every write; ':memory:' never saves.
import fs from 'node:fs'
import initSqlJs, { type SqlValue } from 'sql.js'

const FILE = process.env.DB_FILE || 'app.db'
const persist = FILE !== ':memory:'
const SQL = await initSqlJs()
const db = persist && fs.existsSync(FILE) ? new SQL.Database(fs.readFileSync(FILE)) : new SQL.Database()

db.run(`
  CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
  )
`)

const save = () => {
  if (persist) fs.writeFileSync(FILE, db.export())
}

// Rows as plain objects
export function all<T = Record<string, unknown>>(sql: string, params: SqlValue[] = []): T[] {
  const stmt = db.prepare(sql)
  stmt.bind(params)
  const rows: T[] = []
  while (stmt.step()) rows.push(stmt.getAsObject() as T)
  stmt.free()
  return rows
}

export function run(sql: string, params: SqlValue[] = []): { lastId: number } {
  db.run(sql, params)
  const lastId = Number(db.exec('SELECT last_insert_rowid()')[0]?.values[0]?.[0] ?? 0)
  save()
  return { lastId }
}
