# Room AI provider (bring your own key): design

**Date:** 2026-10-09 · **Status:** approved in conversation, awaiting spec review

## Goal

A room's owner can point the room's agents (coordinator and coder) at the AI provider of their choice,
with their own API key and their own model for each agent role. The owner pays that provider for the
room's usage. Rooms without a setting keep using the server's Token Factory key.

## Decisions

| Question | Decision |
|---|---|
| Whose key | The room owner's, set per room. Everyone in the room's agent work uses it. |
| Which providers | Any OpenAI-compatible chat completions API (base URL + key + model ids). The UI offers presets. |
| Model roles | Three, as today: Lightning (coordinator), Super (coder), Ultra (coder's escalation). |
| Who sees what | Everyone in the room sees provider, base URL and model ids; only the owner changes them; the key is never sent to browsers. |
| Fallback | No room setting → the server's Token Factory settings. Neither → agents are off for that room (today's behaviour without Token Factory). |
| When a change applies | From the next model call. No restart of the room. |
| Validation | Saving makes one tiny request per distinct model; any failure → nothing saved, per-role errors shown. |
| Errors during work | A failed model call posts a feed notice (at most one a minute per room, key hidden). Coder failures still park the task with the reason. |

## Architecture

```
room events (owner, via UI) ─► RoomActor.ai_settings ─┐
                                                      ├─► RoomLLM (one per room runtime; implements LLM)
server .env (Token Factory) ─► default OpenAILLM ─────┘     • each chat(): room settings → client for them
                                                            •               else → the server's client
                                                            •               neither → NoModel
                                Coordinator, CoderLoop, research use RoomLLM unchanged
```

### Shared pieces moved out of `mux/mcp/`

- `mux/mcp/secrets.py` → `mux/secrets.py` (same API: `encrypt_headers`/`decrypt_headers` become
  `encrypt_values`/`decrypt_values`, `SecretsUnavailable`), keyed by the new setting `ROOM_SECRETS_KEY`.
  `MCP_ENCRYPTION_KEY` is still read when `ROOM_SECRETS_KEY` is empty.
- `mux/mcp/urls.py` → `mux/urls.py` (same API), allowed private addresses via the new setting
  `ALLOW_PRIVATE_URLS`; `MCP_ALLOW_PRIVATE_URLS` is still read as the old name.
- MCP code imports the moved modules; its behaviour doesn't change.

### LLM clients (`mux/agents/llm.py`)

- `TokenFactoryLLM` becomes `OpenAILLM(base_url, api_key, models: dict[ModelRole, str], *, thinking: bool)`.
  `thinking=True` sends Nemotron's `chat_template_kwargs.enable_thinking` (Token Factory only); otherwise
  `reasoning` is ignored. `TokenFactoryLLM()` stays as a function returning `OpenAILLM` from settings.
- `NoModel(Exception)`: raised when a room has no model.
- `RoomLLM(actor, default: OpenAILLM | None)` (`mux/agents/room_llm.py`):
  - `available() -> bool`: room settings present, or a default.
  - `chat(...)`: builds (and caches, keyed by the settings' event id) an `OpenAILLM` from
    `actor.ai_settings` with the decrypted key; else uses `default`; else raises `NoModel`. If the key
    can't be decrypted (secrets key changed), it raises `NoModel` with that reason.
- `check_models(llm: OpenAILLM) -> dict[role, str | None]`: one request per distinct model id
  (`"Reply with OK"`, `max_tokens=5`), error text per role or None. Error texts have the key replaced
  by `[hidden]`.

### Room state and events

| Event | Fields | Sent to browsers as |
|---|---|---|
| `room_ai_settings_saved` | provider, base_url, api_key (encrypted), models `{lightning, super, ultra}` | `ai.changed` `{provider, base_url, models, has_key: true}` |
| `room_ai_settings_cleared` | — | `ai.changed` `{cleared: true}` |

`RoomActor.ai_settings: dict | None` is rebuilt from these events.

### API (`mux/server/mux/api/ai.py`, mounted under `/rooms`)

| Method and path | Who | What |
|---|---|---|
| `GET /rooms/{id}/ai` | viewer | `{source: "room" \| "server" \| "none", provider, base_url, models, has_key}` |
| `PUT /rooms/{id}/ai` | owner | `{provider, base_url, api_key, models}`: URL check (400), encrypt (400 without a secrets key), `check_models` (400 with `{errors: {role: text}}` if any fails), then save |
| `DELETE /rooms/{id}/ai` | owner | Back to the server's model |

`provider` is a label from a fixed list: `token_factory`, `openai`, `anthropic`, `openrouter`, `groq`,
`together`, `custom`. Only `token_factory` turns on `thinking`. Model ids: 1–200 chars, no whitespace.
API key: 1–500 chars, visible ASCII. The key is never returned.

### Runtime

- `main.agent_runtime_factory()` always returns a factory: `RoomRuntime(actor, RoomLLM(actor, default))`
  where `default` is the Token Factory client when configured, else `None`.
- `RoomRuntime._handle` returns early when `not self.llm.available()` (no agent work, no notices); the
  coder loop doesn't start tasks either.
- On `room_ai_settings_saved` the runtime wakes the coder so approved tasks start.
- Model errors: `openai.APIError` and `NoModel` in the event handler and the coder post
  `ai.error {error}` (throttled to one a minute per room), error text with the key hidden.

### Web UI

- An **AI model** button in the room's top bar opens a dialog.
- Everyone sees the source ("This room's key" / "The MUX server's model" / "No AI model: agents are
  off"), provider and models.
- The owner sees a form: provider preset (fills base URL and suggested model ids), base URL, API key
  (password field, "leave empty to keep the saved key" when one is set), three model ids, **Save** (shows
  per-role check errors) and **Use the server's model**.
- The feed shows `ai.error` notices like `mcp.unavailable`.

Presets (base URL; suggested Lightning / Super / Ultra):

| Provider | Base URL | Suggested models |
|---|---|---|
| Nebius Token Factory | `https://api.tokenfactory.nebius.com/v1` | left empty (owner fills in from GET /v1/models) |
| OpenAI | `https://api.openai.com/v1` | left empty |
| Anthropic | `https://api.anthropic.com/v1` | `claude-haiku-4-5-20251001` / `claude-sonnet-5-5` / `claude-opus-5-5` |
| OpenRouter | `https://openrouter.ai/api/v1` | left empty |
| Groq | `https://api.groq.com/openai/v1` | left empty |
| Together | `https://api.together.xyz/v1` | left empty |
| Custom | empty | empty |

When the key field is left empty on a room that already has a key, the saved key is kept (and still checked).

Structured output (`response_format: json_schema`) isn't supported by every provider. The coordinator already parses JSON out of the reply text (`agents/coordinator/agent.py`), so providers that ignore `response_format` still work if the model follows the prompt; the save check only proves the key and model ids work.

## Error handling

| Situation | Result |
|---|---|
| Base URL not https / private | 400, nothing saved |
| No `ROOM_SECRETS_KEY` (or old `MCP_ENCRYPTION_KEY`) | 400, nothing saved |
| A model check fails | 400 with per-role errors, nothing saved |
| Secrets key changed after saving | `NoModel` with the reason → `ai.error` notice; owner re-saves the key |
| Provider error during work (401, 429, 5xx) | `ai.error` notice (throttled); coordinator skips that message; coder task parked with the reason |
| No model at all | Agents off for the room, no notices; dialog says so |

## Testing

- `RoomLLM`: room settings used when present, server default otherwise, `NoModel` with neither,
  cache refreshed after a new save, `thinking` only for `token_factory`.
- `check_models`: per-role errors, key hidden, one request per distinct model.
- API: owner-only changes, viewer reads, key never in responses or the socket dump, URL refusal,
  failed check saves nothing, keep-saved-key on empty key, clear, survives rehydration.
- Runtime: no model → no agent work; model error → one `ai.error` per minute; saving a key starts an
  approved task.
- Moved secrets/URL modules: old setting names still work.
- Web: `tsc`, lint, build.

## Out of scope

- Per-user keys (each person's own key).
- Provider-specific (non-OpenAI-compatible) APIs.
- Price-aware budgets (the budget meter keeps counting tokens).
- Listing a provider's models in the dialog.
