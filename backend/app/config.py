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

PROHIBITED_REQUEST_TERMS = (
    "date of birth",
    "dob",
    "birth date",
    "birthplace",
    "place of birth",
    "country of birth",
    "home address",
    "street address",
    "mailing address",
    "postal address",
    "address",
    "phone number",
    "mobile number",
    "telephone number",
    "phone",
    "passport number",
    "passport details",
    "passport",
    "sexual orientation",
    "sexual inclination",
    "sexual preference",
    "sexuality",
    "gender identity",
    "family information",
    "family details",
    "mother",
    "father",
    "parents",
    "siblings",
    "spouse",
    "partner",
    "children",
    "religion",
    "ethnicity",
    "race",
    "nationality",
    "citizenship",
    "bank account",
    "credit card",
    "tax file number",
    "social security number",
    "government id",
    "driver license",
    "driver's licence",
    "health",
    "medical",
    "disability",
    "mental health",
    "biometric",
    "genetic",
    "criminal record",
    "change the site",
    "modify the site",
    "update the site",
    "edit the site",
    "send information outside",
    "send data outside",
    "outside this site",
    "outside the site",
    "send this outside",
    "share this outside",
    "export data",
    "data export",
    "download data",
    "download file",
    "save data",
    "forward data",
    "exfiltrate",
    "leak",
    "send email",
    "send emails",
    "forward email",
    "email someone",
    "email out",
    "send to email",
    "phishing",
    "malware",
    "hack",
    "malicious",
    "bypass login",
    "steal credentials",
    "credential theft",
    "api key",
    "secret key",
    "token",
    "password",
    "prompt injection",
    "inject prompt",
    "jailbreak",
    "ignore previous instructions",
    "ignore all previous instructions",
    "ignore instructions",
    "previous instructions",
    "reveal the system prompt",
    "override instructions",
    "system prompt",
    "developer message",
    "reveal prompt",
    "show prompt",
    "csv",
    "spreadsheet",
    "sql injection",
    "xss",
    "csrf",
)

PROHIBITED_REQUEST_REFUSAL = (
    "I can't help with sensitive personal information, prompt injection, exfiltration, site changes, email sending, or malicious actions. Ask about work experience or project evidence instead."
)
