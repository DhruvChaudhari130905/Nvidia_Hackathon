# MUX design theme

**Status:** Chosen by the user on 2026-09-28. Based on GitHub Dark (Primer). The reference mockup is [`../demos/mux-room-demo.html`](../demos/mux-room-demo.html).

MUX is dark-only for the MVP.

## Color tokens

| Token | Hex | Use |
|---|---|---|
| `--bg` | `#010409` | Page background |
| `--panel` | `#0d1117` | Top bar, columns, timeline |
| `--raised` | `#161b22` | Cards, inputs, secondary buttons, active tab |
| `--line` | `#30363d` | Borders and dividers |
| `--ink` | `#e6edf3` | Primary text |
| `--muted` | `#8d96a0` | Secondary text |
| `--faint` | `#6e7681` | Timestamps, hints, file tree |
| `--code-bg` | `#010409` | Code view background |
| `--coord` (accent) | `#4493f8` | Coordinator labels, budget bar, agent avatar, focus ring |
| `--coder` | `#d29922` | Coder's in-progress task |
| `--ok` | `#3fb950` | Build passed, checkpoints |
| `--conflict` | `#f85149` | Conflict cards, votes, interrupts |
| `--ask` | `#a371f7` | Agent question cards (`ask_room`) |
| `--queue` | `#39c5cf` | Queued plan items |
| Primary button | `#238636` bg, `#2ea043` border, `#ffffff` text | Send, Export to GitHub |

Avatar initials use `#0d1117` on pastel circles. The agent avatar is white on `--coord`.

## Code syntax

| Element | Hex |
|---|---|
| Keyword | `#ff7b72` |
| String | `#a5d6ff` |
| Comment | `#8b949e` |
| JSX tag | `#7ee787` |
| Attribute | `#79c0ff` |

## Type

- UI and headings: **Mona Sans** (Google Fonts), falling back to the system UI font.
- Code, labels, and timestamps: **IBM Plex Mono**, falling back to `ui-monospace`.

## Message labels

The coordinator's label chips are outlined in the matching color: merge `--coord`, queue `--queue`, interrupt and conflict `--conflict`, chat `--muted`.
