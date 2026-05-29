r"""
KnowMe Backend API

HOW TO RUN (Command Prompt):
---------------------------
1. Navigate to the project root:
   cd /d E:\Programming\knowRob\knowMe
2. Activate the virtual environment:
   .venv\Scripts\activate
3. Run the application:
   set PYTHONPATH=.
   python -m backend.app.main
4. python -m unittest tests.test_app
"""
import os
import re
import json
import mimetypes
import hashlib
import time
import uuid
import secrets
import sys
from pathlib import Path
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from urllib.parse import urlparse
import uvicorn
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from openai import OpenAI
from typing import TypedDict

from .config import (
    ADMIN_COOKIE_NAME,
    BACKEND_DIR,
    CV_FILE,
    DATA_DIR,
    MAX_QUESTION_CHARS,
    QUESTION_EVENT_LOG_FILE,
    ANSWER_CACHE_FILE,
    QUESTION_LOG_FILE,
    STAR_FILE,
    STATIC_DIR,
    UNKNOWN_LOG_VALUES,
)

type FileMetadata = dict[str, str | int | float | bool]
type LlmBudgetStatus = dict[str, str | int | FileMetadata]


class LlmIdentityRecord(TypedDict, total=False):
    last_ts: float


class LlmDayState(TypedDict):
    tokens_used: int
    identities: dict[str, LlmIdentityRecord]


LlmUsageState = dict[str, LlmDayState]

# ------------------------
# Time helpers
# ------------------------

def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_today_key() -> str:
    return utc_now().date().isoformat()


CV_TEXT = ""
STAR_TEXT = ""
ANSWER_CACHE: dict[str, dict[str, object]] = {}

load_dotenv(BACKEND_DIR / ".env")

ANALYTICS_SALT = os.getenv("ANALYTICS_SALT", "").strip()


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required.")
    return value


def loud_warning(message: str) -> None:
    print(f"WARNING: {message}", file=sys.stderr)


def log_info(message: str) -> None:
    print(f"INFO: {message}")


ADMIN_PASSWORD = require_env("ADMIN_PASSWORD")
ADMIN_COOKIE_SECRET = require_env("ADMIN_COOKIE_SECRET")

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ------------------------
# Lifespan (startup)
# ------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    load_all_data()
    startup_checkup()
    yield


app = FastAPI(title="knowMe API", lifespan=lifespan)
mimetypes.add_type("application/javascript", ".js")

# ------------------------
# Data loading
# ------------------------

def save_text_file(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    log_info(f"Saving text file: {path} ({len(text)} chars)")
    path.write_text(text, encoding="utf-8")
    log_info(f"Saved text file: {path}")


def load_text_file(path: Path) -> str:
    if not path.exists():
        message = f"Required data file missing: {path}"
        loud_warning(message)
        raise RuntimeError(message)
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        message = f"Required data file is empty: {path}"
        loud_warning(message)
        raise RuntimeError(message)
    log_info(f"Loaded text file: {path} ({len(text)} chars)")
    return text


def get_file_metadata(path: Path) -> FileMetadata:
    if not path.exists():
        return {"exists": False, "path": str(path), "size": 0, "modified": 0}
    stat = path.stat()
    return {"exists": True, "path": str(path), "size": stat.st_size, "modified": stat.st_mtime}


def load_all_data():
    global CV_TEXT, STAR_TEXT, PROMPT_OVERRIDES, ANSWER_CACHE
    log_info("Loading in-memory backend data from disk.")
    CV_TEXT = load_text_file(CV_FILE)
    STAR_TEXT = load_text_file(STAR_FILE)
    PROMPT_OVERRIDES = load_prompt_overrides()
    ANSWER_CACHE = load_answer_cache()
    log_info(f"Loaded CV={len(CV_TEXT)} chars, STAR={len(STAR_TEXT)} chars.")


def startup_checkup():
    print("\n" + "=" * 60)
    print("knowMe startup checkup")
    print("=" * 60)
    print(f"CWD: {os.getcwd()}")
    print(f"CV file:   {CV_FILE.resolve()}  exists={CV_FILE.exists()}")
    print(f"STAR file: {STAR_FILE.resolve()} exists={STAR_FILE.exists()}")
    print(f"Loaded CV chars:   {len(CV_TEXT)}")
    print(f"Loaded STAR chars: {len(STAR_TEXT)}")
    print(f"Loaded answer cache entries: {len(ANSWER_CACHE)}")
    print("=" * 60 + "\n")

# ------------------------
# Logging helpers
# ------------------------

def normalize_log_identity(value: str | None) -> str:
    text = (value or "").strip()
    return text if text else "-"


def is_meaningful_log_value(value: str | None) -> bool:
    return normalize_log_identity(value).lower() not in UNKNOWN_LOG_VALUES


def sanitize_log_value(value: str | None) -> str:
    text = normalize_log_identity(value)
    text = text.replace("\r", " ").replace("\n", " ").replace("|", "/")
    return re.sub(r"\s+", " ", text).strip() or "-"


def hash_analytics_value(value: str | None) -> str | None:
    text = (value or "").strip()
    if not text or not ANALYTICS_SALT:
        return None
    digest = hashlib.sha256(f"{ANALYTICS_SALT}:{text}".encode("utf-8")).hexdigest()
    return digest[:16]


def extract_client_ip(request: Request) -> str | None:
    if request.client and request.client.host:
        return request.client.host.strip() or None
    return None


def derive_source_page(source_page: str | None, source_path: str | None) -> str:
    if is_meaningful_log_value(source_page):
        return normalize_log_identity(source_page)
    path = (source_path or "").strip()
    if path == "/admin":
        return "admin"
    if path == "/":
        return "landing"
    return path if path else "-"


def build_logging_context(request: Request, payload: dict) -> dict[str, str]:
    referer = (request.headers.get("referer") or "").strip()
    referer_path = urlparse(referer).path.strip() if referer else ""
    source_path = normalize_log_identity(payload.get("source_path") or referer_path)
    source_page = derive_source_page(payload.get("source_page"), source_path if source_path != "-" else "")
    return {
        "request_id": normalize_log_identity(payload.get("request_id")) if is_meaningful_log_value(payload.get("request_id")) else uuid.uuid4().hex,
        "client_id": normalize_log_identity(payload.get("client_id")),
        "session_id": normalize_log_identity(payload.get("session_id")),
        "request_path": sanitize_log_value(str(request.url.path)),
        "source_path": sanitize_log_value(source_path),
        "source_page": sanitize_log_value(source_page),
        "referer": sanitize_log_value(referer),
        "user_agent": sanitize_log_value(request.headers.get("user-agent")),
        "client_ip_hash": sanitize_log_value(hash_analytics_value(extract_client_ip(request))),
    }


def log_question(question: str, name: str | None, company: str | None, metadata: dict[str, str]):
    QUESTION_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    fields = {
        "request_id": metadata.get("request_id", "-"),
        "client_id": metadata.get("client_id", "-"),
        "session_id": metadata.get("session_id", "-"),
        "request_path": metadata.get("request_path", "-"),
        "source_page": metadata.get("source_page", "-"),
        "source_path": metadata.get("source_path", "-"),
        "client_ip_hash": metadata.get("client_ip_hash", "-"),
        "name": normalize_log_identity(name),
        "company": normalize_log_identity(company),
        "q": question,
    }
    row = f"{utc_now().isoformat()} | " + " | ".join(
        f"{key}={sanitize_log_value(value)}" for key, value in fields.items()
    )
    with QUESTION_LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(row + "\n")
    log_info(f"Logged question: {question[:80]} -> {QUESTION_LOG_FILE}")
    log_question_event(question, name, company, metadata)


def log_question_event(question: str, name: str | None, company: str | None, metadata: dict[str, str]):
    event = {
        "ts": utc_now().isoformat(),
        "question": question,
        "name": normalize_log_identity(name),
        "company": normalize_log_identity(company),
        "identity_provided": any(is_meaningful_log_value(v) for v in (name, company)),
    }
    event.update(metadata)
    QUESTION_EVENT_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with QUESTION_EVENT_LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")

# ------------------------
# Analytics
# ------------------------

def parse_question_log_line(line: str) -> dict[str, str]:
    parts = [part.strip() for part in line.split("|") if part.strip()]
    record = {"raw": line}
    if parts:
        record["ts"] = parts[0]
    for part in parts[1:]:
        if "=" in part:
            key, value = part.split("=", 1)
            record[key.strip()] = value.strip()
    return record


def read_question_log() -> list[dict[str, str]]:
    if not QUESTION_LOG_FILE.exists():
        return []
    with QUESTION_LOG_FILE.open("r", encoding="utf-8") as f:
        records = [parse_question_log_line(line) for line in f if line.strip()]
    log_info(f"Loaded question log: {QUESTION_LOG_FILE} ({len(records)} records)")
    return records


def analytics_summary() -> dict:
    question_records = read_question_log()
    source_counts: dict[str, int] = {}
    for rec in question_records:
        source_page = rec.get("source_page", "-")
        if source_page:
            source_counts[source_page] = source_counts.get(source_page, 0) + 1

    recent_questions = [
        {
            "ts": rec.get("ts", ""),
            "question": rec.get("q", ""),
            "name": rec.get("name", "-"),
            "company": rec.get("company", "-"),
            "request_id": rec.get("request_id", "-"),
            "client_id": rec.get("client_id", "-"),
            "session_id": rec.get("session_id", "-"),
            "source_page": rec.get("source_page", "-"),
            "source_path": rec.get("source_path", "-"),
            "request_path": rec.get("request_path", "-"),
            "client_ip_hash": rec.get("client_ip_hash", "-"),
        }
        for rec in question_records[-10:]
    ][::-1]

    unique_client_ids = {rec.get("client_id", "").strip() for rec in question_records if is_meaningful_log_value(rec.get("client_id"))}
    unique_session_ids = {rec.get("session_id", "").strip() for rec in question_records if is_meaningful_log_value(rec.get("session_id"))}
    unique_ip_hashes = {rec.get("client_ip_hash", "").strip() for rec in question_records if is_meaningful_log_value(rec.get("client_ip_hash"))}
    named_question_count = sum(1 for rec in question_records if any(is_meaningful_log_value(rec.get(f)) for f in ("name", "company")))

    return {
        "question_count": len(question_records),
        "named_question_count": named_question_count,
        "anonymous_question_count": len(question_records) - named_question_count,
        "unique_client_count": len(unique_client_ids),
        "unique_session_count": len(unique_session_ids),
        "unique_hashed_ip_count": len(unique_ip_hashes),
        "hashed_ip_enabled": bool(ANALYTICS_SALT),
        "source_page_counts": [{"source_page": s, "count": c} for s, c in sorted(source_counts.items(), key=lambda x: x[1], reverse=True)],
        "recent_questions": recent_questions,
        # kept for admin UI compatibility — no longer populated
        "top_canonical_questions": [],
        "top_normalized_questions": [],
        "intent_counts": [],
        "intent_event_count": 0,
    }

# ------------------------
# LLM
# ------------------------

BASE_SYSTEM_PROMPT = (
    "You answer recruiter questions about candidate Rob Voto based strictly on the supplied CV and STAR examples. "
    "Every claim must be anchored to a specific organisation and time period from the CV. "
    "Do not invent or infer experience not in the supplied text. "
    "\n\n"
    "RULE — EXAMPLE OR STORY QUESTIONS: "
    "When the question asks for an example, a story, a time when, a situation, a challenge, a result, or uses phrases like "
    "'give an example', 'tell me about a time', 'describe a situation', 'walk me through', 'concrete example', or 'STAR', "
    "you MUST look in the STAR EXAMPLES section first. "
    "Find the most relevant EXAMPLE block and present it using these exact headings: "
    "Situation, Task, Action, Result. "
    "Each section should be 2-4 sentences drawn directly from the STAR block. "
    "Do not summarise into bullets. Do not pad with generic skill claims from the CV body. "
    "If multiple STAR blocks are relevant, pick the best one unless the question asks for more than one. "
    "\n\n"
    "RULE — INDUSTRY OR SECTOR QUESTIONS: "
    "List ALL relevant organisations with their sector or domain. Do not stop early. "
    "\n\n"
    "RULE — GENERAL QUESTIONS: "
    "Lead with the most recent and directly relevant experience. "
    "Keep answers concise and recruiter-focused unless asked for more detail. "
    "\n\n"
    "If the answer is not in the supplied text, say exactly: 'I can't find that in the CV text I was given.'"
)

PROMPT_CONFIG_PATH = DATA_DIR / "prompt_config.json"
PROMPT_OVERRIDE_KEYS = ("base", "industry", "fit", "star", "bpmn", "tools", "ai", "detail")
PROMPT_OVERRIDES: dict[str, str] = {key: "" for key in PROMPT_OVERRIDE_KEYS}

LLM_MODEL = "gpt-4.1-mini"
LLM_MAX_OUTPUT_TOKENS = 500
LLM_CALL_COOLDOWN_SECONDS = 10
LLM_DAILY_TOKEN_CAP = int(os.getenv("LLM_DAILY_TOKEN_CAP", "50000"))
LLM_USAGE_PATH = DATA_DIR / "llm_usage.json"


def load_prompt_overrides() -> dict[str, str]:
    if not PROMPT_CONFIG_PATH.exists():
        loud_warning(f"Prompt config missing; using empty overrides: {PROMPT_CONFIG_PATH}")
        return {key: "" for key in PROMPT_OVERRIDE_KEYS}
    try:
        raw = json.loads(PROMPT_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        loud_warning(f"Prompt config unreadable; using empty overrides: {exc}")
        return {key: "" for key in PROMPT_OVERRIDE_KEYS}
    if not isinstance(raw, dict):
        return {key: "" for key in PROMPT_OVERRIDE_KEYS}
    return {
        key: raw.get(key, "").strip() if isinstance(raw.get(key, ""), str) else ""
        for key in PROMPT_OVERRIDE_KEYS
    }


def save_prompt_overrides(overrides: dict[str, str]) -> None:
    PROMPT_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROMPT_CONFIG_PATH.write_text(json.dumps(overrides, ensure_ascii=False, indent=2), encoding="utf-8")
    log_info(f"Saved prompt overrides: {PROMPT_CONFIG_PATH}")


def active_system_prompt() -> str:
    return PROMPT_OVERRIDES.get("base") or BASE_SYSTEM_PROMPT


def hash_cache_payload(payload: object) -> str:
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def normalize_cached_question(question: str) -> str:
    return re.sub(r"\s+", " ", question.strip()).lower()


def build_answer_cache_key(question: str, detail_level: str) -> str:
    return hash_cache_payload({
        "version": 1,
        "question": normalize_cached_question(question),
        "detail_level": detail_level,
        "model": LLM_MODEL,
        "cv_hash": hashlib.sha256(CV_TEXT.encode("utf-8")).hexdigest(),
        "star_hash": hashlib.sha256(STAR_TEXT.encode("utf-8")).hexdigest(),
        "prompt": active_system_prompt(),
    })


def get_cached_answer(question: str, detail_level: str) -> dict[str, object] | None:
    return ANSWER_CACHE.get(build_answer_cache_key(question, detail_level))


def store_cached_answer(question: str, detail_level: str, answer: str, tokens_used: int) -> None:
    cache_key = build_answer_cache_key(question, detail_level)
    ANSWER_CACHE[cache_key] = {
        "answer": answer,
        "tokens_used": tokens_used,
        "cached_at": utc_now().isoformat(),
    }
    save_answer_cache(ANSWER_CACHE)


def load_answer_cache() -> dict[str, dict[str, object]]:
    if not ANSWER_CACHE_FILE.exists():
        log_info(f"Answer cache missing; starting empty cache: {ANSWER_CACHE_FILE}")
        return {}
    try:
        raw = json.loads(ANSWER_CACHE_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        loud_warning(f"Answer cache unreadable; starting empty cache: {exc}")
        return {}
    if not isinstance(raw, dict):
        loud_warning(f"Answer cache has invalid format; starting empty cache: {ANSWER_CACHE_FILE}")
        return {}
    entries: dict[str, dict[str, object]] = {}
    for key, value in raw.items():
        if isinstance(key, str) and isinstance(value, dict) and isinstance(value.get("answer"), str):
            entries[key] = value
    log_info(f"Loaded answer cache: {ANSWER_CACHE_FILE} ({len(entries)} entries)")
    return entries


def save_answer_cache(state: dict[str, dict[str, object]]) -> None:
    ANSWER_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    ANSWER_CACHE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    log_info(f"Saved answer cache: {ANSWER_CACHE_FILE} ({len(state)} entries)")


def load_llm_usage() -> LlmUsageState:
    if not LLM_USAGE_PATH.exists():
        return {}
    try:
        raw = json.loads(LLM_USAGE_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        loud_warning(f"LLM usage file unreadable: {exc}")
        return {}
    if not isinstance(raw, dict):
        return {}
    state: LlmUsageState = {}
    for key, value in raw.items():
        state[key] = normalize_llm_day_state(value)
    return state


def save_llm_usage(state: LlmUsageState) -> None:
    LLM_USAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    LLM_USAGE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def coerce_int(value: object, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def normalize_llm_day_state(day_state: object) -> LlmDayState:
    if not isinstance(day_state, dict):
        return {"tokens_used": 0, "identities": {}}
    identities: dict[str, LlmIdentityRecord] = {}
    raw_identities: object = day_state.get("identities")
    if isinstance(raw_identities, dict):
        for key, value in raw_identities.items():
            if isinstance(key, str) and isinstance(value, dict):
                record: LlmIdentityRecord = {}
                last_ts: object = value.get("last_ts")
                if isinstance(last_ts, (int, float)) and not isinstance(last_ts, bool):
                    record["last_ts"] = float(last_ts)
                identities[key] = record
    tokens_used: object = day_state.get("tokens_used", 0)
    return {
        "tokens_used": coerce_int(tokens_used),
        "identities": identities,
    }


def get_rate_limit_identity(logging_context: dict[str, str]) -> str:
    for key, prefix in (("client_id", "client"), ("client_ip_hash", "ip"), ("session_id", "session")):
        value = logging_context.get(key, "")
        if is_meaningful_log_value(value):
            return f"{prefix}:{value}"
    return f"request:{logging_context.get('request_id', '-')}"


def is_admin_session(request: Request) -> bool:
    token = request.cookies.get(ADMIN_COOKIE_NAME, "")
    return bool(token) and secrets.compare_digest(token, build_admin_cookie())


def get_llm_budget_status() -> LlmBudgetStatus:
    today = utc_today_key()
    state = load_llm_usage()
    day_state = normalize_llm_day_state(state.get(today))
    used = coerce_int(day_state["tokens_used"])
    return {
        "day": today,
        "daily_cap": LLM_DAILY_TOKEN_CAP,
        "tokens_used": used,
        "tokens_remaining": max(0, LLM_DAILY_TOKEN_CAP - used),
        "budget_file": get_file_metadata(LLM_USAGE_PATH),
    }


def record_llm_usage(logging_context: dict[str, str], tokens_used: int) -> None:
    if tokens_used <= 0:
        return
    today = utc_today_key()
    state: LlmUsageState = load_llm_usage()
    day_state: LlmDayState = normalize_llm_day_state(state.get(today))
    identities: dict[str, LlmIdentityRecord] = day_state["identities"]
    identity = get_rate_limit_identity(logging_context)
    identity_state: LlmIdentityRecord = identities.get(identity) or {}
    identity_state["last_ts"] = time.time()
    identities[identity] = identity_state
    day_state["identities"] = identities
    day_state["tokens_used"] = coerce_int(day_state["tokens_used"]) + tokens_used
    state[today] = day_state
    save_llm_usage(state)


def enforce_llm_rate_limit(request: Request, logging_context: dict[str, str]) -> None:
    if is_admin_session(request):
        return

    today = utc_today_key()
    now = time.time()
    state: LlmUsageState = load_llm_usage()
    day_state: LlmDayState = normalize_llm_day_state(state.get(today))
    identities: dict[str, LlmIdentityRecord] = day_state["identities"]
    identity = get_rate_limit_identity(logging_context)
    record: LlmIdentityRecord = identities.get(identity) or {}

    last_ts = float(record.get("last_ts", 0.0) or 0.0)
    if last_ts and now - last_ts < LLM_CALL_COOLDOWN_SECONDS:
        wait_seconds = max(1, int(LLM_CALL_COOLDOWN_SECONDS - (now - last_ts) + 0.5))
        raise HTTPException(
            status_code=429,
            detail=f"Please wait {wait_seconds} seconds before asking again.",
            headers={"Retry-After": str(wait_seconds)},
        )

    used = coerce_int(day_state["tokens_used"])
    if used >= LLM_DAILY_TOKEN_CAP:
        raise HTTPException(
            status_code=429,
            detail="AI is paused for today — daily limit reached. Try again tomorrow.",
            headers={"Retry-After": "86400"},
        )

    record["last_ts"] = now
    identities[identity] = record
    day_state["identities"] = identities
    state[today] = day_state
    save_llm_usage(state)


def llm_answer(question: str, detail_level: str = "concise") -> tuple[str, int]:
    context_parts = [CV_TEXT]
    if STAR_TEXT:
        context_parts.append("STAR EXAMPLES:\n" + STAR_TEXT)
    context = "\n\n".join(context_parts)

    detail_instruction = (
        " Provide one additional concrete example or evidence point from a different role when the material supports it."
        if detail_level == "detailed"
        else ""
    )

    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OpenAI API key is not configured.")

    start = time.time()
    print(f"[{datetime.now().strftime('%H:%M:%S')}] LLM: calling {LLM_MODEL}...")

    resp = client.responses.create(
        model=LLM_MODEL,
        instructions=(
            active_system_prompt()
            + "\n\nAnswer as recruiter-friendly prose. No bullet points or headings unless the question asks for a list."
            + detail_instruction
        ),
        input=f"Question: {question}\n\nCV AND STAR TEXT:\n{context}",
        temperature=0.2,
        max_output_tokens=LLM_MAX_OUTPUT_TOKENS,
    )

    elapsed = time.time() - start
    usage = getattr(resp, "usage", None)
    tokens_used = 0
    if usage:
        in_t = coerce_int(getattr(usage, "input_tokens", 0))
        out_t = coerce_int(getattr(usage, "output_tokens", 0))
        tokens_used = in_t + out_t
        cost = (in_t * 0.00000015) + (out_t * 0.0000006)
        print(f"[{datetime.now().strftime('%H:%M:%S')}] LLM: {elapsed:.2f}s | {in_t}in {out_t}out | ${cost:.6f}")
    else:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] LLM: {elapsed:.2f}s (usage unavailable)")

    final_text = (resp.output_text or "").strip()
    if not final_text:
        raise RuntimeError("OpenAI returned an empty response.")
    return final_text, tokens_used

# ------------------------
# Admin auth
# ------------------------

def build_admin_cookie() -> str:
    return hashlib.sha256(f"{ADMIN_COOKIE_SECRET}:admin".encode("utf-8")).hexdigest()


def require_admin_auth(request: Request) -> None:
    token = request.cookies.get(ADMIN_COOKIE_NAME, "")
    if not token or not secrets.compare_digest(token, build_admin_cookie()):
        raise HTTPException(status_code=401, detail="Admin login required.")

# ------------------------
# Static / UI
# ------------------------

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def home():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/admin")
def admin():
    return FileResponse(
        STATIC_DIR / "admin.html",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
    )


@app.get("/designs")
def designs():
    return FileResponse(STATIC_DIR / "designs.html")


@app.get("/health")
def health():
    return {"ok": True}


def ready():
    return {
        "ok": bool(CV_TEXT),
        "cv_loaded": bool(CV_TEXT),
        "star_loaded": bool(STAR_TEXT),
        "cv_length": len(CV_TEXT),
        "star_length": len(STAR_TEXT),
    }


def status():
    return {
        "cv_loaded": bool(CV_TEXT),
        "star_loaded": bool(STAR_TEXT),
        "cv_length": len(CV_TEXT),
        "star_length": len(STAR_TEXT),
    }

# ------------------------
# Admin endpoints
# ------------------------

@app.post("/api/admin_login")
def api_admin_login(payload: dict, response: Response):
    if not ADMIN_PASSWORD:
        raise HTTPException(status_code=503, detail="Admin password is not configured.")
    password = (payload.get("password") or "").strip()
    if not password or not secrets.compare_digest(password, ADMIN_PASSWORD):
        raise HTTPException(status_code=401, detail="Invalid admin password.")
    log_info("Admin login succeeded.")
    response.set_cookie(
        key=ADMIN_COOKIE_NAME,
        value=build_admin_cookie(),
        httponly=True,
        samesite="strict",
        secure=False,
        max_age=60 * 60 * 8,
    )
    return {"ok": True}


@app.post("/api/admin_logout")
def api_admin_logout(response: Response):
    log_info("Admin logout requested.")
    response.delete_cookie(ADMIN_COOKIE_NAME)
    return {"ok": True}


def analytics():
    return analytics_summary()


def admin_state():
    log_info("Admin state requested.")
    return {
        "cv_loaded": bool(CV_TEXT),
        "star_loaded": bool(STAR_TEXT),
        "cv_length": len(CV_TEXT),
        "star_length": len(STAR_TEXT),
        "cv_text": CV_TEXT,
        "star_text": STAR_TEXT,
        "llm_budget": get_llm_budget_status(),
        "prompt_overrides": PROMPT_OVERRIDES,
        "prompt_config_file": get_file_metadata(PROMPT_CONFIG_PATH),
        "cv_file": get_file_metadata(CV_FILE),
        "star_file": get_file_metadata(STAR_FILE),
    }


@app.get("/api/admin_state", dependencies=[Depends(require_admin_auth)])
def api_admin_state():
    return admin_state()


@app.get("/api/admin_prompts", dependencies=[Depends(require_admin_auth)])
def api_admin_prompts_get():
    log_info("Prompt bundle requested.")
    return {
        "defaults": {
            "base": BASE_SYSTEM_PROMPT,
            "industry": "",
            "fit": "",
            "star": "",
            "bpmn": "",
            "tools": "",
            "ai": "",
            "detail": "",
        },
        "overrides": PROMPT_OVERRIDES,
        "active": {key: PROMPT_OVERRIDES.get(key, "") for key in PROMPT_OVERRIDE_KEYS},
    }


@app.post("/api/admin_prompts", dependencies=[Depends(require_admin_auth)])
def api_admin_prompts_post(payload: dict):
    global PROMPT_OVERRIDES
    incoming = payload.get("overrides", {})
    if not isinstance(incoming, dict):
        raise HTTPException(status_code=400, detail="Invalid prompt overrides payload.")
    next_overrides = {key: "" for key in PROMPT_OVERRIDE_KEYS}
    for key in PROMPT_OVERRIDE_KEYS:
        value = incoming.get(key, "")
        if isinstance(value, str):
            next_overrides[key] = value.strip()
    PROMPT_OVERRIDES = next_overrides
    save_prompt_overrides(PROMPT_OVERRIDES)
    return {"ok": True, "overrides": PROMPT_OVERRIDES}


@app.get("/api/analytics", dependencies=[Depends(require_admin_auth)])
def api_analytics():
    return analytics_summary()


@app.get("/api/reload", dependencies=[Depends(require_admin_auth)])
def api_reload():
    return reload_files()


@app.get("/api/status")
def api_status():
    return status()


@app.get("/api/ready")
def api_ready():
    return ready()


@app.get("/api/health")
def api_health():
    return {"ok": True, "service": "knowMe agent API", "version": "2.0"}


@app.get("/api/docs")
def api_docs():
    return {
        "service": "knowMe agent API",
        "version": "2.0",
        "description": "CV Q&A backed by full-text LLM — no heuristic retrieval.",
        "endpoints": [
            {"method": "GET", "path": "/api/ready"},
            {"method": "GET", "path": "/api/status"},
            {"method": "GET", "path": "/api/admin_state"},
            {"method": "GET", "path": "/api/analytics"},
            {"method": "GET", "path": "/api/reload"},
            {"method": "POST", "path": "/api/ingest_cv"},
            {"method": "POST", "path": "/api/ingest_star"},
            {"method": "POST", "path": "/api/ask"},
        ],
    }


@app.post("/api/ingest_cv", dependencies=[Depends(require_admin_auth)])
def api_ingest_cv(payload: dict):
    return ingest_cv(payload)


@app.post("/api/ingest_star", dependencies=[Depends(require_admin_auth)])
def api_ingest_star(payload: dict):
    return ingest_star(payload)


@app.post("/api/ask")
def api_ask(payload: dict, request: Request):
    return ask(payload, request)

# ------------------------
# Core routes
# ------------------------

def ingest_cv(payload: dict):
    global CV_TEXT
    text = payload.get("text", "")
    if not text:
        return {"error": "No CV text provided"}
    log_info(f"Ingesting CV text ({len(text)} chars).")
    save_text_file(CV_FILE, text)
    CV_TEXT = text
    return {"status": "CV stored", "length": len(CV_TEXT)}


def ingest_star(payload: dict):
    global STAR_TEXT
    text = payload.get("text", "")
    if not text:
        return {"error": "No STAR text provided"}
    log_info(f"Ingesting STAR text ({len(text)} chars).")
    save_text_file(STAR_FILE, text)
    STAR_TEXT = text
    return {"status": "STAR stored", "length": len(STAR_TEXT)}


def reload_files():
    log_info("Reload requested: refreshing backend data from disk.")
    load_all_data()
    startup_checkup()
    log_info("Reload complete.")
    return {
        "status": "reloaded",
        "cv_length": len(CV_TEXT),
        "star_length": len(STAR_TEXT),
    }


def ask(payload: dict, request: Request):
    question = payload.get("question", "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="Please type a question.")

    print(f"\n--- Ask: '{question[:80]}' ---")

    if len(question) > MAX_QUESTION_CHARS:
        loud_warning(f"Rejected: question exceeded {MAX_QUESTION_CHARS} chars.")
        return {"answer": f"Please shorten your question to under {MAX_QUESTION_CHARS} characters."}

    if not CV_TEXT:
        loud_warning("Rejected: CV_TEXT not loaded.")
        return {"answer": "No CV loaded yet."}

    use_llm = bool(payload.get("use_llm", True))
    if not use_llm:
        return {
            "answer": "Enable 'Use AI rewrite' to get an answer.",
            "answer_source": "none",
        }

    detail_level = payload.get("detail_level", "concise")
    name = payload.get("name")
    company = payload.get("company")
    logging_context = build_logging_context(request, payload)
    log_question(question, name, company, logging_context)

    cached_entry = get_cached_answer(question, detail_level)
    if cached_entry:
        cached_answer = cached_entry.get("answer", "")
        if isinstance(cached_answer, str) and cached_answer.strip():
            log_info(f"Answer cache hit for question: {question[:80]}")
            print("  > Done. 0 tokens (cache hit).")
            return {
                "answer": cached_answer,
                "answer_source": "llm",
                "request_id": logging_context["request_id"],
            }

    try:
        enforce_llm_rate_limit(request, logging_context)
        answer, tokens_used = llm_answer(question, detail_level)
        record_llm_usage(logging_context, tokens_used)
        store_cached_answer(question, detail_level, answer, tokens_used)
    except HTTPException:
        raise
    except Exception as exc:
        loud_warning(f"LLM call failed: {exc}")
        raise HTTPException(status_code=503, detail=f"AI answer failed: {exc}")

    print(f"  > Done. {tokens_used} tokens.")
    return {
        "answer": answer,
        "answer_source": "llm",
        "request_id": logging_context["request_id"],
    }


if __name__ == "__main__":
    print("\nStarting KnowMe server at http://localhost:8000 ...")
    uvicorn.run("backend.app.main:app", host="0.0.0.0", port=8000, reload=True)
