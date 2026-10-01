# MUX Web Frontend

Next.js 15 + React 19 frontend for MUX - the multiplayer coding agent.

## Tech Stack

- **Framework**: Next.js 15 (App Router)
- **Language**: TypeScript
- **Styling**: Tailwind CSS with custom GitHub Dark theme
- **Auth**: Supabase Auth (Google, GitHub OAuth)
- **Real-time**: WebSocket connection to FastAPI backend
- **Code Editor**: Monaco Editor (@monaco-editor/react)
- **Preview**: WebContainer API (@webcontainer/api)
- **State Management**: Pure reducer pattern (events → state)

## Project Structure

```
src/
├── app/
│   ├── layout.tsx          # Root layout with fonts
│   ├── globals.css         # Global styles + theme tokens
│   ├── login/
│   │   └── page.tsx        # Login page (Supabase OAuth)
│   ├── dashboard/
│   │   └── page.tsx        # Dashboard - list rooms, create new
│   └── room/[roomId]/
│       └── page.tsx        # Main room page (3-column layout)
├── components/
│   ├── feed/               # Agent feed, composer, messages
│   ├── center/             # Preview/Code tabs, file tree, editor
│   ├── room/               # Top bar, presence, budget, share dialog
│   ├── side/               # Conflict cards, question cards, plan
│   └── timeline/           # Checkpoint timeline with rewind
├── lib/
│   ├── api.ts              # REST API client
│   ├── socket.ts           # WebSocket client + presence
│   ├── reducer.ts          # Pure reducer (events → state)
│   ├── supabase.ts         # Supabase auth client
│   └── webcontainer.ts     # WebContainer integration
└── types/
    └── index.ts            # All TypeScript types
```

## Key Features Implemented

### 1. Three-Column Room Layout
- **Left**: Agent feed with messages, tool output, composer
- **Center**: Preview tab (WebContainer iframe) + Code tab (file tree + Monaco editor)
- **Right**: Conflict cards, question cards, plan list/approval

### 2. Real-time Collaboration
- WebSocket connection with automatic reconnection
- Presence indicators (avatars, typing, active tab)
- Live event streaming from backend

### 3. Conflict Resolution UI
- Vote cards with role-weighted voting
- Tavily evidence display with citations
- Owner override capability
- Countdown timers

### 4. Question Cards
- Agent questions with options
- Default answer handling
- 5-minute timeout

### 5. Plan Management
- Draft plan editing (drag to reorder, add/remove tasks)
- Owner approval flow
- Live status updates (todo/doing/done/blocked/waiting)

### 6. Code Editing
- Monaco Editor with TypeScript support
- File locking (soft locks)
- Version checking (prevents overwrites)
- Save with base version

### 7. Timeline & Rewind
- Visual checkpoint timeline
- Click to rewind to any checkpoint
- Greyed-out future events
- Return to latest

### 8. Budget Meter
- Token usage bar with color coding
- Build count tracking
- Pause at cap

## Getting Started

```bash
# Install dependencies
npm install

# Copy environment variables
cp .env.example .env.local

# Fill in your Supabase credentials in .env.local

# Run development server
npm run dev
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `NEXT_PUBLIC_SUPABASE_URL` | Supabase project URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase anonymous key |
| `NEXT_PUBLIC_API_URL` | Backend API URL (default: http://localhost:8000) |

## Design System

Colors and tokens match the GitHub Dark theme from the MUX design spec:

- `--bg`: #010409 (deep background)
- `--panel`: #0d1117 (panel background)
- `--raised`: #161b22 (raised surfaces)
- `--line`: #30363d (borders)
- `--ink`: #e6edf3 (primary text)
- `--muted`: #8d96a0 (secondary text)
- `--coord`: #3b82f6 (coordinator blue)
- `--coder`: #06b6d4 (coder cyan)
- `--ok`: #3fb950 (success green)
- `--conflict`: #f85149 (conflict red)
- `--ask`: #a371f7 (question purple)
- `--queue`: #39c5cf (queue teal)

Fonts:
- Display: Mona Sans
- Body: Mona Sans
- Mono: IBM Plex Mono

## Architecture Notes

### Event Sourcing on Client
The frontend uses a pure reducer function (`lib/reducer.ts`) that takes an array of events and produces the complete room state. This makes:
- Replay/reconnection trivial
- Rewind instant (just re-reduce up to checkpoint)
- Time-travel debugging possible
- Optimistic updates unnecessary (events are the truth)

### WebSocket Protocol
- Connect: `GET /rooms/{id}/ws?since={seq}`
- Server sends all events after `since`, then streams live
- Presence messages on same socket (not stored)
- Streaming coder text as `agent.text.delta` (not stored)

### WebContainer Integration
- Preview runs in `@webcontainer/api` (browser-based Node.js)
- File changes pushed via `fs.writeFile`
- Vite HMR updates preview automatically
- COOP/COEP headers required (set in next.config.ts)

## Backend Integration

The frontend expects a FastAPI backend with these endpoints:

### REST
- `GET /rooms` - List user's rooms
- `POST /rooms` - Create room
- `GET /rooms/{id}` - Get room details
- `PATCH /rooms/{id}/sharing` - Update sharing
- `POST /rooms/{id}/messages` - Send steering message
- `PATCH /rooms/{id}/plan` - Update plan
- `POST /rooms/{id}/plan/approve` - Approve plan
- `POST /rooms/{id}/conflicts/{cid}/vote` - Vote on conflict
- `POST /rooms/{id}/conflicts/{cid}/override` - Owner override
- `POST /rooms/{id}/questions/{qid}/answer` - Answer question
- `POST /rooms/{id}/files/lock` - Lock file
- `POST /rooms/{id}/files/unlock` - Unlock file
- `PUT /rooms/{id}/files` - Save file edit
- `POST /rooms/{id}/rewind` - Rewind to checkpoint
- `PATCH /rooms/{id}/budget` - Update budget
- `GET /github/connect` - Start GitHub OAuth
- `POST /rooms/{id}/export` - Export to GitHub

### WebSocket
- `GET /rooms/{id}/ws?since={seq}` - Event stream + presence

## License

MIT