import { describe, expect, it } from 'vitest'
import { app } from './app'

describe('api', () => {
  it('reports health', async () => {
    const res = await app.request('/api/health')
    expect(res.status).toBe(200)
    expect((await res.json()).status).toBe('ok')
  })

  it('adds and lists items', async () => {
    const created = await app.request('/api/items', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: 'first' }),
    })
    expect(created.status).toBe(201)
    const items = await (await app.request('/api/items')).json()
    expect(items.map((i: { name: string }) => i.name)).toContain('first')
  })

  it('rejects an empty name', async () => {
    const res = await app.request('/api/items', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: ' ' }),
    })
    expect(res.status).toBe(400)
  })
})
