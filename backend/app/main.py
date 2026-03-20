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
from openai import BaseModel, OpenAI

# ─────────────────────────
# Globals / config
# ─────────────────────────
APP_DIR = Path(__file__).resolve().parent
BACKEND_DIR = APP_DIR.parent
STATIC_DIR = BACKEND_DIR / "static"
DATA_DIR = BACKEND_DIR / "data"
CV_FILE = DATA_DIR / "cv.txt"
STAR_FILE = DATA_DIR / "star.txt"

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


def load_text_file(path: str) -> str:
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()



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
    AUTHORITATIVE is extracted.
    BODY remains the FULL CV so nothing is lost to retrieval.
    """
    if AUTHORITATIVE_MARKER not in cv_text:
        return "", cv_text.strip()

    start = cv_text.find(AUTHORITATIVE_MARKER)
    end = cv_text.find("====", start + 1)

    if end == -1:
        authoritative = cv_text[start:].strip()
    else:
        authoritative = cv_text[start:end].strip()

    body = cv_text.strip()
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

    cv_file = os.path.abspath(CV_FILE)
    star_file = os.path.abspath(STAR_FILE)
    log_path = os.path.abspath("questions.log")

    cv_exists = os.path.exists(CV_FILE)
    star_exists = os.path.exists(STAR_FILE)

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
    with open("questions.log", "a", encoding="utf-8") as f:
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

def find_relevant_sentences(cv_text: str, question: str, limit: int | None = None):
    if limit is None:
        limit = TOP_QUESTIONS

    lines = [ln.rstrip() for ln in cv_text.splitlines()]

    kept_words = []
    for w in question.lower().split():
        clean = w.strip(string.punctuation)
        if len(clean) > 3 or clean in IMPORTANT_SHORT_WORDS:
            kept_words.append(clean)

    scored = []
    current_org = None

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # Detect organisation header (no dash, reasonably short)
        if not stripped.startswith("-") and len(stripped) < 80:
            # crude but effective: organisation names are title-like
            current_org = stripped
            continue

        if len(stripped) < MIN_LINE_LENGTH:
            continue

        l_lower = stripped.lower()
        score = sum(1 for w in kept_words if w in l_lower)

        if score > 0:
            if current_org:
                annotated = f"[{current_org}] {stripped.lstrip('- ').strip()}"
            else:
                annotated = stripped.lstrip("- ").strip()

            scored.append((score, annotated))

    scored.sort(reverse=True, key=lambda x: x[0])
    return kept_words, scored[:limit]

def llm_rewrite_answer(question: str, context: str) -> str:
    resp = client.responses.create(
        model="gpt-4.1-mini",
        input=[
            {
                "role": "system",
                "content": (
                            "You answer recruiter questions about candidate Rob Voto. "
                            "Use the CV text as the source of truth for facts. "
                            "You may infer higher-level concepts (such as industries, domains, or sectors) "
                            "You may infer higher-level concepts when they are clearly supported by the CV. "
                            "Do not invent experience beyond reasonable professional inference. "

                            "CLASSIFICATION RULE: "
                            "You may classify known organisations or roles into higher-level categories "
                            "(such as industries or domains) even if those categories are not explicitly listed, "
                            "as long as the underlying organisations or roles are present in the CV. "
                            "This applies even when the question is constrained (e.g. 'private sector industries')."

                            "ABSTRACTION RULE: "
                            "Match the abstraction level of the answer to the abstraction level of the question. "
                            "For high-level or abstract questions, synthesise higher-level themes or domains. "
                            "For concrete questions, provide specific factual details from the CV. "

                            "Do not invent facts. "
                            "If the answer is not present, say exactly: "
                            "'I can't find that in the CV text I was given.' "

                           
                            "BPMN EXAMPLE SELECTION RULE (MANDATORY): "
                            "Before writing any BPMN examples, first identify ALL organisations in the CV "
                            "where BPMN usage is explicitly described. "
                            "Only these organisations may be used as anchors. "

                            "Then, generate AT MOST ONE example per organisation. "
                            "Each example MUST be anchored to a different organisation. "
                            "Do NOT reuse the same organisation name more than once. "

                            "If BPMN usage exists for fewer organisations, return fewer examples. "
                            "Do NOT default multiple examples to the same organisation. "
                            "Do NOT merge or generalise examples across organisations. "

                            "Each example MUST follow this format: "
                            "'- At <REAL ORGANISATION NAME>: <Concrete BPMN activity and outcome>' "

                            "Do NOT include tools unless explicitly asked. "
                            "Do NOT include generic or summary bullets."



                            "DEFAULT BREVITY RULE: "
                            "Unless the question explicitly asks for explanation or detail, "
                            "keep answers concise and factual. "
                          #  "Avoid introductory or concluding sentences. "

                            "CRITICAL RULE — STAR OVERRIDE: "
                            "If the CV TEXT contains a section starting with 'STAR EXAMPLE:', "
                            "you MUST prioritise that STAR example over CV bullets. "
                            "In that case, answer STRICTLY in STAR format with these headings: "
                            "Situation, Task, Action, Result. "
                            "Each section must be 1–3 concise sentences. "
                            "Only summarise the STAR example. "

                            "NON-STAR MODE: "
                            "If there is NO 'STAR EXAMPLE:' section, answer using relevant CV bullets only. "
                            "Merge duplicates. "
                            "If technologies are historical, label them as earlier-career experience."
                ),
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

    if len(question) > MAX_QUESTION_CHARS:
        return {"answer": f"Please shorten your question to under {MAX_QUESTION_CHARS} characters."}

    if not CV_BODY:
        return {"answer": "No CV loaded yet."}

    # Log question (optional name/company)
    name = payload.get("name")
    company = payload.get("company")
    log_question(question, name, company)
    
    # Retrieve relevant CV lines
    kept_words, top = find_relevant_sentences(CV_BODY, question)
    bullets = dedupe_lines([clean_line(s) for _, s in top])

    # Decide whether to include STAR
    payload_forced_star = bool(payload.get("use_star", False))
    use_star = payload_forced_star or should_use_star(question)

    star_blocks = []
    if use_star and STAR_TEXT:
        _, star_blocks = find_relevant_star_examples(STAR_TEXT, question, limit=1)

    # ✅ Log STAR intent decision (right here)
    reason = "no_star_trigger"
    if payload_forced_star:
        reason = "payload_use_star"
    elif use_star:
        reason = "question_trigger_phrase"

    star_example_id = None
    if star_blocks:
        # First line is like: "EXAMPLE 1 - ..."
        star_example_id = star_blocks[0].splitlines()[0].strip()

    log_intent_event(
        question=question,
        requested_star=use_star,
        included_star=bool(star_blocks),
        star_example_id=star_example_id,
        reason=reason,
    )

    # Build LLM context: AUTHORITATIVE + STAR + CV bullets
    context_parts = []

    if CV_AUTHORITATIVE:
        context_parts.append(CV_AUTHORITATIVE)

    if star_blocks:
        context_parts.append("STAR EXAMPLE:\n" + "\n\n".join(star_blocks))

    if bullets:
        context_parts.append("RELEVANT EXPERIENCE:\n" + "\n".join(f"- {b}" for b in bullets))

    full_context = "\n\n".join(context_parts)

    # If nothing matched at all, be honest
    if not bullets and not star_blocks:
        return {"answer": "I couldn't find anything relevant in the CV text I was given."}

    # Default answer (no LLM) = show bullets (and STAR if debug mode)
    final_answer = bullets

    # Optional LLM rewrite
    if use_llm:
        final_answer = llm_rewrite_answer(question, full_context)

    print("\n===== FULL CONTEXT SENT TO LLM =====")
    print(full_context[:2000])
    print("===== END CONTEXT (first 2000 chars) =====\n")
    
    response: dict[str, str | list[str]] = {"answer": final_answer}

    if debug:
        response.update({
            "use_star": use_star,
            "star_found": bool(star_blocks),
            "star": star_blocks,
            "kept_words": kept_words,
            "bullets": bullets,
        })

    return response
