/// <reference types="vitest" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The API runs on port 3000; the dev server forwards /api there so the app can call fetch('/api/...')
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { '/api': 'http://localhost:3000' },
  },
  test: {
    include: ['src/**/*.test.ts'],
    environment: 'node',
    env: { DB_FILE: ':memory:' },
  },
})
