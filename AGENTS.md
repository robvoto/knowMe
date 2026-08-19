# AGENTS.md for knowMe

## Scope
- This repo is a FastAPI prototype with a static public UI, static admin UI, and file-backed data under `backend/data`.
- Keep changes small, direct, and consistent with the existing UI and route contract.

## Non-negotiables
- Do not hardcode secrets, passwords, environment-specific values, business rules, routes, selectors, labels, or scoring logic without explicit approval.
- Do not add fallbacks, silent defaults, compatibility wrappers, legacy aliases, or "just in case" behaviour unless explicitly approved for a specific reason.
- Do not keep unused, duplicate, dead, temporary, or legacy code. Remove it as part of the change once it is no longer used.
- Do not rename routes, HTML element IDs, or API response shapes unless explicitly requested.
- Do not introduce heuristic data, random filter words, sample labels, or inferred rules without asking first.
- Do not hide errors behind generic success paths. Surface missing or invalid state clearly.
- If unsure, stop and ask before changing behaviour.

## Source Of Truth
- Backend entrypoint: `backend/app/main.py`
- Shared config constants: `backend/app/config.py`
- Public UI: `backend/static/index.html`
- Admin UI: `backend/static/admin.html`
- Shared theme/styles: `backend/static/main-style.css`
- Regression tests: `tests/test_app.py`
- Deployment notes: `backend/DEPLOYMENT_AND_ADMIN_GUIDE.md`

## Environment
- `ADMIN_PASSWORD` is required.
- `ADMIN_COOKIE_SECRET` is required.
- Treat missing required env vars as a visible startup failure.
- Keep any other env-based behavior explicit.

## Change Rules
- Centralise reused values in one place.
- Prefer the existing theme and language across the app.
- Keep route and payload contracts stable.
- Preserve missing-content failures as visible failures.
- Challenge UI or data changes that introduce inconsistency or unnecessary complexity.

## Test Strategy
- Run only tests related to the change unless a full pass is clearly needed.
- For backend/UI regressions, prefer `python -m unittest tests.test_app`.
- Add regression tests before refactoring public behavior.
- Verify the narrowest route, asset, or response surface that changed.

## Editing Workflow
- Read existing code before editing.
- Keep comments succinct and only where they add real value.
- Use `apply_patch` for manual edits.
- Avoid broad rewrites when a targeted change is enough.

## Practical Notes
- The app serves static HTML and CSS directly from `backend/static`.
- Public UI copy should remain consistent with the current product language.
- Admin flows should stay aligned with existing labels and IDs.

## Repository text format

- All tracked text files use LF line endings. .gitattributes and .editorconfig are authoritative; do not introduce or preserve CRLF.
- Before finishing edits, run git diff --check. If a touched tracked text file is CRLF or mixed, normalize that touched file to LF without rewriting unrelated dirty work.
