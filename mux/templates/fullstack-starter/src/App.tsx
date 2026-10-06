import { useEffect, useState, type FormEvent } from 'react'

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
