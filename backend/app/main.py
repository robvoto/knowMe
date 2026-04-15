import string
import os
import re
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
    "industry": ["industries"],
    "departments": ["department"],
    "department": ["departments"],
    "tools": ["tool", "technology", "technologies", "tech stack"],
    "tool": ["tools", "technology", "technologies"],
    "technology": ["tools", "technologies"],
    "technologies": ["tools", "technology"],
    "bpmn": ["business process model and notation", "process mapping"],
    "sql": ["structured query language", "data query"],
    "api": ["application programming interface", "apis"],
    "reporting": ["reports", "analytics"],
    "stakeholder": ["stakeholders", "vendor", "vendors", "client", "clients"],
    "delivery": ["project delivery", "delivery collaboration", "program delivery"],
    "analysis": ["analytics", "data analysis"],
    "agile": ["scrum", "kanban", "delivery collaboration"],
    "requirements": ["user stories", "acceptance criteria"],
}

QUESTION_CANONICAL_PATTERNS = [
    (re.compile(r"\b(strong fit|good fit|fit for|why (?:would|is) .+ fit)\b"), "why would <candidate> be a strong fit"),
    (re.compile(r"\b(industry|industries|department|departments|sector|sectors)\b.*\b(work|worked|experience|background)\b"), "what industries has <candidate> worked in"),
    (re.compile(r"\b(api|application programming interface|apis)\b"), "what api experience has <candidate> had"),
    (re.compile(r"\b(bpmn|business process model and notation|process mapping)\b"), "has <candidate> used bpmn"),
    (re.compile(r"\b(tools|technology|technologies|tech stack|software|platforms)\b"), "what tools has <candidate> used"),
    (re.compile(r"\b(data analysis|sql|reporting|analytics)\b"), "what experience does <candidate> have with data analysis and sql"),
    (re.compile(r"\b(agile|scrum|kanban|delivery collaboration|project delivery)\b"), "what experience does <candidate> have with agile and scrum"),
    (re.compile(r"\b(user stories|requirements|acceptance criteria)\b"), "what experience does <candidate> have writing requirements and user stories"),
    (re.compile(r"\b(stakeholder|stakeholders|vendor|vendors|client|clients)\b"), "has <candidate> worked with stakeholders or vendors"),
    (re.compile(r"\b(testing|uat|quality assurance|qa|user acceptance)\b"), "what experience does <candidate> have in testing and quality assurance"),
]

INTENT_PATTERNS = [
    (re.compile(r"\b(star|tell me about a time|describe a situation|give an example|scenario|challenge|result|action|task)\b"), "star"),
    (re.compile(r"\b(bpmn|business process model and notation|process mapping)\b"), "bpmn"),
    (re.compile(r"\b(api|application programming interface|apis)\b"), "api"),
    (re.compile(r"\b(tools|technology|technologies|tech stack|platforms|software)\b"), "tools"),
    (re.compile(r"\b(data analysis|sql|reporting|analytics)\b"), "data"),
    (re.compile(r"\b(agile|scrum|kanban|delivery collaboration|project delivery)\b"), "agile"),
    (re.compile(r"\b(user stories|requirements|acceptance criteria)\b"), "requirements"),
    (re.compile(r"\b(stakeholder|stakeholders|vendor|vendors|client|clients)\b"), "stakeholders"),
    (re.compile(r"\b(testing|uat|quality assurance|qa|user acceptance)\b"), "testing"),
    (re.compile(r"\b(strong fit|good fit|why\b|fit for|summarise|summarize|why is)\b"), "fit"),
]

PHRASE_WEIGHTS = {
    "api": 3,
    "bpmn": 4,
    "sql": 3,
    "data analysis": 4,
    "agile": 3,
    "scrum": 3,
    "stakeholder": 3,
    "tools": 2,
    "requirements": 2,
    "user stories": 3,
    "testing": 2,
    "uat": 2,
    "project delivery": 3,
    "acceptance criteria": 3,
    "business analyst": 4,
}

FOLLOWUP_SUGGESTIONS: dict[str, list[str]] = {
    "api": [
        "What tools or platforms has Rob used alongside APIs in delivery projects?",
        "Has Rob worked with external vendors or third-party system integrations?",
        "What experience does Rob have with data analysis or reporting in projects?",
    ],
    "bpmn": [
        "What tools has Rob used for process mapping or business analysis?",
        "Has Rob worked with stakeholders to design or validate business processes?",
        "Describe a situation where Rob improved a process — STAR format.",
    ],
    "data": [
        "What experience does Rob have with SQL, reporting tools, or dashboards?",
        "Has Rob worked on data quality or governance initiatives?",
        "What experience does Rob have with Agile or delivery in data projects?",
    ],
    "agile": [
        "What experience does Rob have writing requirements or user stories in Agile?",
        "Has Rob worked with external vendors or stakeholders in Agile delivery?",
        "Describe a challenging delivery situation — STAR format.",
    ],
    "requirements": [
        "What experience does Rob have in UAT or quality assurance of requirements?",
        "Has Rob worked directly with stakeholders or end users to gather requirements?",
        "Describe a time Rob resolved a requirements conflict — STAR format.",
    ],
    "stakeholders": [
        "Describe a difficult stakeholder situation and how Rob managed it — STAR format.",
        "Has Rob worked with external vendors or government clients?",
        "What experience does Rob have leading workshops or requirements sessions?",
    ],
    "testing": [
        "What tools or platforms has Rob used for testing and quality assurance?",
        "Has Rob worked in government or regulated environments requiring formal testing?",
        "Describe a time Rob found a critical issue during UAT — STAR format.",
    ],
    "star": [
        "Describe a time Rob led delivery in a complex stakeholder environment.",
        "Tell me about a process Rob improved that had measurable results.",
        "What experience does Rob have in testing, UAT, or quality assurance?",
    ],
    "fit": [
        "What industries or government departments has Rob worked in?",
        "What tools and technologies has Rob used most recently?",
        "Describe a challenging project Rob led — STAR format.",
    ],
    "tools": [
        "What experience does Rob have with data analysis, SQL, or reporting tools?",
        "Has Rob used BPMN or process mapping tools in past projects?",
        "What tools has Rob used in Agile or delivery collaboration?",
    ],
    "general": [
        "Why would Rob be a strong fit for a senior business analyst role?",
        "What tools and technologies has Rob used most recently?",
        "Describe a time Rob solved a complex problem — STAR format.",
    ],
}


def suggest_followup_questions(intent: str, question: str) -> list[str]:
    """Return follow-up question suggestions based on detected intent, excluding close matches to the current question."""
    pool = FOLLOWUP_SUGGESTIONS.get(intent, FOLLOWUP_SUGGESTIONS["general"])
    q_lower = question.lower()
    filtered = [s for s in pool if s.lower()[:30] not in q_lower]
    return (filtered if filtered else pool)[:3]


STAR_TRIGGER_PHRASES = [
    "star",
    "tell me about a time",
    "describe a situation",
    "give an example",
    "give examples",
    "example",
    "scenario",
    "challenge",
    "task",
    "action",
    "result",
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
    return text.lstrip("•\u2022-–—▪▸* \t").strip()


def normalize_question_text(question: str) -> str:
    """Normalize a candidate question for logging and analytics."""
    normalized = question or ""
    normalized = normalized.strip().lower()
    normalized = re.sub(r"\([^)]*\)", "", normalized)
    normalized = re.sub(r"[^\w\s]", "", normalized)

    normalized = re.sub(r"\b(please|could you|would you|can you|i want to know|tell me|do you know|what is|what s)\b", "", normalized)
    normalized = re.sub(r"\b(rob|robert|candidate|he|she|they)\b", "<candidate>", normalized)
    normalized = re.sub(r"\b(technical\s+ba|technical\s+business\s+analyst|ba)\b", "business analyst", normalized)
    normalized = re.sub(r"\b(senior\s+business\s+analyst\s+or\s+business\s+analyst)\b", "senior business analyst", normalized)
    normalized = re.sub(r"\b(project delivery|delivery collaboration|program delivery)\b", "delivery", normalized)
    normalized = re.sub(r"\b(user stories|acceptance criteria)\b", "requirements", normalized)

    normalized = re.sub(r"\s+", " ", normalized)
    normalized = normalized.strip()

    return normalized


def classify_question_intent(question: str) -> str:
    normalized = normalize_question_text(question)
    for pattern, label in INTENT_PATTERNS:
        if pattern.search(normalized):
            return label
    return "general"


def canonical_question_text(question: str) -> str:
    """Map normalized questions to canonical question groups for analytics."""
    normalized = normalize_question_text(question)
    if not normalized:
        return ""

    for pattern, canonical in QUESTION_CANONICAL_PATTERNS:
        if pattern.search(normalized):
            return canonical

    return normalized


def load_text_file(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def get_file_metadata(path: Path) -> dict[str, str | int | float]:
    if not path.exists():
        return {"exists": False, "path": str(path), "size": 0, "modified": 0}
    stat = path.stat()
    return {
        "exists": True,
        "path": str(path),
        "size": stat.st_size,
        "modified": stat.st_mtime,
    }


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


def parse_question_log_line(line: str) -> dict[str, str]:
    parts = [part.strip() for part in line.split("|") if part.strip()]
    record = {"raw": line}
    if parts:
        record["ts"] = parts[0]
    for part in parts[1:]:
        if "=" in part:
            key, value = part.split("=", 1)
            record[key.strip()] = value.strip()
    if "q_norm" not in record and "q" in record:
        record["q_norm"] = normalize_question_text(record["q"])
    if "q_canonical" not in record and "q" in record:
        record["q_canonical"] = canonical_question_text(record["q"])
    return record


def read_question_log() -> list[dict[str, str]]:
    if not QUESTION_LOG_FILE.exists():
        return []
    with QUESTION_LOG_FILE.open("r", encoding="utf-8") as f:
        return [parse_question_log_line(line) for line in f if line.strip()]


def read_intent_log() -> list[dict]:
    if not INTENT_LOG_PATH.exists():
        return []
    events = []
    with INTENT_LOG_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def analytics_summary() -> dict:
    question_records = read_question_log()
    canonical_counts: dict[str, int] = {}
    normalized_counts: dict[str, int] = {}
    intent_counts: dict[str, int] = {}

    for rec in question_records:
        canonical = rec.get("q_canonical", "")
        normalized = rec.get("q_norm", "")
        intent = classify_question_intent(rec.get("q", ""))
        intent_counts[intent] = intent_counts.get(intent, 0) + 1
        if canonical:
            canonical_counts[canonical] = canonical_counts.get(canonical, 0) + 1
        if normalized:
            normalized_counts[normalized] = normalized_counts.get(normalized, 0) + 1

    top_canonical = sorted(canonical_counts.items(), key=lambda item: item[1], reverse=True)[:10]
    top_normalized = sorted(normalized_counts.items(), key=lambda item: item[1], reverse=True)[:10]
    intent_events = read_intent_log()

    star_requests = sum(1 for e in intent_events if e.get("requested_star"))
    star_included = sum(1 for e in intent_events if e.get("included_star"))

    recent_questions = [
        {"ts": rec.get("ts", ""), "question": rec.get("q", ""), "canonical": rec.get("q_canonical", "")}
        for rec in question_records[-10:]
    ][::-1]

    return {
        "question_count": len(question_records),
        "top_canonical_questions": [{"question": q, "count": c} for q, c in top_canonical],
        "top_normalized_questions": [{"question": q, "count": c} for q, c in top_normalized],
        "intent_counts": [{"intent": intent, "count": count} for intent, count in sorted(intent_counts.items(), key=lambda item: item[1], reverse=True)],
        "recent_questions": recent_questions,
        "intent_event_count": len(intent_events),
        "star_trigger_rate": (star_requests / len(intent_events) * 100) if intent_events else 0,
        "star_included_rate": (star_included / len(intent_events) * 100) if intent_events else 0,
    }


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
    norm_question = normalize_question_text(question)
    canonical_question = canonical_question_text(question)
    with QUESTION_LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(
            f"{datetime.utcnow().isoformat()} | "
            f"name={name or '-'} | "
            f"company={company or '-'} | "
            f"q={question} | "
            f"q_norm={norm_question} | "
            f"q_canonical={canonical_question}\n"
        )


def should_use_star(question: str) -> bool:
    normalized = normalize_question_text(question)
    if any(p in normalized for p in STAR_TRIGGER_PHRASES):
        return True

    if re.search(r"\b(star|situation|task|action|result|challenge|behaviour|behavior|tell me about a time|give an example|example|scenario)\b", normalized):
        return True

    return False


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
    Score each STAR block by how many relevant question terms appear in it.
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
        score += sum(1 for marker in ("challenge", "problem", "situation", "action", "result") if marker in b_lower)
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

    # Ensure useful multi-word concepts are present for recruiter questions.
    if "business" in terms and "analyst" not in terms:
        terms.append("business analyst")
    if "data" in terms and "analysis" not in terms:
        terms.append("data analysis")

    return terms



def is_period_line(text: str) -> bool:
    # Must contain an actual 4-digit year (19xx or 20xx) and be short
    return bool(re.search(r'\b(19|20)\d{2}\b', text)) and len(text) <= 40



_BULLET_PREFIXES = ("•", "-", "–", "▪", "▸", "*", "\u2022", "\u2013", "\u2014")
_ROLE_MARKERS = {"analyst", "developer", "consultant", "manager", "lead", "scrum", "master",
                  "engineer", "architect", "director", "officer", "specialist", "senior", "junior"}
_NOT_ORG_WORDS = {"outcome", "outcomes", "note", "notes", "summary", "result", "results",
                   "overview", "background", "context", "responsibilities"}
_SKIP_SECTIONS = {"executive summary", "core competencies", "technical tools", "technical skills",
                   "key achievements", "ai and innovation", "tools & technologies"}


def _is_bullet(line: str) -> bool:
    return any(line.startswith(p) for p in _BULLET_PREFIXES)


def _is_role_line(line: str) -> bool:
    """Pipe-separated role lines: Role | Period | Sector | Type"""
    return "|" in line and any(m in line.lower() for m in _ROLE_MARKERS)


def extract_cv_entries(cv_text: str) -> list[str]:
    entries: list[str] = []
    current_org = None
    current_section = None
    in_employment_history = False

    for raw_line in cv_text.splitlines():
        stripped = raw_line.strip()
        stripped = stripped.strip("*#\t").strip()
        if not stripped:
            continue
        if stripped.startswith("===") or stripped.startswith("---"):
            continue

        upper = stripped.upper()

        # ── Section detection ──────────────────────────────────────────────
        if stripped.startswith("TOOLS (AUTHORITATIVE LIST)"):
            current_section = "tools"
            continue
        if EMPLOYMENT_HISTORY_MARKER in upper or "PROFESSIONAL EXPERIENCE" in upper or "EMPLOYMENT HISTORY" in upper:
            current_section = "employment"
            in_employment_history = True
            current_org = None
            continue
        if upper.startswith("EARLIER CAREER"):
            current_section = "earlier_career"
            in_employment_history = True
            current_org = "Earlier Career"
            continue
        if upper.startswith("EDUCATION") and len(stripped) < 40:
            current_section = "education"
            in_employment_history = False
            current_org = None
            continue
        if "CERTIF" in upper and len(stripped) < 30:
            current_section = "certifications"
            in_employment_history = False
            current_org = None
            continue
        if any(stripped.upper().startswith(s.upper()) for s in _SKIP_SECTIONS):
            current_section = "skip"
            continue

        # Skip decorative or noise lines in non-employment sections
        if current_section == "skip":
            continue

        # ── Explicit Organisation: label ───────────────────────────────────
        if stripped.startswith("Organisation:"):
            current_org = stripped.split(":", 1)[1].strip()
            entries.append(f"Organisation: {current_org}")
            continue

        # ── Employment section handling ────────────────────────────────────
        if in_employment_history:

            # Pipe-separated role lines: extract sector and period
            if _is_role_line(stripped):
                parts = [p.strip() for p in stripped.split("|")]
                for part in parts[1:]:  # skip role title (first part)
                    part_clean = part.strip("–—").strip()
                    if not part_clean:
                        continue
                    # Period detection
                    if any(ch.isdigit() for ch in part_clean):
                        if current_org:
                            entries.append(f"[{current_org}] Period: {part_clean}")
                    # Sector/type detection (no digits, meaningful length)
                    elif len(part_clean) > 3 and part_clean.lower() not in {"contract", "permanent", "casual"}:
                        if current_org:
                            entries.append(f"[{current_org}] Sector: {part_clean}")
                continue

            # Period-only line
            if current_org and is_period_line(stripped):
                entries.append(f"[{current_org}] Period: {stripped}")
                continue

            # Org name detection: short line, no bullet, no digit, no role marker, no pipe
            if (not _is_bullet(stripped) and ":" not in stripped and "|" not in stripped
                    and len(stripped) < 100 and not is_period_line(stripped)
                    and not any(ch.isdigit() for ch in stripped)
                    and not any(re.search(r'\b' + m + r'\b', stripped.lower()) for m in _ROLE_MARKERS)
                    and stripped.lower() not in _NOT_ORG_WORDS):
                current_org = stripped
                entries.append(f"Organisation: {stripped}")
                continue

            # Context/intro line (sentence describing the role, not a bullet)
            if (not _is_bullet(stripped) and ":" not in stripped and "|" not in stripped
                    and current_org and len(stripped) > 30 and stripped.endswith(".")
                    and not any(m in stripped.lower() for m in _ROLE_MARKERS)):
                entries.append(f"[{current_org}] Context: {stripped}")
                continue

        # ── Label: value lines ─────────────────────────────────────────────
        if ":" in stripped:
            label, value = stripped.split(":", 1)
            label = label.strip()
            value = value.strip()
            label_lower = label.lower()
            if not value:
                continue
            if label_lower in {"industry", "domain", "sector", "role", "roles", "context", "period"} and current_org:
                entries.append(f"[{current_org}] {label.title()}: {value}")
                continue
            if label_lower in {"name", "location", "experience"}:
                entries.append(f"{label.upper()}: {value}")
                continue

        # ── Bullet lines ───────────────────────────────────────────────────
        if _is_bullet(stripped):
            content = clean_line(stripped)
            if not content or len(content) < MIN_LINE_LENGTH:
                continue
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
            continue

        # ── Plain lines in education / certification sections ──────────────
        if current_section == "education" and len(stripped) >= MIN_LINE_LENGTH:
            entries.append(f"Education: {stripped}")
        elif current_section == "certifications" and len(stripped) >= 10:
            entries.append(f"Certification: {stripped}")

    return entries



def find_relevant_sentences(cv_text: str, question: str, limit: int | None = None):
    if limit is None:
        limit = TOP_QUESTIONS

    entries = extract_cv_entries(cv_text)
    kept_words = build_search_terms(question)
    intent = classify_question_intent(question)

    # For industry/sector/government questions, boost org and domain entries
    _industry_question = any(
        term in question.lower()
        for term in ("industry", "industries", "government", "department", "departments",
                     "sector", "sectors", "organisation", "organizations", "worked in",
                     "background in", "types of")
    )

    scored = []
    for entry in entries:
        entry_lower = entry.lower()
        score = 0
        score += sum(1 for w in kept_words if w in entry_lower)
        score += sum(weight for phrase, weight in PHRASE_WEIGHTS.items() if phrase in entry_lower)
        score += sum(2 for term in ("business analyst", "project delivery", "stakeholder", "data analysis") if term in entry_lower)
        if intent == "star" and any(term in entry_lower for term in ("situation", "task", "action", "result", "challenge")):
            score += 3
        # Boost org/domain/sector entries for industry-type questions so they outrank skill bullets
        if _industry_question and (
            entry.startswith("Organisation:")
            or "domain:" in entry_lower
            or "sector:" in entry_lower
        ):
            score += 6
        if score > 0:
            scored.append((score, entry))

    scored.sort(reverse=True, key=lambda x: x[0])

    # For industry questions, always include ALL org/domain entries regardless of limit
    if _industry_question:
        org_entries = {e for s, e in scored if e.startswith("Organisation:") or "domain:" in e.lower() or "sector:" in e.lower()}
        top_scored = scored[:limit]
        extra = [(s, e) for s, e in scored[limit:] if e in org_entries]
        return kept_words, top_scored + extra

    return kept_words, scored[:limit]

BASE_SYSTEM_PROMPT = (
    "You answer recruiter questions about candidate Rob Voto based strictly on the supplied CV text. "
    "CRITICAL RULE: Every point in your answer must be anchored to a specific organisation and time period. "
    "Never write generic skill-list answers. Always say where and when. "
    "Lead with the most recent and directly relevant experience. "
    "Do not invent or infer experience not clearly described in the CV. "
    "If the answer is not in the supplied text, say exactly: 'I can't find that in the CV text I was given.' "
    "Keep answers concise: 2-4 specific role-anchored points unless the question asks for more detail."
)

INDUSTRY_SYSTEM_PROMPT = (
    "INSTRUCTION FOR INDUSTRY/SECTOR QUESTIONS: "
    "The CV context contains organisations from BOTH government and commercial sectors. "
    "You MUST list every single organisation from the CV context — do not omit any. "
    "Structure your answer with two sections: first '**Government / Public Sector**' then '**Commercial / Private Sector**'. "
    "For each organisation, show: Organisation name — Domain/sector. "
    "Do not stop at 5. Include all organisations from the context under the correct section. "
    "The concise-4-points rule does NOT apply to this question type — list all organisations."
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


def build_system_prompt(question: str, context: str, detail_level: str = "concise") -> str:
    question_lower = question.lower()
    system_parts = [BASE_SYSTEM_PROMPT]

    if "STAR EXAMPLE:" in context:
        system_parts.append(STAR_SYSTEM_PROMPT)

    if "bpmn" in question_lower:
        system_parts.append(BPMN_SYSTEM_PROMPT)

    if any(term in question_lower for term in ("why rob", "good fit", "summarise rob", "summarize rob", "fit for", "why is rob")):
        system_parts.append(FIT_QUESTION_PROMPT)

    if any(term in question_lower for term in ("industry", "industries", "sector", "sectors", "department", "departments", "organisation", "organizations", "worked in", "background in")):
        system_parts.append(INDUSTRY_SYSTEM_PROMPT)

    if any(term in question_lower for term in ("tool", "tools", "technology", "technologies", "tech stack", "stack")):
        system_parts.append(TOOLS_SYSTEM_PROMPT)

    if detail_level == "detailed":
        system_parts.append(
            "When the user chooses a detailed answer, provide one additional concrete example or evidence point, ideally from different roles or outcomes. "
            "Keep the response professional and focused on recruiter needs."
        )

    return "\n\n".join(system_parts)


def llm_rewrite_answer(question: str, context: str, detail_level: str = "concise") -> str:
    system_prompt = build_system_prompt(question, context, detail_level)
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


@app.get("/ready")
def ready():
    return {
        "ok": bool(CV_BODY),
        "cv_loaded": bool(CV_BODY),
        "star_loaded": bool(STAR_TEXT),
        "cv_length": len(CV_BODY),
        "star_length": len(STAR_TEXT),
    }


@app.get("/status")
def status():
    return {
        "cv_loaded": bool(CV_BODY),
        "star_loaded": bool(STAR_TEXT),
        "cv_length": len(CV_BODY),
        "star_length": len(STAR_TEXT),
        "star_blocks": count_star_blocks(STAR_TEXT or ""),
    }


@app.get("/analytics")
def analytics():
    return analytics_summary()


@app.get("/admin_state")
def admin_state():
    return {
        "cv_loaded": bool(CV_BODY),
        "star_loaded": bool(STAR_TEXT),
        "cv_length": len(CV_BODY),
        "star_length": len(STAR_TEXT),
        "cv_text": CV_BODY,
        "star_text": STAR_TEXT,
        "cv_file": get_file_metadata(CV_FILE),
        "star_file": get_file_metadata(STAR_FILE),
    }


@app.get("/api/admin_state")
def api_admin_state():
    return admin_state()


@app.get("/api/analytics")
def api_analytics():
    return analytics()


@app.get("/api/reload")
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
    return {
        "ok": True,
        "service": "knowMe agent API",
        "version": "1.0",
        "api_docs": "/api/docs",
    }


@app.get("/api/docs")
def api_docs():
    return {
        "service": "knowMe agent API",
        "version": "1.0",
        "description": "Agent-friendly endpoints for CV/STAR ingestion, status, analytics, and question answering.",
        "endpoints": [
            {"method": "GET", "path": "/api/ready", "description": "Readiness state for loaded CV and STAR content."},
            {"method": "GET", "path": "/api/status", "description": "Backend status with loaded file metrics."},
            {"method": "GET", "path": "/api/admin_state", "description": "Loaded CV and STAR text, plus metadata."},
            {"method": "GET", "path": "/api/analytics", "description": "Question analytics, intent distribution, and recent questions."},
            {"method": "GET", "path": "/api/reload", "description": "Reload content from disk and refresh in-memory state."},
            {"method": "POST", "path": "/api/ingest_cv", "description": "Ingest CV text into backend storage."},
            {"method": "POST", "path": "/api/ingest_star", "description": "Ingest STAR text into backend storage."},
            {"method": "POST", "path": "/api/ask", "description": "Ask a recruiter-style question and receive an answer plus metadata."},
        ],
    }


@app.post("/api/ingest_cv")
def api_ingest_cv(payload: dict):
    return ingest(payload)


@app.post("/api/ingest_star")
def api_ingest_star(payload: dict):
    return ingest_star(payload)


@app.post("/api/ask")
def api_ask(payload: dict):
    return ask(payload)


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
    detail_level = payload.get("detail_level", "concise")

    if len(question) > MAX_QUESTION_CHARS:
        return {"answer": f"Please shorten your question to under {MAX_QUESTION_CHARS} characters."}

    if not CV_BODY:
        return {"answer": "No CV loaded yet."}

    name = payload.get("name")
    company = payload.get("company")
    log_question(question, name, company)

    q_norm = normalize_question_text(question)
    q_canonical = canonical_question_text(question)

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
    system_prompt = build_system_prompt(question, full_context, detail_level)
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
                "q_norm": q_norm,
                "q_canonical": q_canonical,
            })
        return response

    final_answer = bullets
    answer_source = "retrieval"
    llm_error = None

    if llm_would_run:
        try:
            final_answer = llm_rewrite_answer(question, full_context, detail_level)
            answer_source = "llm"
        except Exception as exc:
            llm_error = str(exc)
            if bullets:
                final_answer = bullets
            else:
                final_answer = ["LLM unavailable and no retrieval answer is available."]
            answer_source = "fallback"

    if llm_would_run:
        print("\n===== FULL CONTEXT SENT TO LLM =====")
        print(full_context[:2000])
        print("===== END CONTEXT (first 2000 chars) =====\n")

    intent = classify_question_intent(question)
    follow_up_questions = suggest_followup_questions(intent, question)

    response: dict[str, str | list[str] | bool] = {
        "answer": final_answer,
        "answer_source": answer_source,
        "follow_up_questions": follow_up_questions,
    }
    if llm_error:
        response["llm_error"] = llm_error

    if debug or preview_context:
        response.update({
            "intent": intent,
            "detail_level": detail_level,
            "use_star": use_star,
            "star_found": bool(star_blocks),
            "star": star_blocks,
            "q_norm": q_norm,
            "q_canonical": q_canonical,
            "kept_words": kept_words,
            "bullets": bullets,
            "preview_context": full_context,
            "system_prompt": system_prompt,
            "llm_requested": use_llm,
            "llm_executed": llm_would_run,
            "answer_source": answer_source,
        })

    return response
