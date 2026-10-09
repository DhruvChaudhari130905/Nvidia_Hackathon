# 🚀 03 · Getting started

**← Prev** [02 · Architecture](02-architecture.md) · [📚 Docs home](README.md) · **Next →** [04 · Frontend](04-frontend.md)

---

## ✅ Prerequisites

| Tool | Version | For |
|---|---|---|
| Node.js | 20+ | `mux/web` |
| npm | 10+ | `mux/web` |
| Python | 3.11+ | `mux/server` |
| A Chromium browser | recent | WebContainers (the in-browser shell and preview) |

## 🎮 Option A: demo mode (no keys, 1 minute)

The web app ships with sample rooms, teammates, votes and files, all served from your browser.

```bash
cd mux/web
npm install
NEXT_PUBLIC_DEMO_MODE=true npm run dev
```

Then open **http://localhost:3000/room/demo-yoga**, or go to `/login` and click **Try the demo**.

> [!NOTE]
> Demo-mode data lives in `localStorage` and IndexedDB, so it survives reloads. Sign out to leave demo mode.

## 🔐 Option B: real sign-in

```bash
cd mux/web
cp .env.example .env.local
```

| Variable | What it is |
|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | Your Supabase project URL |
| `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | Supabase publishable key, auth only (`NEXT_PUBLIC_SUPABASE_ANON_KEY` also works) |
| `NEXT_PUBLIC_API_URL` | Backend base URL, default `http://localhost:8000` |
| `NEXT_PUBLIC_DEMO_MODE` | `true` to force demo mode (default `false`) |

In Supabase, enable the Google and GitHub providers and add `http://localhost:3000/auth/callback` as a redirect URL.

With `make server` running, signed-in rooms load from the API, and the coordinator and coder run in every room (they need the Token Factory settings in `mux/server/.env`).

## 👥 Working on one room together

Everyone in a room shares one live session. There are three ways in; the owner manages all of them from **Share** in the room's top bar:

| Way in | Who sets it up | What the teammate does | Role they get |
|---|---|---|---|
| **Link** | Owner picks "Anyone with the link" and whether link joiners can steer or only watch | Opens the link (Copy or WhatsApp) and signs in | Editor or viewer, as chosen |
| **Email invite** | Owner enters their email and a role | Clicks the link in the email, signs in with that email | The invited role, even in a private room |
| **Room ID + password** | Owner sets a password (when creating the room, or in Share) | Dashboard > **Join room**, enters the Room ID and password | Editor |

Invite emails are sent by Supabase, which needs `SUPABASE_SERVICE_ROLE_KEY` in `mux/server/.env` and the web app's `/auth/callback` in Supabase's Redirect URLs. If an email can't be sent (no key, or Supabase's hourly email limit), the invite is still saved: send the link yourself and it works the same once they sign in with that email. Supabase's built-in mailer only sends a few emails an hour; add your own SMTP server in Supabase for more.

### Teammates on other computers

`localhost` only works on your machine. For a quick session, `make tunnel` (needs `brew install cloudflared`) gives the web app and API public https addresses and prints the two restart commands and the Supabase redirect URL to add. For something permanent, deploy the web app and API and set `NEXT_PUBLIC_API_URL` and `WEB_APP_URL` to their addresses.

## ⚡ Shortcut: the Makefile

From the repo root, `make help` lists everything. The usual flow:

```bash
make setup     # backend venv + npm packages, copies mux/server/.env
make demo      # web app in demo mode on :3000
make server    # API on :8000 (in another terminal)
make check     # backend tests + web type-check, lint, build
```

## 🐍 The backend

```bash
cd mux/server
python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
uvicorn mux.main:app --reload --port 8000   # http://localhost:8000/docs
pytest -q          # no API keys needed (fake LLM, fake sandbox)
```

Run everything from `mux/server`: the `.env` file is found relative to the current directory.

With an empty `DATABASE_URL` the room actor uses a local SQLite file. The Postgres layer (checkpoints, rewind, room files) and its 26 tests need Postgres:

```bash
docker compose up -d --wait   # Postgres 16 on localhost:5433, plus the mux_test database
pytest -q                     # now runs the DB tests too
```

<details>
<summary><b>🔑 Server environment variables</b></summary>

All of these are in `mux/server/.env.example`; `mux/config.py` reads them.

| Variable | Used by |
|---|---|
| `DATABASE_URL`, `TEST_DATABASE_URL`, `DEBUG` | Postgres (`db/`, `dbsession.py`) and tests |
| `TOKEN_FACTORY_API_KEY`, `TOKEN_FACTORY_BASE_URL` | Nemotron calls (`agents/llm.py`) |
| `MODEL_LIGHTNING`, `MODEL_SUPER`, `MODEL_ULTRA` | Model ids (check with `GET /v1/models`) |
| `SANDBOX_API_KEY`, `SANDBOX_BASE_URL`, `SANDBOX_IMAGE` | Builds and tests in Nebius Sandboxes |
| `TAVILY_API_KEY` | Conflict research and `web_search` |
| `SUPABASE_URL`, `SUPABASE_JWT_SECRET`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_JWT_AUDIENCE`, `SUPABASE_JWT_ISSUER` | JWT checks (`auth/supabase.py`) |
| `ALLOW_UNVERIFIED_TOKENS` | Local development only; never in production |
| `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `GITHUB_REDIRECT_URI`, `GITHUB_TOKEN_ENCRYPTION_KEY` | GitHub export |

</details>

## 🧪 Checks to run before you push

| Where | Command | Expect |
|---|---|---|
| `mux/web` | `npx tsc --noEmit` | 0 errors |
| `mux/web` | `npm run lint` | 0 errors |
| `mux/web` | `npm run build` | passes |
| `mux/web` | `npm audit --omit=dev` | no high or critical |
| `mux/server` | `pytest -q` | all pass |
| `mux/server` | `pyright mux tests scripts` | 0 errors |

## 🩺 Troubleshooting

<details>
<summary><b>The terminal or preview says "not cross-origin isolated"</b></summary>

WebContainers need COOP/COEP headers. `next.config.ts` sends them on every page; make sure you open the app at the dev server URL directly, not inside another site's iframe, and use a Chromium-based browser.

</details>

<details>
<summary><b>Sign-in loops back to /login</b></summary>

Check that both Supabase variables are set in `.env.local`, restart `npm run dev`, and confirm the callback URL is allowed in Supabase. Errors from the provider now show on the login page.

</details>

<details>
<summary><b>"Files aren't syncing to the room server"</b></summary>

Expected until the backend files API exists. Your files are saved in this browser (IndexedDB) and are still there after a reload.

</details>

<details>
<summary><b><code>npm run gen:types</code> says there are no schemas</b></summary>

The backend's `scripts/export_schema.py` is still a stub. Once it writes JSON Schema into `mux/packages/schema/generated/`, the command generates `src/types/generated/`.

</details>

---

**← Prev** [02 · Architecture](02-architecture.md) · **Next →** [04 · Frontend](04-frontend.md)
