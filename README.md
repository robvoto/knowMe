# knowMe
Interactive personalised CV assistant for recruiter questions.

KnowMe is a lightweight FastAPI backend with a static frontend for intelligent CV Q&A.

- Web UI: `/`
- Admin UI: `/admin`
- Backend entrypoint: `backend/app/main.py`
- Dependencies: `backend/requirements.txt`
- Production deployment: AWS-hosted service
- Legacy deployment manifest: `render.yaml`

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

- `http://127.0.0.1:8000/health` - hosting health check
- `http://127.0.0.1:8000/api/ready` - app content readiness

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

Use `/api/*` for application and automation calls. Non-API legacy routes have been removed except `/health`, which is kept for hosting health checks.

Use `/api/docs` to discover the available agent endpoints and their purpose.

## Documentation

See `backend/DEPLOYMENT_AND_ADMIN_GUIDE.md` for deployment, admin operations, logging, and normalization details.

The app is deployed on AWS at `knowme.robvoto.com`. Legacy Render configuration is still kept in source control for reference.
