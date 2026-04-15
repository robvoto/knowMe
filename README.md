# knowMe
Interactive personalised CV assistant for recruiter questions.

KnowMe is a lightweight FastAPI backend with a static frontend for intelligent CV Q&A.

- Web UI: `/`
- Admin UI: `/admin`
- Backend entrypoint: `backend/app/main.py`
- Dependencies: `backend/requirements.txt`

## Local development

From the repository root, change into the backend folder:

```bash
cd backend
```

Install dependencies once:

```bash
pip install -r requirements.txt
```

Start the server locally:

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open the app in your browser:

- Public UI: `http://127.0.0.1:8000/`
- Admin UI: `http://127.0.0.1:8000/admin`

Health and readiness checks:

- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/ready`

Agent-friendly API endpoints:

- `POST http://127.0.0.1:8000/api/ingest_cv`
- `POST http://127.0.0.1:8000/api/ingest_star`
- `POST http://127.0.0.1:8000/api/ask`
- `GET  http://127.0.0.1:8000/api/admin_state`
- `GET  http://127.0.0.1:8000/api/analytics`
- `GET  http://127.0.0.1:8000/api/reload`
- `GET  http://127.0.0.1:8000/api/status`
- `GET  http://127.0.0.1:8000/api/ready`
- `GET  http://127.0.0.1:8000/api/health`
- `GET  http://127.0.0.1:8000/api/docs`

These endpoints mirror the existing admin and ask behavior with a cleaner `/api` contract for automation.

Use `/api/docs` to discover the available agent endpoints and their purpose.

## Documentation

See `backend/DEPLOYMENT_AND_ADMIN_GUIDE.md` for deployment, Render configuration, admin operations, logging, and normalization details.

The root-level `render.yaml` file is a Render manifest that tells Render how to build and run the app automatically from this repo. It stores the service configuration in source control, including the branch, root directory, Python build command, server start command, and health check path.
