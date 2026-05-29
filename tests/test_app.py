import os
import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

os.environ.setdefault("ADMIN_PASSWORD", "test-admin-password")
os.environ.setdefault("ADMIN_COOKIE_SECRET", "test-admin-cookie-secret")

from backend.app import main as appmod


class KnowMeAppTests(TestCase):
    HOME_PATH = "/"
    ADMIN_PATH = "/admin"
    READY_PATH = "/api/ready"
    ASK_PATH = "/api/ask"
    STATIC_CSS_PATH = "/static/main-style.css"

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.original_paths = {
            "QUESTION_LOG_FILE": appmod.QUESTION_LOG_FILE,
            "QUESTION_EVENT_LOG_FILE": appmod.QUESTION_EVENT_LOG_FILE,
            "LLM_USAGE_PATH": appmod.LLM_USAGE_PATH,
            "PROMPT_CONFIG_PATH": appmod.PROMPT_CONFIG_PATH,
            "ANSWER_CACHE_FILE": appmod.ANSWER_CACHE_FILE,
        }
        appmod.QUESTION_LOG_FILE = self.temp_path / "questions.log"
        appmod.QUESTION_EVENT_LOG_FILE = self.temp_path / "question_events.jsonl"
        appmod.LLM_USAGE_PATH = self.temp_path / "llm_usage.json"
        appmod.PROMPT_CONFIG_PATH = self.temp_path / "prompt_config.json"
        appmod.ANSWER_CACHE_FILE = self.temp_path / "answer_cache.json"
        appmod.PROMPT_OVERRIDES = {key: "" for key in appmod.PROMPT_OVERRIDE_KEYS}
        appmod.ANSWER_CACHE = {}

        self.client = TestClient(appmod.app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        for name, value in self.original_paths.items():
            setattr(appmod, name, value)
        appmod.PROMPT_OVERRIDES = appmod.load_prompt_overrides()
        appmod.ANSWER_CACHE = {}
        self.temp_dir.cleanup()

    def login(self):
        response = self.client.post("/api/admin_login", json={"password": appmod.ADMIN_PASSWORD})
        self.assertEqual(response.status_code, 200)

    def assert_html_contains(self, response, *snippets):
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers.get("content-type", ""))
        body = response.text
        for snippet in snippets:
            self.assertIn(snippet, body)

    def assert_css_contains(self, response, *snippets):
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/css", response.headers.get("content-type", ""))
        body = response.text
        for snippet in snippets:
            self.assertIn(snippet, body)

    def test_home_page_contains_expected_ui(self):
        response = self.client.get(self.HOME_PATH)
        body = response.text
        self.assert_html_contains(
            response,
            "KnowMe",
            "Rob Voto",
            "Use KnowMe to explore real project evidence, examples, tools, and role fit.",
            "Senior Business Analyst focused on complex delivery, process, data, and AI-enabled workflow systems.",
            "Evidence",
            "Delivery",
            "AI / automation",
            "label-tip-group",
            "Question template",
            "For better answers, ask a specific question",
            "Stakeholder example",
            "Process improvement",
            "Technical teams",
            "index.js?v=public1",
            ">i</span>",
            "askBtn",
            "main-style.css?v=hero21",
        )

    def test_admin_page_contains_expected_endpoints(self):
        response = self.client.get(self.ADMIN_PATH)
        self.assert_html_contains(
            response,
            "adminPassword",
            "/api/admin_login",
            "/api/ask",
            "/api/ingest_cv",
            "/api/ingest_star",
            "Backend logs are written",
            "Reads the current CV, STAR, and prompt files from disk",
            "Saving here writes to <code>backend/data/cv.txt</code>",
        )

    def test_startup_loads_content(self):
        ready = self.client.get(self.READY_PATH)
        self.assertEqual(ready.status_code, 200)

        payload = ready.json()
        self.assertIn("ok", payload)
        self.assertTrue(payload["cv_loaded"])
        self.assertTrue(payload["star_loaded"])
        self.assertGreater(payload["cv_length"], 0)
        self.assertGreater(payload["star_length"], 0)

    def test_admin_routes_require_login(self):
        self.assertEqual(self.client.get("/api/admin_state").status_code, 401)
        self.assertEqual(self.client.get("/api/admin_prompts").status_code, 401)

    def test_admin_login_and_state(self):
        self.login()
        state = self.client.get("/api/admin_state")
        self.assertEqual(state.status_code, 200)
        payload = state.json()
        self.assertTrue(payload["cv_loaded"])
        self.assertTrue(payload["star_loaded"])
        self.assertIn("llm_budget", payload)
        self.assertIn("prompt_overrides", payload)

    def test_admin_prompt_round_trip(self):
        self.login()
        get_resp = self.client.get("/api/admin_prompts")
        self.assertEqual(get_resp.status_code, 200)
        post_resp = self.client.post(
            "/api/admin_prompts",
            json={"overrides": {"base": "Do not mention years unless the user specifically asks for them."}},
        )
        self.assertEqual(post_resp.status_code, 200)
        self.assertTrue(appmod.PROMPT_CONFIG_PATH.exists())
        self.assertTrue(post_resp.json()["overrides"]["base"].startswith("Do not mention years"))
        persisted = self.client.get("/api/admin_prompts").json()
        self.assertTrue(persisted["overrides"]["base"].startswith("Do not mention years"))

    def test_retrieval_only_ask(self):
        response = self.client.post(
            self.ASK_PATH,
            json={"question": "What tools has Rob used?", "use_llm": False, "debug": False},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["answer_source"], "none")
        self.assertEqual(payload["answer"], "Enable 'Use AI rewrite' to get an answer.")

    def test_empty_question_is_rejected_before_retrieval_or_llm(self):
        with patch.object(appmod, "log_question") as fake_log:
            response = self.client.post(
                self.ASK_PATH,
                json={"question": "   ", "use_llm": True, "debug": False},
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "Please type a question.")
        fake_log.assert_not_called()

    def test_public_javascript_contract(self):
        response = self.client.get("/static/index.js")
        self.assertEqual(response.status_code, 200)
        js = response.text
        self.assertIn("submitQuestion", js)
        self.assertIn("/api/ask", js)
        self.assertIn("/api/ready", js)
        self.assertIn("event.key === 'Enter'", js)
        self.assertIn("Please type a question.", js)

    def test_static_css_loads_expected_tokens(self):
        response = self.client.get(self.STATIC_CSS_PATH)
        self.assert_css_contains(
            response,
            "--accent",
            ".hero",
            "#askBtn",
            "font-family: var(--font-ui)",
            "font-weight: 800",
            "min-height: 78px",
            "align-items: center",
            "text-align: center",
            ".section-heading",
            ".label-tip-group",
        )

    def test_extract_client_ip_ignores_spoofed_forwarded_headers(self):
        request = appmod.Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/ask",
                "headers": [
                    (b"x-forwarded-for", b"1.2.3.4"),
                    (b"x-real-ip", b"5.6.7.8"),
                ],
                "client": ("203.0.113.9", 12345),
                "query_string": b"",
                "scheme": "http",
                "server": ("testserver", 80),
            }
        )

        self.assertEqual(appmod.extract_client_ip(request), "203.0.113.9")

    def test_llm_ask_path_uses_rewrite(self):
        captured = {}

        def fake_budget(*args, **kwargs):
            return None

        def fake_rewrite(question, detail_level="concise"):
            captured["question"] = question
            captured["detail_level"] = detail_level
            return "Rewritten answer.", 123

        def fake_record(logging_context, tokens_used):
            captured["tokens_used"] = tokens_used

        with patch.object(appmod, "enforce_llm_rate_limit", fake_budget), patch.object(appmod, "llm_answer", fake_rewrite), patch.object(appmod, "record_llm_usage", fake_record):
            response = self.client.post(
                self.ASK_PATH,
                json={"question": "Why is Rob a good fit?", "use_llm": True, "debug": False},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["answer_source"], "llm")
        self.assertEqual(payload["answer"], "Rewritten answer.")
        self.assertEqual(captured["tokens_used"], 123)

    def test_llm_answer_cache_skips_second_rewrite(self):
        call_count = {"rewrite": 0}

        def fake_budget(*args, **kwargs):
            return None

        def fake_rewrite(question, context, detail_level="concise"):
            call_count["rewrite"] += 1
            return "Cached answer.", 111

        with patch.object(appmod, "enforce_llm_rate_limit", fake_budget), patch.object(appmod, "llm_answer", fake_rewrite):
            first = self.client.post(
                self.ASK_PATH,
                json={"question": "Why is Rob a good fit?", "use_llm": True, "debug": False},
            )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["answer"], "Cached answer.")
        self.assertEqual(call_count["rewrite"], 1)
        self.assertTrue(appmod.ANSWER_CACHE_FILE.exists())

        def fail_rewrite(*args, **kwargs):
            raise AssertionError("llm_answer should not be called on cache hit")

        with patch.object(appmod, "enforce_llm_rate_limit", fake_budget), patch.object(appmod, "llm_answer", fail_rewrite):
            second = self.client.post(
                self.ASK_PATH,
                json={"question": "Why is Rob a good fit?", "use_llm": True, "debug": False},
            )
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["answer"], "Cached answer.")
        self.assertEqual(call_count["rewrite"], 1)

    def test_llm_budget_blocks_when_cap_reached(self):
        today = appmod.utc_today_key()
        with patch.object(appmod, "LLM_DAILY_TOKEN_CAP", 100), patch.object(
            appmod,
            "load_llm_usage",
            return_value={today: {"tokens_used": 100, "identities": {}}},
        ):
            request = type("Req", (), {"cookies": {}})()
            logging_context = {
                "client_id": "client-1",
                "client_ip_hash": "ip-1",
                "session_id": "session-1",
                "request_id": "req-1",
            }
            with self.assertRaises(HTTPException) as exc:
                appmod.enforce_llm_rate_limit(
                    request=request,
                    logging_context=logging_context,
                )
        self.assertEqual(exc.exception.status_code, 429)
        self.assertIn("daily limit reached", exc.exception.detail.lower())
