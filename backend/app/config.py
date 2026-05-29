"""
KnowMe application configuration.

Created: 2026-05-29
Created by: ChatGPT / OpenAI, with Rob Voto

Purpose:
Centralise stable filesystem paths and application constants so the FastAPI
entrypoint can be refactored safely without changing runtime behaviour.

Rules:
- Do not put business logic here.
- Do not add silent fallback behaviour here.
- Keep route paths and response contracts defined in the route layer.
"""
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
BACKEND_DIR = APP_DIR.parent
STATIC_DIR = BACKEND_DIR / "static"
DATA_DIR = BACKEND_DIR / "data"
CV_FILE = DATA_DIR / "cv.txt"
STAR_FILE = DATA_DIR / "star.txt"
QUESTION_LOG_FILE = DATA_DIR / "questions.log"
QUESTION_EVENT_LOG_FILE = DATA_DIR / "question_events.jsonl"
ANSWER_CACHE_FILE = DATA_DIR / "answer_cache.json"

MAX_QUESTION_CHARS = 300
UNKNOWN_LOG_VALUES = {"", "-", "unknown"}
ADMIN_COOKIE_NAME = "knowme_admin"
