// The API routes. index.ts serves them; tests call app.request() directly.
import { Hono } from 'hono'
import { z } from 'zod'
import { all, run } from './db'

export const app = new Hono()

app.get('/api/health', c => c.json({ status: 'ok', timestamp: new Date().toISOString() }))

app.get('/api/items', c => c.json(all('SELECT * FROM items ORDER BY id DESC')))

const NewItem = z.object({ name: z.string().trim().min(1).max(200) })

app.post('/api/items', async c => {
  const parsed = NewItem.safeParse(await c.req.json().catch(() => null))
  if (!parsed.success) return c.json({ error: parsed.error.flatten() }, 400)
  const { lastId } = run('INSERT INTO items (name) VALUES (?)', [parsed.data.name])
  return c.json({ id: lastId, name: parsed.data.name }, 201)
})
