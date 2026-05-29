# KnowMe Deployment and Admin Guide

## Overview
KnowMe is a lightweight CV Q&A assistant for recruiter-style interactions. It consists of:

- Backend: `backend/app/main.py` (FastAPI)
- Frontend: `backend/static/index.html`
- Admin UI: `backend/static/admin.html`
- Static assets and styles: `backend/static/main-style.css`
- Dependencies: `backend/requirements.txt`

## Architecture

- `/` serves the public question-and-answer interface.
- `/admin` serves the admin UI for ingesting CV and STAR content and testing questions.
- `/ask` is the main API endpoint that scores CV text and optionally rewrites answers with the OpenAI API.
- `/ingest_cv` stores the CV text in `backend/data/cv.txt`.
- `/ingest_star` stores STAR examples in `backend/data/star.txt`.
- `/reload` refreshes the loaded content in memory.

## Deployment on Render

Recommended Render service configuration:

- Root directory: `backend`
- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Environment: Python 3.x
- Add secret env var: `OPENAI_API_KEY`

### Notes
- `backend/requirements.txt` contains the runtime dependencies.
- `backend/.env` is used locally for environment variables, but secrets should be configured in Render.
- Render should be connected to the GitHub `main` branch for automatic deploys.
- `render.yaml` at the repo root is a Render manifest that stores the service settings in source control.

## Admin workflow

1. Open `/admin`.
2. Paste the candidate CV into the CV text box and click `Ingest CV`.
3. Paste STAR examples into the STAR text box and click `Ingest STAR`.
4. Use the question box to test recruiter-style questions.
5. Use the `Reload status` button to confirm current CV and STAR content is loaded.

## Logging and analytics

KnowMe logs question interactions to both:

- `backend/data/questions.log` for quick human-readable inspection
- `backend/data/question_events.jsonl` for structured analytics

Each row contains:

- Timestamp
- Request id
- Anonymous browser `client_id`
- Browser `session_id`
- Request route (`/ask` or `/api/ask`)
- Source page/path (`/` vs `/admin`)
- Optional hashed IP (`client_ip_hash`) when `ANALYTICS_SALT` is configured
- Optional `name` and `company`
- Original question (`q=`)
- Normalized question (`q_norm=`)
- Canonical grouped question (`q_canonical=`)

This supports cleaner analytics by grouping similar questions together and separating repeated tests from likely distinct visitors.

The app also writes intent events to `backend/data/intent_log.jsonl` for internal analysis.

To enable privacy-preserving hashed IP counts, set `ANALYTICS_SALT` in the backend environment. Raw IP addresses are not stored.

## Question normalization

KnowMe now normalizes questions before logging:

- lowercases text
- removes punctuation
- collapses repeated whitespace
- replaces candidate references (e.g. `Rob`, `Robert`) with a stable placeholder
- normalizes role variants such as `technical BA`, `BA`, and `technical business analyst` to `business analyst`

This reduces noisy duplicates and improves analytics quality.

## Local development

From `backend`:

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Then open `http://127.0.0.1:8000/` for the frontend or `http://127.0.0.1:8000/admin` for the admin UI.

## Improvements included

- Better landing page UX with sample questions, status messages, and clipboard support.
- More usable admin dashboard with reload state, ingest feedback, and copy response support.
- Cleaner styles and responsive layout.

## Future recommendations

- Add a Render manifest (`render.yaml`) for reproducible service configuration.
- Add versioned backup of `backend/data/questions.log` if analytics need to scale.
- Add a dedicated `/status` endpoint returning loaded config and log metadata.
