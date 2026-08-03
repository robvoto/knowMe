# KnowMe — Grounded Interactive CV Assistant

KnowMe is an AI-assisted CV question-and-answer application designed for recruiters and hiring managers. It turns structured career material into concise answers while keeping the candidate's supplied CV and STAR examples as the source of truth.

## Live application

**[Open KnowMe](https://knowme.robvoto.com)**

## Problem

A static CV cannot answer follow-up questions, explain context, or adapt the level of detail to a recruiter's needs. Generic chatbots create a different problem: they may produce plausible but unsupported claims.

KnowMe addresses both issues by combining a recruiter-facing interface with bounded candidate material and explicit answer controls.

## Current capabilities

- recruiter-style questions through a public web interface;
- grounded answers based on CV and STAR source material;
- structured STAR responses when a relevant example is available;
- administrative ingestion and prompt management;
- answer caching and configurable LLM usage controls;
- operational health, readiness, and analytics endpoints;
- question-length and prohibited-request safeguards.

## Architecture

```text
Recruiter browser
      │
      ▼
Static HTML/CSS/JavaScript interface
      │
      ▼
FastAPI application
      ├── CV and STAR source material
      ├── prompt configuration
      ├── answer cache and usage controls
      └── OpenAI API
```

The application is deployed on AWS behind a web proxy. Runtime data and secrets are kept outside source control in production.

## Repository structure

```text
.
├── backend/
│   ├── app/                    # FastAPI application and configuration
│   ├── static/                 # Recruiter and admin interfaces
│   ├── data/                   # Default/source content used by the application
│   ├── requirements.txt
│   └── DEPLOYMENT_AND_ADMIN_GUIDE.md
├── tests/                      # Automated application tests
├── docs/API_REFERENCE.md       # API route summary
├── .env.example                # Local configuration template
└── LICENSE
```

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r backend/requirements.txt
cp .env.example backend/.env
```

Set the required values in `backend/.env`, then run:

```bash
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/`.

## Configuration

Required environment variables:

- `ADMIN_PASSWORD`
- `ADMIN_COOKIE_SECRET`
- `OPENAI_API_KEY` — required for live Q&A responses; without it, uncached ask requests return a service-unavailable response

Optional runtime variables:

- `ANALYTICS_SALT`
- `LLM_DAILY_TOKEN_CAP`

Static pages, health checks, and administrative surfaces can start without `OPENAI_API_KEY`, but the application's live answer capability cannot.

Never commit real credentials or production environment files.

## Privacy and security boundaries

- Administrator credentials and API keys are loaded from environment variables.
- The public interface does not expose the admin password or OpenAI key.
- Questions and optional recruiter details may be recorded for application analytics, so production logs and persistent data must be treated as personal information.
- Client IP analytics are hashed only when an analytics salt is configured.
- Candidate source material in `backend/data/` is deliberately part of this personal portfolio repository; runtime logs, caches, and production secrets are not.

## Documentation

- [`docs/API_REFERENCE.md`](docs/API_REFERENCE.md) — supported application endpoints
- [`backend/DEPLOYMENT_AND_ADMIN_GUIDE.md`](backend/DEPLOYMENT_AND_ADMIN_GUIDE.md) — AWS deployment and administration

## Project status

Active and maintained. The primary deployment is AWS; `render.yaml` remains only as a legacy deployment artefact and is not the current production path.

## Licence

Licensed under the MIT License. See [`LICENSE`](LICENSE).
