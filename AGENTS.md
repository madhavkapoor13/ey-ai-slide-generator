# Agent Notes for EY AI Slide Generator

FastAPI backend that generates `.pptx` consulting decks via an LLM orchestration pipeline, plus an Office.js PowerPoint task-pane add-in in `frontend/`.

## Project layout

- `backend/` — FastAPI app, AI pipeline modules, LLM router, design system, layout engine.
- `frontend/` — Real Node project. Plain HTML/CSS/JS Office.js add-in. Root `package-lock.json` is stale; ignore it.
- `ppt_renderer/` — python-pptx renderers and component renderers used by both pipelines.
- `schemas/` — Pydantic models shared across the pipeline.
- `tests/` — `unittest` suite (no pytest/lint/typecheck/formatter config).
- `docs/ARCHITECTURE.md` — deeper pipeline design.

## Running locally

Backend (HTTPS — required for the Office add-in WebView on macOS):

```bash
./scripts/start_backend_https.sh
```

- Runs `venv/bin/uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000` with self-signed certs from `~/.office-addin-dev-certs/`.
- Exits early if certs are missing. Install them once with `cd frontend && npm start`.

Frontend:

```bash
cd frontend
npm install
npm start
```

- Serves HTTPS on `https://localhost:3000/taskpane/taskpane.html` and installs dev certs.
- Plain HTTP alternative: `npm run start:http` (not sufficient for PowerPoint sideload on macOS).
- Sideload into PowerPoint: `npm run sideload`.

## Testing

```bash
./venv/bin/python -m unittest discover -s tests -v
./venv/bin/python -m unittest tests.test_orchestrator -v   # single module
```

- Tests mock LLM calls and run offline without valid API keys.
- No CI, lint, typecheck, or formatter config exists.

## API

- `POST /generate` — Phase 1 legacy single-slide pipeline.
- `POST /generate-slide` — Alias to Phase 1.
- `POST /generate/v2` — Phase 2 orchestrated consulting deck. Always returns a `.pptx`: completed deck, clarification placeholder, or failure placeholder.

Backend CORS allows only `https://localhost:3000` and `https://127.0.0.1:3000`; `POST` and `OPTIONS` only.

## Environment / secrets

See `.env.example`. Configure only the providers you use; the router skips unconfigured ones.

- `GEMINI_API_KEY` (also accepts `GOOGLE_API_KEY`) — Phase 2 primary provider.
- `OPENAI_API_KEY` — Phase 1 direct calls + Phase 2 fallback.
- `GROQ_API_KEY`, `CEREBRAS_API_KEY`, `OPENROUTER_API_KEY` — additional router providers.
- Optional `GEMINI_CONTEXT_MODEL` overrides the Gemini model used by legacy direct calls and router fallback.

Module→provider priority and model IDs are the single source of truth in `backend/llm/config.py` (`MODEL_ROUTING`, `MODEL_NAMES`, `PROVIDER_CONFIG`). Business modules must not hardcode provider/model names.

`.env` is gitignored and present locally. Do not commit it.

## Architecture gotchas

- **Orchestrator owns the topology.** `backend/orchestrator.py` is the only place that knows the full Phase 2 order: Intent → Presentation Planning → Information Analysis → (Clarification) → Context → Process Mapping → Deck Execution → Render. Modules do not call each other directly.
- **Module boundaries are Pydantic schemas.** No raw dicts cross module boundaries except `SlideSpec.raw_spec`, which is the renderer contract.
- **Prompts live in `backend/ai/`.** `backend/llm/prompt_loader.py` loads `backend/ai/instructions.md` once at startup and composes module prompts from `backend/ai/prompts/*.md`. The files in `backend/prompts/*.txt` and `prompts/slide_prompt.py` are dead; do not edit them. Phase 1 prompts live in `backend/llm/prompts.py`.
- **Multi-Provider LLM Router is the single entry point for business modules.** `backend/llm/router.py` exposes `generate_json(module_name, prompt, ...)`. The router retries transient errors, falls back through the priority list, and keeps using the same provider for a module within a deck session.
- **Deck Executor continues on per-slide failures.** `execute_deck()` generates each slide independently and does not abort the deck on a single failure.
- **Visual pattern is decided once and carried.** The Deck Executor calls `plan_visual_pattern()` before content generation and passes the result into `generate_slide_content()`. `slide_service._resolve_visual_selection()` honors the carried `pattern_id` as the single source of truth; only re-score when no id is carried (legacy/direct callers).
- **Content grounding priority:** `EnterpriseContext` > `ProcessResult` > `DomainKnowledge` > model prior. The Knowledge Manager (`backend/knowledge/consulting_knowledge.json`) is deterministic and requires no LLM.
- **Design System / Theme Engine** supplies styling tokens from `backend/themes/*.json`. Component renderers consume the active theme; do not hardcode RGB values or fonts.

## Generated artifacts

- `generated_slide.pptx` (Phase 1) and `generated_slide_v2.pptx` (Phase 2) are produced in the repo root.
- `*.pptx` is gitignored; do not commit generated files.
- `scripts/run_comparison.py` batch-hits both endpoints and writes results to `test_outputs/`.
