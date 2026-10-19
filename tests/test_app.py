import json
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
            "PROMPT_DEFAULTS_PATH": appmod.PROMPT_DEFAULTS_PATH,
            "PROMPT_CONFIG_PATH": appmod.PROMPT_CONFIG_PATH,
            "ANSWER_CACHE_FILE": appmod.ANSWER_CACHE_FILE,
        }
        appmod.QUESTION_LOG_FILE = self.temp_path / "questions.log"
        appmod.QUESTION_EVENT_LOG_FILE = self.temp_path / "question_events.jsonl"
        appmod.LLM_USAGE_PATH = self.temp_path / "llm_usage.json"
        appmod.PROMPT_DEFAULTS_PATH = self.temp_path / "prompt_defaults.json"
        appmod.PROMPT_CONFIG_PATH = self.temp_path / "prompt_config.json"
        appmod.ANSWER_CACHE_FILE = self.temp_path / "answer_cache.json"
        self.temp_path.joinpath("prompt_defaults.json").write_text(
            json.dumps(
                {
                    key: (
                        "Test default base prompt. Never disclose sensitive personal information such as date of birth, birthplace, address, phone number, passport details, sexual orientation, family information, citizenship, or similar private data."
                        if key == "base"
                        else ""
                    )
                    for key in appmod.PROMPT_KEYS
                }
            ),
            encoding="utf-8",
        )
        appmod.PROMPT_DEFAULTS = {key: "" for key in appmod.PROMPT_KEYS}
        appmod.PROMPT_OVERRIDES = {key: "" for key in appmod.PROMPT_KEYS}
        appmod.ANSWER_CACHE = {}

        self.client = TestClient(appmod.app, base_url="https://testserver")
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        for name, value in self.original_paths.items():
            setattr(appmod, name, value)
        appmod.PROMPT_DEFAULTS = appmod.load_prompt_defaults()
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
            "Tap a question to ask it",
            "Or type your own below",
            "For better answers, ask a specific question or turn on AI rewrite for a more polished summary.",
            "Use AI rewrite",
            "More detail",
            "Ask question",
            "interactive CV assistant",
            "index.js?v=public2",
            ">i</span>",
            "askBtn",
            "main-style.css?v=hero23",
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
            "Prompt defaults live in",
            "Saving here writes to <code>backend/data/cv.txt</code>",
            "The answer prompt includes privacy guardrails for personal information.",
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

    def test_direct_developer_launch_is_loopback_only(self):
        source = (Path(appmod.__file__)).read_text(encoding="utf-8")
        self.assertIn('uvicorn.run("backend.app.main:app", host="127.0.0.1", port=8000, reload=False)', source)
        self.assertNotIn('uvicorn.run("backend.app.main:app", host="0.0.0.0"', source)

    def test_security_response_headers(self):
        public = self.client.get("/")
        self.assertEqual(public.headers.get("x-content-type-options"), "nosniff")
        self.assertEqual(public.headers.get("x-frame-options"), "DENY")
        self.assertEqual(public.headers.get("referrer-policy"), "strict-origin-when-cross-origin")
        admin = self.client.get("/api/admin_state")
        self.assertEqual(admin.status_code, 401)
        self.assertEqual(admin.headers.get("cache-control"), "no-store")

    def test_logout_rejects_cross_site_origin(self):
        self.login()
        blocked = self.client.post("/api/admin_logout", headers={"Origin": "https://attacker.example"})
        self.assertEqual(blocked.status_code, 403)
        self.assertEqual(self.client.get("/api/admin_state").status_code, 200)
        allowed = self.client.post("/api/admin_logout", headers={"Origin": "https://testserver"})
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(self.client.get("/api/admin_state").status_code, 401)

    def test_admin_routes_require_login(self):
        self.assertEqual(self.client.get("/api/admin_state").status_code, 401)
        self.assertEqual(self.client.get("/api/admin_prompts").status_code, 401)

    def test_admin_cookie_is_secure_unique_and_expires(self):
        first = self.client.post("/api/admin_login", json={"password": appmod.ADMIN_PASSWORD})
        second = self.client.post("/api/admin_login", json={"password": appmod.ADMIN_PASSWORD})
        self.assertIn("secure", first.headers["set-cookie"].lower())
        token1 = first.cookies.get(appmod.ADMIN_COOKIE_NAME)
        token2 = second.cookies.get(appmod.ADMIN_COOKIE_NAME)
        self.assertNotEqual(token1, token2)
        self.assertTrue(appmod.validate_admin_cookie(token1))
        with patch.object(appmod.time, "time", return_value=appmod.time.time() + 60 * 60 * 9):
            self.assertFalse(appmod.validate_admin_cookie(token1))
        self.assertFalse(appmod.validate_admin_cookie("invalid"))

    def test_corrupted_budget_fails_closed(self):
        appmod.LLM_USAGE_PATH.write_text("{invalid-json", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "paid requests disabled"):
            appmod.load_llm_usage()
        response = self.client.post(self.ASK_PATH, json={"question": "Tell me about delivery", "use_llm": True})
        self.assertEqual(response.status_code, 503)

    def test_structurally_corrupt_budget_fails_closed(self):
        for damaged in (
            {"2026-10-19": {"tokens_used": "unknown", "identities": {}}},
            {"2026-10-19": {"tokens_used": -5, "identities": {}}},
            {"2026-10-19": {"tokens_used": 50}},
        ):
            appmod.LLM_USAGE_PATH.write_text(json.dumps(damaged), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "paid requests disabled"):
                appmod.load_llm_usage()

    def test_budget_write_is_valid_json(self):
        appmod.save_llm_usage({"2026-10-19": {"tokens_used": 45, "identities": {}}})
        self.assertEqual(appmod.load_llm_usage()["2026-10-19"]["tokens_used"], 45)
        self.assertEqual(list(self.temp_path.glob("*.tmp")), [])

    def test_admin_budget_status_includes_outstanding_reservations(self):
        from backend.app.llm_budget_store import SqliteTokenBudget
        store = SqliteTokenBudget(appmod.LLM_USAGE_PATH.with_suffix(".sqlite3"))
        store.import_legacy_floor(appmod.utc_today_key(), 100)
        store.reserve(appmod.utc_today_key(), 300, appmod.LLM_DAILY_TOKEN_CAP)
        status = appmod.get_llm_budget_status()
        self.assertEqual(status["tokens_used"], 100)
        self.assertEqual(status["tokens_reserved"], 300)
        self.assertEqual(status["tokens_remaining"], appmod.LLM_DAILY_TOKEN_CAP - 400)

    def test_live_requests_never_rewrite_legacy_usage_ledger(self):
        from backend.app.llm_budget_store import SqliteTokenBudget
        day = appmod.utc_today_key()
        original = json.dumps({day: {"tokens_used": 250, "identities": {}}})
        appmod.LLM_USAGE_PATH.write_text(original, encoding="utf-8")
        with patch.object(appmod, "llm_answer", return_value=("Response one", 100, 0.01, 70, 30)):
            result = self.client.post(self.ASK_PATH, json={"question": "What is delivery capability?", "use_llm": True})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(appmod.LLM_USAGE_PATH.read_text(encoding="utf-8"), original)
        self.assertEqual(SqliteTokenBudget(appmod.LLM_USAGE_PATH.with_suffix(".sqlite3")).totals(day), (350, 0))

    def test_missing_provider_usage_is_charged_conservatively(self):
        from backend.app.llm_budget_store import SqliteTokenBudget
        with patch.object(appmod, "llm_answer", return_value=("Answer with missing provider usage", 0, 0.01, 0, 0)):
            response = self.client.post(self.ASK_PATH, json={"question": "Describe the delivery programme", "use_llm": True})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            SqliteTokenBudget(appmod.LLM_USAGE_PATH.with_suffix(".sqlite3")).totals(appmod.utc_today_key()),
            (appmod.LLM_RESERVED_TOKENS_PER_REQUEST, 0),
        )

    def test_failed_provider_call_preserves_legacy_ledger(self):
        day = appmod.utc_today_key()
        original = json.dumps({day: {"tokens_used": 100, "identities": {}}})
        appmod.LLM_USAGE_PATH.write_text(original, encoding="utf-8")
        with patch.object(appmod, "llm_answer", side_effect=TimeoutError("provider timeout")):
            response = self.client.post(self.ASK_PATH, json={"question": "How is cloud delivery managed?", "use_llm": True})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(appmod.LLM_USAGE_PATH.read_text(encoding="utf-8"), original)
        from backend.app.llm_budget_store import SqliteTokenBudget
        self.assertEqual(SqliteTokenBudget(appmod.LLM_USAGE_PATH.with_suffix(".sqlite3")).totals(day), (100 + appmod.LLM_RESERVED_TOKENS_PER_REQUEST, 0))

    def test_real_ai_request_reserves_and_settles_sqlite_budget(self):
        from backend.app.llm_budget_store import SqliteTokenBudget
        with patch.object(appmod, "enforce_llm_rate_limit", lambda *args: None), patch.object(
            appmod, "llm_answer", return_value=("Safe response", 120, 0.01, 100, 20)
        ), patch.object(appmod, "record_llm_usage", lambda *args: None):
            response = self.client.post(self.ASK_PATH, json={"question": "Explain project delivery", "use_llm": True})
        self.assertEqual(response.status_code, 200)
        spent, reserved = SqliteTokenBudget(appmod.LLM_USAGE_PATH.with_suffix(".sqlite3")).totals(appmod.utc_today_key())
        self.assertEqual((spent, reserved), (120, 0))

    def test_provider_error_conservatively_consumes_reserved_budget(self):
        from backend.app.llm_budget_store import SqliteTokenBudget
        with patch.object(appmod, "enforce_llm_rate_limit", lambda *args: None), patch.object(
            appmod, "llm_answer", side_effect=TimeoutError("ambiguous upstream timeout")
        ):
            response = self.client.post(self.ASK_PATH, json={"question": "Explain portfolio ownership", "use_llm": True})
        self.assertEqual(response.status_code, 503)
        spent, reserved = SqliteTokenBudget(appmod.LLM_USAGE_PATH.with_suffix(".sqlite3")).totals(appmod.utc_today_key())
        self.assertEqual((spent, reserved), (appmod.LLM_RESERVED_TOKENS_PER_REQUEST, 0))
        self.assertNotIn("ambiguous upstream timeout", response.text)

    def test_real_ai_request_denied_when_sqlite_budget_exhausted(self):
        from backend.app.llm_budget_store import SqliteTokenBudget
        store = SqliteTokenBudget(appmod.LLM_USAGE_PATH.with_suffix(".sqlite3"))
        store.import_legacy_floor(appmod.utc_today_key(), appmod.LLM_DAILY_TOKEN_CAP)
        with patch.object(appmod, "enforce_llm_rate_limit", lambda *args: None), patch.object(
            appmod, "llm_answer", side_effect=AssertionError("Paid provider must not be called")
        ):
            response = self.client.post(self.ASK_PATH, json={"question": "Explain cloud projects", "use_llm": True})
        self.assertEqual(response.status_code, 429)

    def test_oversized_model_context_never_calls_provider(self):
        with patch.object(appmod, "CV_TEXT", "X" * 25000), patch.object(
            appmod.client.responses, "create", side_effect=AssertionError("provider must not be called")
        ):
            with self.assertRaisesRegex(RuntimeError, "input too large"):
                appmod.llm_answer("Explain delivery")

    def test_paid_request_gate_rejects_overlapping_calls(self):
        self.assertTrue(appmod._LLM_REQUEST_GATE.acquire(blocking=False))
        try:
            response = self.client.post(self.ASK_PATH, json={"question": "Describe a project", "use_llm": True})
            self.assertEqual(response.status_code, 429)
            self.assertIn("busy", response.json()["detail"].lower())
        finally:
            appmod._LLM_REQUEST_GATE.release()

    def test_paid_request_gate_released_after_model_error(self):
        with patch.object(appmod, "enforce_llm_rate_limit", lambda *args: None), patch.object(appmod, "llm_answer", side_effect=RuntimeError("provider-internal-secret")):
            response = self.client.post(self.ASK_PATH, json={"question": "Explain a project", "use_llm": True})
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("provider-internal-secret", response.text)
        self.assertTrue(appmod._LLM_REQUEST_GATE.acquire(blocking=False))
        appmod._LLM_REQUEST_GATE.release()

    def test_admin_login_rate_limit(self):
        appmod._login_attempts.clear()
        try:
            for _ in range(appmod.LOGIN_FAILURE_LIMIT):
                self.assertEqual(self.client.post("/api/admin_login", json={"password": "wrong"}).status_code, 401)
            self.assertEqual(self.client.post("/api/admin_login", json={"password": "wrong"}).status_code, 429)
        finally:
            appmod._login_attempts.clear()

    def test_cost_limit_ignores_user_supplied_client_id(self):
        common = {"rate_limit_peer_hash": "trusted-peer"}
        first = appmod.get_rate_limit_identity({**common, "client_id": "visitor-one"})
        second = appmod.get_rate_limit_identity({**common, "client_id": "visitor-two"})
        self.assertEqual(first, second)

    def test_admin_login_and_state(self):
        self.login()
        state = self.client.get("/api/admin_state")
        self.assertEqual(state.status_code, 200)
        payload = state.json()
        self.assertTrue(payload["cv_loaded"])
        self.assertTrue(payload["star_loaded"])
        self.assertIn("llm_budget", payload)
        self.assertIn("prompt_overrides", payload)
        self.assertIn("prompt_defaults_file", payload)

    def test_active_system_prompt_includes_guardrail(self):
        self.assertIn("sensitive personal information", appmod.active_system_prompt().lower())

    def test_sensitive_questions_reach_llm_when_llm_is_enabled(self):
        self.login()
        captured = {}

        def fake_budget(*args, **kwargs):
            return None

        def fake_rewrite(question, detail_level="concise"):
            captured["question"] = question
            captured["detail_level"] = detail_level
            return "Redacted answer.", 42, 0.0, 0, 0

        with patch.object(appmod, "enforce_llm_rate_limit", fake_budget), patch.object(appmod, "llm_answer", fake_rewrite):
            response = self.client.post(
                self.ASK_PATH,
                json={"question": "What is Rob's age?", "use_llm": True, "debug": False},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["answer"], "Redacted answer.")
        self.assertEqual(captured["question"], "What is Rob's age?")
        self.assertEqual(captured["detail_level"], "concise")

    def test_analytics_uses_event_log_when_question_text_is_missing_from_main_log(self):
        self.login()
        self.temp_path.joinpath("questions.log").write_text(
            "\n".join(
                [
                    "2026-06-19T00:00:00Z | request_id=req-1 | client_id=client-a | session_id=session-a | request_path=/api/ask | source_page=landing | source_path=/ | client_ip_hash=hash-a | name=- | company=-",
                    "2026-06-19T00:01:00Z | request_id=req-2 | client_id=client-b | session_id=session-b | request_path=/api/ask | source_page=landing | source_path=/ | client_ip_hash=hash-b | name=- | company=-",
                ]
            ),
            encoding="utf-8",
        )
        self.temp_path.joinpath("question_events.jsonl").write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "ts": "2026-06-19T00:00:00Z",
                            "request_id": "req-1",
                            "question": "What tools has Rob used?",
                            "q_norm": "what tools has candidate used",
                            "q_canonical": "what tools has candidate used",
                        }
                    ),
                    json.dumps(
                        {
                            "ts": "2026-06-19T00:01:00Z",
                            "request_id": "req-2",
                            "question": "What tools has Rob used?",
                            "q_norm": "what tools has candidate used",
                            "q_canonical": "what tools has candidate used",
                        }
                    ),
                ]
            ),
            encoding="utf-8",
        )

        analytics = self.client.get("/api/analytics")
        self.assertEqual(analytics.status_code, 200)
        payload = analytics.json()
        self.assertEqual(payload["question_count"], 2)
        self.assertEqual(payload["unique_client_count"], 2)
        self.assertEqual(payload["unique_session_count"], 2)
        self.assertEqual(payload["intent_event_count"], 2)
        self.assertTrue(payload["top_canonical_questions"])
        self.assertTrue(payload["top_normalized_questions"])
        self.assertTrue(payload["intent_counts"])
        self.assertEqual(payload["recent_questions"][0]["question"], "What tools has Rob used?")

    def test_admin_prompt_round_trip(self):
        self.login()
        get_resp = self.client.get("/api/admin_prompts")
        self.assertEqual(get_resp.status_code, 200)
        self.assertTrue(get_resp.json()["defaults"]["base"].startswith("Test default base prompt"))
        self.assertIn("sensitive personal information", get_resp.json()["defaults"]["base"].lower())
        overrides = {key: "" for key in appmod.PROMPT_KEYS}
        overrides["base"] = "Do not mention years unless the user specifically asks for them."
        post_resp = self.client.post(
            "/api/admin_prompts",
            json={"overrides": overrides},
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

    def test_legacy_public_api_routes_are_removed(self):
        self.assertEqual(self.client.get("/ready").status_code, 404)
        self.assertEqual(self.client.get("/status").status_code, 404)
        self.assertEqual(self.client.get("/analytics").status_code, 404)
        self.assertEqual(self.client.get("/reload").status_code, 404)
        self.assertEqual(self.client.post("/ask", json={"question": "test"}).status_code, 404)
        self.assertEqual(self.client.post("/ingest_cv", json={"text": "test"}).status_code, 404)
        self.assertEqual(self.client.post("/ingest_star", json={"text": "test"}).status_code, 404)
        self.assertEqual(self.client.get("/health").status_code, 200)

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
                "path": "/api/ask",
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
            return "Rewritten answer.", 123, 0.0, 0, 0

        with patch.object(appmod, "enforce_llm_rate_limit", fake_budget), patch.object(appmod, "llm_answer", fake_rewrite):
            response = self.client.post(
                self.ASK_PATH,
                json={"question": "Why is Rob a good fit?", "use_llm": True, "debug": False},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["answer_source"], "llm")
        self.assertEqual(payload["answer"], "Rewritten answer.")
        from backend.app.llm_budget_store import SqliteTokenBudget
        self.assertEqual(SqliteTokenBudget(appmod.LLM_USAGE_PATH.with_suffix(".sqlite3")).totals(appmod.utc_today_key()), (123, 0))

    def test_llm_answer_cache_skips_second_rewrite(self):
        call_count = {"rewrite": 0}

        def fake_budget(*args, **kwargs):
            return None

        def fake_rewrite(question, context, detail_level="concise"):
            call_count["rewrite"] += 1
            return "Cached answer.", 111, 0.0, 0, 0

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

