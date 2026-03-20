import string
import os
import json
from pathlib import Path
from datetime import datetime
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from openai import OpenAI

# ─────────────────────────
# Globals / config
# ─────────────────────────
APP_DIR = Path(__file__).resolve().parent
BACKEND_DIR = APP_DIR.parent
STATIC_DIR = BACKEND_DIR / "static"
DATA_DIR = BACKEND_DIR / "data"
CV_FILE = DATA_DIR / "cv.txt"
STAR_FILE = DATA_DIR / "star.txt"
QUESTION_LOG_FILE = DATA_DIR / "questions.log"

TOP_QUESTIONS = 20
MAX_QUESTION_CHARS = 300
MIN_LINE_LENGTH = 25

IMPORTANT_SHORT_WORDS = {
    "api", 
    "sql", 
    "aws", 
    "etl", 
    "bi", 
    "ux", 
    "ui", 
    "dev", 
    "pm"
}

SEARCH_TERM_ALIASES = {
    "located": ["location"],
    "location": ["located"],
    "where": ["location"],
    "industries": ["industry"],
    "departments": ["department"],
    "tools": ["tool", "technology", "technologies"],
    "technology": ["tools"],
    "technologies": ["tools"],
}

STAR_TRIGGER_PHRASES = [
    "star",
    "tell me about a time",
    "describe a situation",
    "give an example",
    "give examples",
    "example",
    "scenario",
]

AUTHORITATIVE_MARKER = "AUTHORITATIVE CV INFORMATION (SOURCE OF TRUTH)"
EMPLOYMENT_HISTORY_MARKER = "EMPLOYMENT HISTORY"

CV_AUTHORITATIVE = ""
CV_BODY = ""
STAR_TEXT = ""

load_dotenv(BACKEND_DIR / ".env")

INTENT_LOG_PATH = Path(DATA_DIR / "intent_log.jsonl")

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ─────────────────────────
# Lifespan (startup)
# ─────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    load_all_data()
    startup_checkup()
    yield


app = FastAPI(title="knowMe API", lifespan=lifespan)


# ─────────────────────────
# Helpers
# ─────────────────────────

def save_text_file(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")

def clean_line(text: str) -> str:
    return text.lstrip("•-– ").strip()


def load_text_file(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def log_intent_event(
    question: str,
    requested_star: bool,
    included_star: bool,
    star_example_id: str | None,
    reason: str,
):
    event = {
        "ts": datetime.utcnow().isoformat(),
        "question": question,
        "requested_star": requested_star,
        "included_star": included_star,
        "star_example_id": star_example_id,
        "reason": reason,
    }
    INTENT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with INTENT_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")

def split_authoritative(cv_text: str):
    """
    Prefer an explicit AUTHORITATIVE marker when present.
    Otherwise, treat the profile/tools block before employment history as authoritative.
    BODY remains the full CV for retrieval.
    """
    body = cv_text.strip()
    if not body:
        return "", ""

    authoritative_source = ""

    if AUTHORITATIVE_MARKER in body:
        authoritative_source = body.split(AUTHORITATIVE_MARKER, 1)[1].strip()
    elif EMPLOYMENT_HISTORY_MARKER in body:
        authoritative_source = body.split(EMPLOYMENT_HISTORY_MARKER, 1)[0].strip()
    else:
        return "", body

    authoritative = authoritative_source.strip().strip("=\n- ")
    return authoritative, body


def load_all_data():
    global CV_AUTHORITATIVE, CV_BODY, STAR_TEXT

    cv_text = load_text_file(CV_FILE)
    STAR_TEXT = load_text_file(STAR_FILE)

    CV_AUTHORITATIVE, CV_BODY = split_authoritative(cv_text)

def count_star_blocks(star_text: str) -> int:
    # count lines that start with "EXAMPLE "
    return sum(1 for ln in star_text.splitlines() if ln.strip().startswith("EXAMPLE "))

def startup_checkup():
    cwd = os.getcwd()

    cv_file = CV_FILE.resolve()
    star_file = STAR_FILE.resolve()
    log_path = INTENT_LOG_PATH.resolve()

    cv_exists = CV_FILE.exists()
    star_exists = STAR_FILE.exists()

    print("\n" + "=" * 60)
    print("knowMe startup checkup")
    print("=" * 60)
    print(f"CWD: {cwd}")
    print(f"CV file:   {cv_file}  exists={cv_exists}")
    print(f"STAR file: {star_file} exists={star_exists}")
    print(f"Log file:  {log_path}")
    print("-" * 60)

    print(f"Loaded CV_BODY chars:          {len(CV_BODY)}")
    print(f"Loaded CV_AUTHORITATIVE chars: {len(CV_AUTHORITATIVE)}")
    print(f"Loaded STAR_TEXT chars:        {len(STAR_TEXT)}")

    # quick content checks
    cv_lower = (CV_BODY or "").lower()
    print("-" * 60)
    print(f"CV contains AUTHORITATIVE marker? {AUTHORITATIVE_MARKER in (CV_BODY or '')}")
    print(f"CV contains 'api'?                {'api' in cv_lower}")
    print(f"CV contains 'postman'?            {'postman' in cv_lower}")
    print(f"CV contains 'bpmn'?               {'bpmn' in cv_lower}")

    star_blocks = count_star_blocks(STAR_TEXT or "")
    print(f"STAR blocks detected (EXAMPLE …): {star_blocks}")

    if star_blocks == 0 and len(STAR_TEXT) > 0:
        print("WARNING: STAR loaded but no 'EXAMPLE ' headers found. Check STAR format.")
    if len(STAR_TEXT) == 0:
        print("WARNING: STAR is empty. Check backend/data/star.txt path or file contents.")

    print("=" * 60 + "\n")


def dedupe_lines(lines: list[str]) -> list[str]:
    seen = set()
    out = []
    for ln in lines:
        key = ln.lower().strip()
        if key not in seen:
            seen.add(key)
            out.append(ln)
    return out


def log_question(question: str, name: str | None, company: str | None):
    QUESTION_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with QUESTION_LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(
            f"{datetime.utcnow().isoformat()} | "
            f"name={name or '-'} | "
            f"company={company or '-'} | "
            f"q={question}\n"
        )
        

def should_use_star(question: str) -> bool:
    q = question.lower()
    return any(p in q for p in STAR_TRIGGER_PHRASES)

def split_star_examples(star_text: str) -> list[str]:
    """
    Splits STAR text into blocks.
    Supports:
      - blocks starting with 'EXAMPLE '
      - blocks starting with 'SKILL:'
    Keeps the header line inside each block.
    """
    if not star_text.strip():
        return []

    lines = star_text.splitlines()
    blocks: list[str] = []
    current: list[str] = []

    def is_block_start(ln: str) -> bool:
        s = ln.strip()
        return s.startswith("EXAMPLE ") or s.startswith("SKILL:")

    for ln in lines:
        if is_block_start(ln):
            if current:
                blocks.append("\n".join(current).strip())
                current = []
        if ln.strip():  # skip pure empty lines at the start of file
            current.append(ln)

    if current:
        blocks.append("\n".join(current).strip())

    # filter out obvious non-content headers
    cleaned = []
    for b in blocks:
        bl = b.lower()
        if "authoritative experience examples" in bl and "skill:" not in bl and "example " not in bl:
            continue
        cleaned.append(b)

    return [b for b in cleaned if b]

def find_relevant_star_examples(star_text: str, question: str, limit: int = 1):
    """
    Score each STAR block by how many kept_words appear in it.
    Returns (kept_words, top_blocks)
    """
    blocks = split_star_examples(star_text)

    kept_words = []
    for w in question.lower().split():
        clean = w.strip(string.punctuation)
        if len(clean) > 3 or clean in IMPORTANT_SHORT_WORDS:
            kept_words.append(clean)

    scored = []
    for block in blocks:
        b_lower = block.lower()
        score = sum(1 for w in kept_words if w and w in b_lower)
        if score > 0:
            scored.append((score, block))

    scored.sort(reverse=True, key=lambda x: x[0])
    top = [b for _, b in scored[:limit]]
    return kept_words, top

def build_search_terms(question: str) -> list[str]:
    terms: list[str] = []

    for w in question.lower().split():
        clean = w.strip(string.punctuation)
        if len(clean) <= 3 and clean not in IMPORTANT_SHORT_WORDS:
            continue

        if clean not in terms:
            terms.append(clean)

        for alias in SEARCH_TERM_ALIASES.get(clean, []):
            if alias not in terms:
                terms.append(alias)

    return terms



def is_period_line(text: str) -> bool:
    has_digit = any(ch.isdigit() for ch in text)
    has_range = any(token in text.lower() for token in ("-", "?", "?", "???", "to", "present"))
    return has_digit and has_range and len(text) <= 40



def extract_cv_entries(cv_text: str) -> list[str]:
    entries: list[str] = []
    current_org = None
    current_section = None
    in_employment_history = False

    for raw_line in cv_text.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue

        if stripped.startswith("===") or stripped.startswith("---"):
            continue

        upper = stripped.upper()
        if stripped.startswith("TOOLS (AUTHORITATIVE LIST)"):
            current_section = "tools"
            continue
        if EMPLOYMENT_HISTORY_MARKER in upper:
            current_section = "employment"
            in_employment_history = True
            current_org = None
            continue
        if "EDUCATION" in upper:
            current_section = "education"
            current_org = None
            continue
        if "CERTIFICATIONS" in upper:
            current_section = "certifications"
            current_org = None
            continue

        if stripped.startswith("Organisation:"):
            current_org = stripped.split(":", 1)[1].strip()
            continue

        if in_employment_history and current_org and is_period_line(stripped):
            entries.append(f"[{current_org}] Period: {stripped}")
            continue

        if in_employment_history and not stripped.startswith("-") and ":" not in stripped and len(stripped) < 80 and not is_period_line(stripped) and not any(ch.isdigit() for ch in stripped):
            current_org = stripped
            continue

        if ":" in stripped:
            label, value = stripped.split(":", 1)
            label = label.strip()
            value = value.strip()
            label_lower = label.lower()

            if not value:
                continue

            if label_lower in {"industry", "role", "roles", "context", "period"} and current_org:
                entries.append(f"[{current_org}] {label.title()}: {value}")
                continue

            if label_lower in {"name", "role", "location", "experience"}:
                entries.append(f"{label.upper()}: {value}")
                continue

        if stripped.startswith("-"):
            content = clean_line(stripped)
            if in_employment_history and current_org:
                entries.append(f"[{current_org}] {content}")
            elif current_section == "tools":
                entries.append(f"Tools: {content}")
            elif current_section == "education":
                entries.append(f"Education: {content}")
            elif current_section == "certifications":
                entries.append(f"Certification: {content}")
            else:
                entries.append(content)

    return entries



def find_relevant_sentences(cv_text: str, question: str, limit: int | None = None):
    if limit is None:
        limit = TOP_QUESTIONS

    entries = extract_cv_entries(cv_text)
    kept_words = build_search_terms(question)

    scored = []
    for entry in entries:
        entry_lower = entry.lower()
        score = sum(1 for w in kept_words if w in entry_lower)
        if score > 0:
            scored.append((score, entry))

    scored.sort(reverse=True, key=lambda x: x[0])
    return kept_words, scored[:limit]

BASE_SYSTEM_PROMPT = (
    "You answer recruiter questions about candidate Rob Voto. "
    "Use the supplied CV text as the source of truth for facts. "
    "You may make reasonable high-level inferences when they are clearly supported by the CV context. "
    "Do not invent experience beyond reasonable professional inference. "
    "If the answer is not present in the supplied text, say exactly: "
    "'I can't find that in the CV text I was given.' "
    "Unless the question explicitly asks for detail, keep answers concise and factual."
)

FIT_QUESTION_PROMPT = (
    "For broad fit questions such as 'Why Rob', 'Why is Rob a good fit', or 'Summarise Rob', "
    "start with overall fit first, then support it with a balanced mix of recent and representative experience. "
    "Prefer recent roles first, especially DEWR and ABS when relevant, then add one or two other distinct organisations "
    "or sectors if needed. Do not anchor the whole answer to NSW Health or any single employer unless the question is specifically about that employer."
)

STAR_SYSTEM_PROMPT = (
    "If the CV text contains a section starting with 'STAR EXAMPLE:', prioritise that STAR example over CV bullets. "
    "In that case, answer strictly in STAR format with these headings: Situation, Task, Action, Result. "
    "Each section must be 1-3 concise sentences. Only summarise the supplied STAR example."
)

BPMN_SYSTEM_PROMPT = (
    "Before writing any BPMN examples, identify all organisations in the CV where BPMN usage is explicitly described. "
    "Only these organisations may be used as anchors. Generate at most one example per organisation, and do not reuse the same organisation name more than once. "
    "If BPMN usage exists for fewer organisations, return fewer examples. Do not merge or generalise examples across organisations. "
    "Each example must follow this format: '- At <REAL ORGANISATION NAME>: <Concrete BPMN activity and outcome>'. "
    "Do not include tools unless explicitly asked. Do not include generic or summary bullets."
)

TOOLS_SYSTEM_PROMPT = (
    "Only include tools or technologies when the question explicitly asks for them. "
    "If technologies are historical, label them as earlier-career experience."
)


def build_system_prompt(question: str, context: str) -> str:
    question_lower = question.lower()
    system_parts = [BASE_SYSTEM_PROMPT]

    if "STAR EXAMPLE:" in context:
        system_parts.append(STAR_SYSTEM_PROMPT)

    if "bpmn" in question_lower:
        system_parts.append(BPMN_SYSTEM_PROMPT)

    if any(term in question_lower for term in ("why rob", "good fit", "summarise rob", "summarize rob", "fit for", "why is rob")):
        system_parts.append(FIT_QUESTION_PROMPT)

    if any(term in question_lower for term in ("tool", "tools", "technology", "technologies", "tech stack", "stack")):
        system_parts.append(TOOLS_SYSTEM_PROMPT)

    return "\n\n".join(system_parts)


def llm_rewrite_answer(question: str, context: str) -> str:
    system_prompt = build_system_prompt(question, context)
    resp = client.responses.create(
        model="gpt-4.1-mini",
        input=[
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": f"Question: {question}\n\nCV TEXT:\n{context}",
            },
        ],
    )
    return resp.output_text

# ─────────────────────────
# Static / UI
# ─────────────────────────

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def home():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/admin")
def admin():
    return FileResponse(STATIC_DIR / "admin.html")


@app.get("/health")
def health():
    return {"ok": True}


# ─────────────────────────
# API
# ───────────────────────── 
@app.post("/ingest_cv")
def ingest(payload: dict):
    global CV_AUTHORITATIVE, CV_BODY

    text = payload.get("text", "")
    if not text:
        return {"error": "No CV text provided"}

    save_text_file(CV_FILE, text)

    CV_AUTHORITATIVE, CV_BODY = split_authoritative(text)

    return {
        "status": "CV stored",
        "authoritative_length": len(CV_AUTHORITATIVE),
        "body_length": len(CV_BODY),
    }

@app.post("/ingest_star")
def ingest_star(payload: dict):
    global STAR_TEXT

    text = payload.get("text", "")
    if not text:
        return {"error": "No STAR text provided"}

    save_text_file(STAR_FILE, text)

    STAR_TEXT = text

    return {
        "status": "STAR stored",
        "length": len(STAR_TEXT),
    }

@app.get("/reload")
def reload_files():
    load_all_data()
    startup_checkup()
    return {
        "status": "reloaded",
        "authoritative_length": len(CV_AUTHORITATIVE),
        "body_length": len(CV_BODY),
        "star_length": len(STAR_TEXT),
    }

@app.post("/ask")
def ask(payload: dict):
    question = payload.get("question", "").strip()
    debug = bool(payload.get("debug", False))
    use_llm = bool(payload.get("use_llm", False))
    preview_context = bool(payload.get("preview_context", False))

    if len(question) > MAX_QUESTION_CHARS:
        return {"answer": f"Please shorten your question to under {MAX_QUESTION_CHARS} characters."}

    if not CV_BODY:
        return {"answer": "No CV loaded yet."}

    name = payload.get("name")
    company = payload.get("company")
    log_question(question, name, company)

    kept_words, top = find_relevant_sentences(CV_BODY, question)
    bullets = dedupe_lines([clean_line(s) for _, s in top])

    payload_forced_star = bool(payload.get("use_star", False))
    use_star = payload_forced_star or should_use_star(question)

    star_blocks = []
    if use_star and STAR_TEXT:
        _, star_blocks = find_relevant_star_examples(STAR_TEXT, question, limit=1)

    reason = "no_star_trigger"
    if payload_forced_star:
        reason = "payload_use_star"
    elif use_star:
        reason = "question_trigger_phrase"

    star_example_id = None
    if star_blocks:
        star_example_id = star_blocks[0].splitlines()[0].strip()

    log_intent_event(
        question=question,
        requested_star=use_star,
        included_star=bool(star_blocks),
        star_example_id=star_example_id,
        reason=reason,
    )

    context_parts = []
    if CV_AUTHORITATIVE:
        context_parts.append(CV_AUTHORITATIVE)
    if star_blocks:
        context_parts.append("STAR EXAMPLE:\n" + "\n\n".join(star_blocks))
    if bullets:
        context_parts.append("RELEVANT EXPERIENCE:\n" + "\n".join(f"- {b}" for b in bullets))

    full_context = "\n\n".join(context_parts)
    system_prompt = build_system_prompt(question, full_context)
    llm_would_run = use_llm and not preview_context

    if not bullets and not star_blocks:
        response = {"answer": "I couldn't find anything relevant in the CV text I was given."}
        if debug or preview_context:
            response.update({
                "preview_context": full_context,
                "system_prompt": system_prompt,
                "llm_requested": use_llm,
                "llm_executed": False,
                "kept_words": kept_words,
                "bullets": bullets,
                "star": star_blocks,
            })
        return response

    final_answer = bullets
    if llm_would_run:
        final_answer = llm_rewrite_answer(question, full_context)

    print("\n===== FULL CONTEXT SENT TO LLM =====")
    print(full_context[:2000])
    print("===== END CONTEXT (first 2000 chars) =====\n")

    response: dict[str, str | list[str] | bool] = {"answer": final_answer}

    if debug or preview_context:
        response.update({
            "use_star": use_star,
            "star_found": bool(star_blocks),
            "star": star_blocks,
            "kept_words": kept_words,
            "bullets": bullets,
            "preview_context": full_context,
            "system_prompt": system_prompt,
            "llm_requested": use_llm,
            "llm_executed": llm_would_run,
        })

    return response
