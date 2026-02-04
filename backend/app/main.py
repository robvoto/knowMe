import string
import os
from openai import OpenAI
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# ─────────────────────────
# App & global state
# ─────────────────────────

app = FastAPI(title="knowMe API")

TOP_QUESTIONS = 20
MAX_QUESTION_CHARS = 300

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

MIN_LINE_LENGTH = 25
CV_AUTHORITATIVE = ""
CV_BODY = ""

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ─────────────────────────
# Helper functions (pure logic)
# ─────────────────────────

def clean_line(text: str) -> str:
    return text.lstrip("•-– ").strip()

def dedupe_lines(lines: list[str]) -> list[str]:
    seen = set()
    out = []
    for ln in lines:
        key = ln.lower().strip()
        if key not in seen:
            seen.add(key)
            out.append(ln)
    return out

def find_relevant_sentences(cv_text: str, question: str, limit: int | None = None):
    if limit is None:
        limit = TOP_QUESTIONS

    lines = [ln.strip() for ln in cv_text.splitlines() if ln.strip()]

    kept_words = []
    for w in question.lower().split():
        clean = w.strip(string.punctuation)
        if len(clean) > 3 or clean in IMPORTANT_SHORT_WORDS:
            kept_words.append(clean)

    scored = []
    for line in lines:
        if len(line) < MIN_LINE_LENGTH:
            continue

        l_lower = line.lower()
        score = sum(1 for w in kept_words if w in l_lower)
        if score > 0:
            scored.append((score, line))

    scored.sort(reverse=True, key=lambda x: x[0])
    return kept_words, scored[:limit]
 
def llm_rewrite_answer(question: str, bullets: list[str]) -> str:
    context = "\n".join(f"- {b}" for b in bullets)

    resp = client.responses.create(
        model="gpt-4.1-mini",
        input=[
            {
                "role": "system",
                "content": (
                    "You are an assistant that answers recruiter questions about candidate Rob Voto. "
                    "Answer using ONLY information explicitly stated in the provided CV text. "
                    "Do not invent facts or infer unstated experience. "
                    "If the answer isn't in the provided CV text, say: 'I can't find that in the CV text I was given.' "
                    "You may aggregate, summarise, and list items when the CV clearly contains them. "
                    "Merge duplicates and avoid repeating the same point. "
                    "Prefer clear, professional wording without referencing 'bullets' or internal context. "
                    "If the question explicitly asks for a list, provide a list even if it exceeds the sentence guideline."
                    "When technologies span different periods, distinguish between earlier-career and recent experience if the CV states dates. "
                    "Prefer 1–3 concise sentences unless the question asks for a list."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Question: {question}\n\n"
                    f"CV text:\n{context}\n\n"
                    "Write a concise answer. If asked for a list, provide a short list."
                ),
            },
        ],
    )
    return resp.output_text
 
# ─────────────────────────
# API endpoints
# ─────────────────────────

app.mount("/static", StaticFiles(directory="backend/static"), name="static")

@app.get("/")
def home():
    return FileResponse("backend/static/index.html")

@app.get("/admin")
def admin():
    return FileResponse("backend/static/admin.html")

@app.get("/health")
def health():
    return {"ok": True}
 
@app.post("/ingest")
def ingest(payload: dict):
    global CV_AUTHORITATIVE, CV_BODY

    text = payload.get("text", "")
    if not text:
        return {"error": "No CV text provided"}

    marker = "AUTHORITATIVE DECLARATIONS (READ FIRST)"

    if marker in text:
        before, after = text.split(marker, 1)
        CV_AUTHORITATIVE = marker + after
        CV_BODY = before
    else:
        # fallback: no authoritative section defined
        CV_AUTHORITATIVE = ""
        CV_BODY = text

    return {
        "status": "CV stored",
        "authoritative_length": len(CV_AUTHORITATIVE),
        "body_length": len(CV_BODY),
    }
 
@app.post("/ask")
def ask(payload: dict):
    question = payload.get("question", "")
    debug = bool(payload.get("debug", False))
    use_llm = bool(payload.get("use_llm", False))

    if len(question) > MAX_QUESTION_CHARS:
        return {
            "answer": f"Please shorten your question to under {MAX_QUESTION_CHARS} characters."
        }

    if not CV_BODY:
        return {"answer": "No CV loaded yet."}

    kept_words, top = find_relevant_sentences(CV_BODY, question)

    if not top:
        return {"answer": "I couldn't find anything relevant in the CV."}

    bullets = [clean_line(sentence) for _, sentence in top]
    bullets = dedupe_lines(bullets)

    context_blocks = []

    if CV_AUTHORITATIVE:
        context_blocks.append(
            "AUTHORITATIVE CV INFORMATION:\n" + CV_AUTHORITATIVE.strip()
        )

    if bullets:
        context_blocks.append(
            "RELEVANT EXPERIENCE:\n" + "\n".join(f"- {b}" for b in bullets)
        )

    llm_context = "\n\n".join(context_blocks)

    # Default answer = bullets (no LLM)
    final_answer = bullets

    # Optional LLM rewrite
    if use_llm:
        if not os.getenv("OPENAI_API_KEY"):
            return {"answer": "OPENAI_API_KEY is not set."}
        final_answer = llm_rewrite_answer(question, bullets)

    # One single response block
    response = {"answer": final_answer}

    if debug:
        response.update({
            "kept_words": kept_words,
            "matches": [{"score": score, "text": sentence} for score, sentence in top],
            "bullets": bullets
        })

    return response


