# Repository guidance

SRE Copilot is a local incident-triage application: an embedded async agent investigates
services, proposes remediation, waits for operator approval, and verifies recovery.
Read `README.md` for setup, demo scenarios, and operational limitations.

## Build, run, and validation

Run backend commands from the repository root with an activated Python virtual environment.
Requirements are Python 3.11+, Node.js 20+, and npm 9+; CI uses Python 3.12 and Node.js 22.

| Task | Command |
| --- | --- |
| Install backend and UI dependencies | `make install` |
| Install backend only | `python -m pip install -e ".[dev]"` |
| Install UI only | `cd ui && npm ci` |
| Build production UI, including TypeScript checking | `make build` |
| Backend development server | `uvicorn sre_copilot.app:app --reload --port 8000` |
| UI development server (separate terminal) | `cd ui && npm run dev` |
| All backend tests | `python -m pytest -q` |
| One test file | `python -m pytest -q tests/test_runtime.py` |
| One test | `python -m pytest -q tests/test_runtime.py::test_run_requires_approval_and_resolves` |
| Backend lint | `python -m ruff check src tests sandbox` |
| UI type check | `cd ui && npm run typecheck` |
| Combined backend lint and UI type check | `make lint` |
| Validate deployment configuration | `docker compose config --quiet` |
| Build and start the complete application | `docker compose up --build -d` |

Vite serves port 5173 and proxies `/api` to FastAPI on port 8000. For native production
hosting, build the UI before starting FastAPI: `static.py` chooses its SPA/fallback routes
when the app is created. Rebuild and restart FastAPI to switch from the unbuilt-UI fallback.
The multi-stage `Dockerfile` builds the UI and installs the Python package, then runs
the `sre-copilot` entry point as a non-root user.

CI in `.github/workflows/ci.yml` runs Ruff and pytest, separately type-checks and builds
the UI, then builds the container after both jobs succeed.

## Architecture

- `app.py:create_app(settings)` owns the FastAPI lifespan. It initializes `RunStore`,
  `ToolRegistry`, and `AgentRuntime`, exposes them through `app.state`, recovers runnable
  incidents at startup, and stops tasks before closing the store. `api.py` is the REST/SSE
  adapter; runtime methods own operator actions and workflow transitions.
- `runtime.py` drives the five built-in plan steps: `scope`, `evidence`, `diagnose`,
  `remediate`, and `verify`. It schedules asyncio tasks with per-run locks, enforces
  step/tool budgets, retries retryable tool failures, and returns failed remediation or
  verification to evidence collection. Exhausted automation waits in `needs_human`.
  Built-in step IDs dispatch behavior; an unknown operator-defined step is acknowledged
  rather than interpreted as a new executable capability.
- `store.py` persists serialized Pydantic `RunState` snapshots in SQLite, append-only
  events, and checkpoint history. `save_run(state, reason)` also writes a checkpoint.
  Only `queued` and `running` runs are automatically scheduled on restart; pending
  approvals remain durable and wait for the operator. SQLite and in-process scheduling
  target a single application replica.
- `tools.py` registers tool definitions, risk classifications, input schemas, and async
  handlers. Tools access portable sandbox JSON, local Markdown runbooks, HTTP, or Docker.
  `llm.py` supplies optional Ollama diagnosis and recommendations, not execution authority.
  `LLM_MODE=auto` falls back to deterministic diagnosis; `deterministic` skips Ollama;
  explicit `ollama` mode records model errors and stops in `needs_human`.
- `protection.py` centralizes injection screening, DLP redaction, service/tool policies,
  and bounded outbound requests. Keep new ingestion, model, storage, and execution paths
  behind these controls. `auth.py` provides optional bearer/session authentication and
  viewer/operator/approver roles; cookie-authenticated mutations require CSRF protection.
- `knowledge.py` indexes sanitized runbooks and resolved incidents into SQLite FTS5,
  optionally adding cached Ollama embeddings for hybrid search. Index/query failures
  must be surfaced as warnings rather than presented as successful semantic retrieval.
- The React 18/TypeScript console uses Fluent UI v9. `main.tsx` supplies themes and
  `/runs/:runId` routing; `App.tsx` owns run selection/list state; `RunDetail` composes
  operator controls and panels. REST calls go through `ui/src/api/client.ts`.
  `useRunStream.ts` owns EventSource connections, event deduplication, reconnect backoff,
  and polling fallback. FastAPI serves `ui/dist` and client-side route fallbacks.

## Cross-cutting conventions

- Mutating tools must stay behind the runtime's persisted `PendingAction` and explicit
  approve endpoint, including operator-edited arguments and matching action ID. Register
  each tool's `read_only` or `mutating` risk in code; model output cannot override it.
  Keep post-action verification separate from the mutation's own success response.
- Tool handlers return data; `ToolRegistry.execute` wraps it as `{"ok": true, "data": ...}`
  or `{"ok": false, "error": ..., "retryable": ...}`. Runtime execution records
  `tool_call`, `tool_result`, and retry events and charges each attempt to the tool budget.
  Findings link back to evidence event IDs. UI reasoning is a concise operational
  summary, not raw model chain-of-thought.
- Persist workflow changes through `RunStore` with meaningful checkpoint reasons and
  corresponding timeline events. Keep new operator actions inside the per-run lock
  pattern and map `RunNotFound`/`RuntimeConflict` to HTTP 404/409 through the API adapter.
- Treat `models.py` as the backend wire/state contract. Changes to statuses, pending
  actions, plans, or events must also account for `ui/src/types.ts`, `format.ts`,
  API client methods, and consuming components. The frontend accepts compatibility
  aliases, so do not infer backend values from its permissive types.
- SSE uses named events whose names come from runtime event types, numeric persisted
  IDs, and an `EventRecord` JSON envelope. The API supports replay using `Last-Event-ID`.
  When changing events, check both API serialization and the explicit listener names
  in `useRunStream.ts`; generic `onmessage` does not consume custom named events.
- Use Fluent UI components/icons and component-local `makeStyles`, `shorthands`, and
  semantic `tokens` from `@fluentui/react-components`. The shared light/dark brand
  themes live in `ui/src/styles/theme.ts`; preserve theme-aware component styling.
- Settings are centralized in `config.py` using Pydantic Settings and `.env`;
  `get_settings()` is cached. Default filesystem paths are relative to the working
  directory. Tests inject `Settings` with `tmp_path` databases, sandbox state, and
  runbooks, and use `llm_mode="deterministic"` to avoid external model dependencies.
  Async pytest tests/fixtures use the configured `asyncio_mode="auto"`.
- The service name `demo-api` selects the portable JSON-based evidence/remediation path;
  other explicitly allowlisted service names select local Docker-container tools. Seed demo state with
  `python sandbox/chaos.py db-down` (also `bad-config`, `latency`, or `healthy`).
  The knowledge index ingests top-level `runbooks/*.md`; refresh it after runbook edits.
- Plan edits require a paused run without a pending action and must retain ordered safety
  stages. Persist the action-execution marker before mutations so restart recovery verifies
  interrupted changes instead of re-executing them.
- `ai-log/README.md` describes the source-controlled AI assistance record. Exported
  transcripts for assessment submissions must exclude credentials, machine-specific
  secrets, and private chain-of-thought.
