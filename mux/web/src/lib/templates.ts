// Starter templates offered by Quick Launch (dashboard) and the Sandbox screen.
// `prompt` pre-fills the "What do you want to build?" box when creating a room.
export interface StarterTemplate {
  id: string;
  name: string;
  summary: string;
  runtime: 'node' | 'python';
  stack: string[];
  prompt: string;
}

export const STARTER_TEMPLATES: StarterTemplate[] = [
  {
    id: 'react-vite',
    name: 'React + Vite + Tailwind',
    summary: 'Standard component scaffolding',
    runtime: 'node',
    stack: ['React 18', 'Vite 5', 'Tailwind 3'],
    prompt: 'A React + Vite + Tailwind single-page app with a navbar, hero section and a card grid.',
  },
  {
    id: 'nextjs',
    name: 'Next.js App Router',
    summary: 'Full-stack server components',
    runtime: 'node',
    stack: ['Next.js 15', 'Server Actions', 'Tailwind 3'],
    prompt: 'A Next.js App Router project with server components, an API route and a dashboard page.',
  },
  {
    id: 'fastapi',
    name: 'Python FastAPI Service',
    summary: 'Async endpoints and OpenAPI spec',
    runtime: 'python',
    stack: ['FastAPI', 'Pydantic 2', 'SQLite'],
    prompt: 'A Python FastAPI service with async CRUD endpoints, Pydantic models and an OpenAPI spec.',
  },
  {
    id: 'fullstack',
    name: 'Hono + React Full-stack',
    summary: 'Vite frontend with a Hono API and SQLite',
    runtime: 'node',
    stack: ['React 18', 'Hono 4', 'SQLite (sql.js)'],
    prompt: 'A full-stack app: React frontend, Hono API server and a SQLite database with a health route.',
  },
];
