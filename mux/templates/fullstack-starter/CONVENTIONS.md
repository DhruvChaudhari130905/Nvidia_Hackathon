# MUX Coder Conventions

## General

- Keep changes small and directly related to the current task.
- Prefer existing project patterns over introducing new abstractions.
- Do not add dependencies unless the task explicitly requires them.
- Do not generate boilerplate that already exists in the starter template.

## Files

- Read a file before editing it.
- Use line-range reads when only part of a file is needed.
- Use `edit_file` for existing files when possible.
- Never overwrite changes made since the last read.
- Keep filenames and directory structure consistent with the starter template.

## Runnable projects

- The room previews the app by running `npm install` then `npm run dev` in the browser, so every app
  must start that way. A React or TypeScript app needs, at the project root:
  - `package.json` with a `dev` script (`"dev": "vite"`) and its dependencies (react, react-dom, vite,
    @vitejs/plugin-react, typescript)
  - `vite.config.ts` using `@vitejs/plugin-react`
  - `index.html` with `<div id="root"></div>` and `<script type="module" src="/src/main.tsx"></script>`
  - `src/main.tsx`, which renders the app into `#root`
- Create these first, in the first task, before writing components.
- A simple static site may be plain `index.html`, CSS and JS instead, with no package.json.
- Every link, import, CSS class and id must point at something that exists in the project.

## React / TypeScript

- Use TypeScript.
- Keep React components focused and reusable.
- Prefer existing components and utilities before creating duplicates.
- Keep UI state close to the component that owns it unless shared state is required.

## Hono / Backend

- Keep routes small and explicit.
- Validate inputs at the route boundary.
- Reuse existing backend utilities instead of duplicating logic.

## Database

- Use the database approach already provided by the starter template.
- Do not introduce a second persistence mechanism.

## Validation

- When the build tools are available, run the build after meaningful changes, run relevant tests, and
  fix build errors before declaring the task complete.
- When they aren't, re-read the files you changed and check them against the rules above.
- Do not claim success without a successful validation result.

## Task Completion

- Implement only the current task.
- If the task is blocked by a decision, use `ask_room`.
- When complete, call `finish_task` with a concise summary of what changed.