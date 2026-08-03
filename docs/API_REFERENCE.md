# KnowMe API Reference

KnowMe exposes application and administration endpoints under `/api`.

## Public application

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/ask` | Submit a recruiter-style question and receive a grounded answer. |
| `GET` | `/api/status` | Return application status information. |
| `GET` | `/api/ready` | Confirm that required source content has loaded. |
| `GET` | `/api/health` | Return API health information. |
| `GET` | `/health` | Hosting-level health check retained for infrastructure compatibility. |

## Administration

Administrative routes are protected by the application's admin authentication controls.

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/ingest_cv` | Replace or update CV source content. |
| `POST` | `/api/ingest_star` | Replace or update STAR example content. |
| `GET` | `/api/admin_state` | Return the current administration state. |
| `GET` | `/api/analytics` | Return question and usage analytics. |
| `GET` | `/api/reload` | Reload source and prompt data from storage. |
| `GET` | `/api/docs` | Return the application-provided endpoint catalogue. |

## Data and privacy

Requests to `/api/ask` may record the question, optional recruiter identity fields, request metadata, and a salted hash of the client IP when `ANALYTICS_SALT` is configured. Treat production logs as personal information and restrict access accordingly.

## Compatibility

Application and automation integrations should use `/api/*`. Legacy non-API routes have been removed except for `/health`, which is retained for hosting health checks.
