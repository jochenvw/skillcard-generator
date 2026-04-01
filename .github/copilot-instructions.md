# Copilot Instructions for skillcard-generator

## Project overview
This is a **Profile Agent** — an interview-style web app that builds a personalized strengths "skill card" (Pokémon-style). It has a Python/FastAPI backend and a React/TypeScript frontend.

## Tech stack
- **Backend**: Python 3.12, FastAPI, Azure OpenAI (via `openai` SDK), Pydantic
- **Frontend**: React 19, TypeScript, Vite, Tailwind CSS v4, Vercel AI SDK types
- **Infrastructure**: Docker, Azure Container Apps, Bicep IaC
- **Package management**: `uv` (Python), `npm` (frontend)

## Repository structure
- `src/profile_agent/` — Python backend (FastAPI app, services, stages, prompts)
- `frontend/src/` — React frontend (components, hooks, types)
- `tests/` — Python tests (pytest)
- `infra/` — Bicep infrastructure modules
- `.github/workflows/` — CI/CD pipelines

## CI requirements (must pass before merge)
All PRs must pass these checks:
1. **lint-and-test**: `ruff check` + `pytest` on Python code
2. **build-frontend**: `eslint` + `vite build` on React code
3. **build-docker**: Full Docker image build

## Code conventions
- Python: Follow ruff rules (E, F, W, I, N, UP, B, A, SIM, TCH). Line length 120.
- TypeScript: ESLint with React 19 strict rules. No `setState` inside `useEffect`. No ref access during render.
- Use `useCallback`/`useMemo` properly with complete dependency arrays.
- Backend SSE streaming uses AI SDK Data Stream Protocol (`text-start`, `text-delta`, `text-end`, `data-stateUpdate`).
- All LLM calls must be wrapped in try/except with user-visible error messages in the SSE stream.

## How to run locally
```bash
# PowerShell
.\scripts\dev.ps1
# or manually:
uv sync && cd frontend && npm install && npm run build && cd .. && uv run python -m profile_agent
```

## How to run tests
```bash
uv run --extra dev python -m pytest tests/ -v
cd frontend && npm run lint && npm run build
```

## When fixing CI failures
1. Read the failing job logs carefully
2. Run the relevant checks locally before pushing (`pytest`, `npm run lint`, `npm run build`)
3. Do not introduce new lint suppressions — fix the underlying issue
4. Ensure all 36+ existing Python tests still pass
