// The starter project every new room begins with: React + Vite frontend, Hono API, SQLite database.
// SQLite comes from sql.js (SQLite compiled to WebAssembly) rather than better-sqlite3, because native
// modules can't be built in the browser's WebContainer: npm install would stall trying to compile them.

const files: Record<string, string> = {
  'package.json': `${JSON.stringify(
    {
      name: 'mux-app',
      version: '0.0.0',
      private: true,
      type: 'module',
      scripts: {
        dev: 'concurrently -n web,api -c cyan,magenta "vite" "tsx watch src/server/index.ts"',
        'dev:web': 'vite',
        'dev:api': 'tsx watch src/server/index.ts',
        build: 'tsc --noEmit && vite build',
        start: 'tsx src/server/index.ts',
      },
      dependencies: {
        '@hono/node-server': '^1.13.0',
        hono: '^4.6.0',
        react: '^18.3.1',
        'react-dom': '^18.3.1',
        'sql.js': '^1.12.0',
        zod: '^3.23.0',
      },
      devDependencies: {
        '@types/node': '^22.0.0',
        '@types/react': '^18.3.0',
        '@types/react-dom': '^18.3.0',
        '@types/sql.js': '^1.4.9',
        '@vitejs/plugin-react': '^4.3.0',
        autoprefixer: '^10.4.20',
        concurrently: '^9.0.0',
        postcss: '^8.4.47',
        tailwindcss: '^3.4.14',
        tsx: '^4.19.0',
        typescript: '^5.6.0',
        vite: '^5.4.0',
      },
    },
    null,
    2,
  )}\n`,

  'tsconfig.json': `${JSON.stringify(
    {
      compilerOptions: {
        target: 'ES2022',
        lib: ['ES2022', 'DOM', 'DOM.Iterable'],
        module: 'ESNext',
        moduleResolution: 'bundler',
        jsx: 'react-jsx',
        strict: true,
        skipLibCheck: true,
        esModuleInterop: true,
        isolatedModules: true,
        resolveJsonModule: true,
        noEmit: true,
        types: ['node'],
      },
      include: ['src', 'vite.config.ts'],
    },
    null,
    2,
  )}\n`,

  'vite.config.ts': `import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The API runs on port 3000; the dev server forwards /api there so the app can call fetch('/api/...')
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { '/api': 'http://localhost:3000' },
  },
})
`,

  'tailwind.config.js': `/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: { extend: {} },
  plugins: [],
}
`,

  'postcss.config.js': `export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
}
`,

  '.gitignore': `node_modules
dist
*.db
*.log
.env
`,

  'index.html': `<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>MUX App</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
`,

  'src/main.tsx': `import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
`,

  'src/index.css': `@tailwind base;
@tailwind components;
@tailwind utilities;

body {
  margin: 0;
  min-height: 100vh;
  font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}
`,

  'src/App.tsx': `import { useEffect, useState, type FormEvent } from 'react'

type Item = { id: number; name: string; created_at: string }

export default function App() {
  const [status, setStatus] = useState('checking…')
  const [items, setItems] = useState<Item[]>([])
  const [name, setName] = useState('')

  const load = () =>
    fetch('/api/items')
      .then(r => r.json())
      .then(setItems)
      .catch(() => setItems([]))

  useEffect(() => {
    fetch('/api/health')
      .then(r => r.json())
      .then(d => setStatus(d.status))
      .catch(() => setStatus('API not running (npm run dev starts it)'))
    load()
  }, [])

  const add = async (e: FormEvent) => {
    e.preventDefault()
    if (!name.trim()) return
    await fetch('/api/items', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    })
    setName('')
    load()
  }

  return (
    <div className="min-h-screen bg-gray-50 p-8 dark:bg-gray-900">
      <div className="mx-auto max-w-2xl">
        <h1 className="mb-2 text-3xl font-bold text-gray-900 dark:text-gray-100">Hello from MUX!</h1>
        <p className="mb-8 text-gray-600 dark:text-gray-300">
          API: <span className="font-mono">{status}</span>
        </p>
        <form onSubmit={add} className="mb-4 flex gap-2">
          <input
            value={name}
            onChange={e => setName(e.target.value)}
            placeholder="Add an item"
            className="flex-1 rounded border border-gray-300 px-3 py-2 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100"
          />
          <button className="rounded bg-blue-600 px-4 py-2 font-medium text-white hover:bg-blue-700">Add</button>
        </form>
        <ul className="divide-y divide-gray-200 rounded bg-white shadow dark:divide-gray-700 dark:bg-gray-800">
          {items.map(item => (
            <li key={item.id} className="px-4 py-3 text-gray-800 dark:text-gray-100">{item.name}</li>
          ))}
          {items.length === 0 && <li className="px-4 py-3 text-gray-500">No items yet</li>}
        </ul>
      </div>
    </div>
  )
}
`,

  'src/server/db.ts': `// SQLite via sql.js (WebAssembly), so it runs anywhere Node does, including the browser sandbox.
// The database lives in memory and is saved to app.db after every write.
import fs from 'node:fs'
import initSqlJs, { type SqlValue } from 'sql.js'

const FILE = 'app.db'
const SQL = await initSqlJs()
const db = fs.existsSync(FILE) ? new SQL.Database(fs.readFileSync(FILE)) : new SQL.Database()

db.run(\`
  CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
  )
\`)

const save = () => fs.writeFileSync(FILE, db.export())

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
`,

  'src/server/index.ts': `import { Hono } from 'hono'
import { serve } from '@hono/node-server'
import { z } from 'zod'
import { all, run } from './db'

const app = new Hono()

app.get('/api/health', c => c.json({ status: 'ok', timestamp: new Date().toISOString() }))

app.get('/api/items', c => c.json(all('SELECT * FROM items ORDER BY id DESC')))

const NewItem = z.object({ name: z.string().trim().min(1).max(200) })

app.post('/api/items', async c => {
  const parsed = NewItem.safeParse(await c.req.json().catch(() => null))
  if (!parsed.success) return c.json({ error: parsed.error.flatten() }, 400)
  const { lastId } = run('INSERT INTO items (name) VALUES (?)', [parsed.data.name])
  return c.json({ id: lastId, name: parsed.data.name }, 201)
})

const port = Number(process.env.PORT) || 3000
serve({ fetch: app.fetch, port }, () => console.log(\`API running on http://localhost:\${port}\`))
`,
};

export function starterProjectFiles(): Map<string, { content: string }> {
  return new Map(Object.entries(files).map(([path, content]) => [path, { content }]));
}
