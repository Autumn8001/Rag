import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api import admin_routes, auth_routes, chat_routes
from core import database
from core.models import APIKeyMap, Base, ChatHistory, DocumentRecord, User
from core.rag_engine import METADATA_END_MARKER, METADATA_START_MARKER


class _MockMarkdownResult:
    def __init__(self, text_content: str):
        self.text_content = text_content


class _MockMarkdownConverter:
    def convert(self, _file_path: str):
        return _MockMarkdownResult("# Mock Document\n\nThis is a mock upload.")


async def _fake_stream_rag_answer(_question: str, _history=None, tenant_id: str = "default_tenant"):
    yield f"mock answer for {tenant_id}: "
    yield "done"
    yield (
        f"\n\n{METADATA_START_MARKER}\n"
        '{"chunks":[{"source":"handbook.md","content":"mock chunk"}]}\n'
        f"{METADATA_END_MARKER}"
    )


async def _failing_stream_rag_answer(_question: str, _history=None, tenant_id: str = "default_tenant"):
    yield f"partial answer for {tenant_id}"
    raise RuntimeError("stream interrupted")


class ApiFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        db_path = Path(cls.temp_dir.name) / "test_app.db"
        cls.engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False},
        )
        cls.testing_session_local = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=cls.engine,
        )

        database.engine = cls.engine
        database.SessionLocal = cls.testing_session_local
        Base.metadata.create_all(bind=cls.engine)

        cls.patchers = [
            patch.object(chat_routes, "stream_rag_answer", _fake_stream_rag_answer),
            patch.object(admin_routes, "ingest_knowledge", return_value=True),
            patch.object(database, "clear_all_data", return_value=True),
            patch.object(admin_routes, "md_converter", _MockMarkdownConverter()),
        ]
        for patcher in cls.patchers:
            patcher.start()

        cls.app = FastAPI()
        cls.app.include_router(chat_routes.router)
        cls.app.include_router(auth_routes.router, prefix="/api/v1")
        cls.app.include_router(admin_routes.router, prefix="/api/v1")
        cls.client = TestClient(cls.app)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        for patcher in reversed(cls.patchers):
            patcher.stop()
        cls.engine.dispose()
        cls.temp_dir.cleanup()

    def setUp(self):
        Base.metadata.drop_all(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)

    def _register_and_login(self, username: str, password: str = "Passw0rd_123") -> dict:
        register_response = self.client.post(
            "/api/v1/auth/register",
            json={"username": username, "password": password},
        )
        self.assertEqual(register_response.status_code, 201, register_response.text)

        login_response = self.client.post(
            "/api/v1/auth/login",
            json={"username": username, "password": password},
        )
        self.assertEqual(login_response.status_code, 200, login_response.text)
        return login_response.json()

    def test_register_login_and_me(self):
        register_response = self.client.post(
            "/api/v1/auth/register",
            json={"username": "../bad_user", "password": "Passw0rd_123"},
        )
        self.assertEqual(register_response.status_code, 422)

        token_payload = self._register_and_login("user_alpha")
        me_response = self.client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token_payload['access_token']}"},
        )
        self.assertEqual(me_response.status_code, 200, me_response.text)
        self.assertEqual(me_response.json()["username"], "user_alpha")
        self.assertTrue(me_response.json()["tenant_id"].startswith("tenant_user_alpha_"))

    def test_auth_endpoints_reject_missing_or_invalid_credentials(self):
        missing_auth_response = self.client.get("/api/v1/auth/me")
        self.assertEqual(missing_auth_response.status_code, 401, missing_auth_response.text)
        self.assertIn("缺少认证令牌", missing_auth_response.text)

        invalid_token_response = self.client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer invalid-token"},
        )
        self.assertEqual(invalid_token_response.status_code, 401, invalid_token_response.text)
        self.assertIn("登录凭证无效", invalid_token_response.text)

        invalid_api_key_response = self.client.get(
            "/api/v1/auth/me",
            headers={"X-API-Key": "bad-key"},
        )
        self.assertEqual(invalid_api_key_response.status_code, 401, invalid_api_key_response.text)
        self.assertIn("X-API-Key 无效", invalid_api_key_response.text)

    def test_auth_me_supports_legacy_x_api_key_mapping(self):
        db = self.testing_session_local()
        try:
            db.add(
                APIKeyMap(
                    api_key="legacy-demo-key",
                    tenant_id="tenant_legacy",
                    user_id="legacy_user",
                )
            )
            db.commit()
        finally:
            db.close()

        response = self.client.get(
            "/api/v1/auth/me",
            headers={"X-API-Key": "legacy-demo-key"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["username"], "legacy_user")
        self.assertEqual(payload["tenant_id"], "tenant_legacy")
        self.assertIn("created_at", payload)

    def test_visitor_login_creates_isolated_temporary_user(self):
        first_response = self.client.post("/api/v1/auth/visitor-login")
        second_response = self.client.post("/api/v1/auth/visitor-login")

        self.assertEqual(first_response.status_code, 200, first_response.text)
        self.assertEqual(second_response.status_code, 200, second_response.text)

        first_payload = first_response.json()
        second_payload = second_response.json()

        self.assertTrue(first_payload["username"].startswith("visitor_"))
        self.assertTrue(first_payload["tenant_id"].startswith("tenant_visitor_"))
        self.assertNotEqual(first_payload["tenant_id"], second_payload["tenant_id"])
        self.assertIn("expires_at", first_payload)

        me_response = self.client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {first_payload['access_token']}"},
        )
        self.assertEqual(me_response.status_code, 200, me_response.text)
        self.assertTrue(me_response.json()["is_temporary"])

    def test_expired_temporary_visitor_is_rejected(self):
        visitor_response = self.client.post("/api/v1/auth/visitor-login")
        self.assertEqual(visitor_response.status_code, 200, visitor_response.text)
        payload = visitor_response.json()

        db = self.testing_session_local()
        try:
            visitor = db.query(User).filter(User.username == payload["username"]).first()
            visitor.expires_at = datetime.utcnow() - timedelta(minutes=1)
            db.commit()
        finally:
            db.close()

        me_response = self.client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {payload['access_token']}"},
        )
        self.assertEqual(me_response.status_code, 401, me_response.text)
        self.assertIn("已过期", me_response.text)

    def test_chat_session_history_and_delete_flow(self):
        token_payload = self._register_and_login("chat_user")
        headers = {"Authorization": f"Bearer {token_payload['access_token']}"}
        session_id = "session_test_001"

        chat_response = self.client.post(
            "/api/v1/chat",
            headers=headers,
            json={"question": "What is the policy?", "session_id": session_id},
        )
        self.assertEqual(chat_response.status_code, 200, chat_response.text)
        self.assertEqual(chat_response.headers.get("x-session-id"), session_id)
        self.assertIn("mock answer", chat_response.text)

        sessions_response = self.client.get("/api/v1/sessions", headers=headers)
        self.assertEqual(sessions_response.status_code, 200, sessions_response.text)
        sessions = sessions_response.json()["data"]
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["session_id"], session_id)

        history_response = self.client.get(f"/api/v1/history/{session_id}", headers=headers)
        self.assertEqual(history_response.status_code, 200, history_response.text)
        history_items = history_response.json()["data"]
        self.assertEqual(len(history_items), 2)
        self.assertEqual(history_items[0]["role"], "user")
        self.assertEqual(history_items[1]["role"], "assistant")
        self.assertNotIn(METADATA_START_MARKER, history_items[1]["content"])

        delete_response = self.client.delete(f"/api/v1/history/{session_id}", headers=headers)
        self.assertEqual(delete_response.status_code, 200, delete_response.text)

        history_after_delete = self.client.get(f"/api/v1/history/{session_id}", headers=headers)
        self.assertEqual(history_after_delete.status_code, 200, history_after_delete.text)
        self.assertEqual(history_after_delete.json()["data"], [])

    def test_upload_list_duplicate_and_clear_flow(self):
        token_payload = self._register_and_login("doc_user")
        headers = {"Authorization": f"Bearer {token_payload['access_token']}"}
        upload_file = ("handbook.md", b"# Handbook\n\nHello world.", "text/markdown")

        upload_response = self.client.post(
            "/api/v1/upload",
            headers=headers,
            files={"file": upload_file},
        )
        self.assertEqual(upload_response.status_code, 200, upload_response.text)
        self.assertEqual(upload_response.json()["status"], "success")

        duplicate_response = self.client.post(
            "/api/v1/upload",
            headers=headers,
            files={"file": upload_file},
        )
        self.assertEqual(duplicate_response.status_code, 200, duplicate_response.text)
        self.assertEqual(duplicate_response.json()["status"], "skipped")

        list_response = self.client.get("/api/v1/list?page=1&page_size=10", headers=headers)
        self.assertEqual(list_response.status_code, 200, list_response.text)
        list_payload = list_response.json()
        self.assertEqual(list_payload["total"], 1)
        self.assertEqual(len(list_payload["data"]), 1)
        self.assertEqual(list_payload["data"][0]["source"], "handbook.md")

        clear_response = self.client.delete("/api/v1/clear", headers=headers)
        self.assertEqual(clear_response.status_code, 200, clear_response.text)

        list_after_clear = self.client.get("/api/v1/list?page=1&page_size=10", headers=headers)
        self.assertEqual(list_after_clear.status_code, 200, list_after_clear.text)
        self.assertEqual(list_after_clear.json()["total"], 0)

    def test_sessions_are_isolated_between_users(self):
        first_user = self._register_and_login("tenant_user_one")
        second_user = self._register_and_login("tenant_user_two")
        first_headers = {"Authorization": f"Bearer {first_user['access_token']}"}
        second_headers = {"Authorization": f"Bearer {second_user['access_token']}"}
        session_id = "isolated_session"

        chat_response = self.client.post(
            "/api/v1/chat",
            headers=first_headers,
            json={"question": "User one question", "session_id": session_id},
        )
        self.assertEqual(chat_response.status_code, 200, chat_response.text)

        other_history = self.client.get(f"/api/v1/history/{session_id}", headers=second_headers)
        self.assertEqual(other_history.status_code, 200, other_history.text)
        self.assertEqual(other_history.json()["data"], [])

        other_sessions = self.client.get("/api/v1/sessions", headers=second_headers)
        self.assertEqual(other_sessions.status_code, 200, other_sessions.text)
        self.assertEqual(other_sessions.json()["data"], [])

    def test_upload_failure_rolls_back_partial_document_record(self):
        token_payload = self._register_and_login("rollback_user")
        headers = {"Authorization": f"Bearer {token_payload['access_token']}"}

        with patch.object(admin_routes, "ingest_knowledge", return_value=True), patch.object(
            admin_routes,
            "create_document_record",
            side_effect=RuntimeError("db write failed"),
        ), patch.object(admin_routes, "remove_document", return_value=True) as remove_mock:
            upload_response = self.client.post(
                "/api/v1/upload",
                headers=headers,
                files={"file": ("rollback.md", b"# Rollback", "text/markdown")},
            )

        self.assertEqual(upload_response.status_code, 500, upload_response.text)
        self.assertEqual(
            self.testing_session_local().query(DocumentRecord).filter_by(filename="rollback.md").count(),
            0,
        )
        remove_mock.assert_called_once_with("rollback.md", token_payload["tenant_id"])

    def test_upload_index_failure_rolls_back_uploaded_file_and_vector_cleanup(self):
        token_payload = self._register_and_login("index_fail_user")
        headers = {"Authorization": f"Bearer {token_payload['access_token']}"}
        tenant_upload_dir = Path("data") / "uploads" / token_payload["tenant_id"]

        with patch.object(admin_routes, "ingest_knowledge", return_value=False), patch.object(
            admin_routes, "remove_document", return_value=True
        ) as remove_mock:
            upload_response = self.client.post(
                "/api/v1/upload",
                headers=headers,
                files={"file": ("failed-index.md", b"# Failed index", "text/markdown")},
            )

        self.assertEqual(upload_response.status_code, 500, upload_response.text)
        self.assertIn("Failed to index document", upload_response.text)
        self.assertFalse(tenant_upload_dir.exists() and any(tenant_upload_dir.iterdir()))
        remove_mock.assert_called_once_with("failed-index.md", token_payload["tenant_id"])

    def test_clear_failure_keeps_document_records_until_cleanup_succeeds(self):
        token_payload = self._register_and_login("clear_fail_user")
        headers = {"Authorization": f"Bearer {token_payload['access_token']}"}
        upload_dir = Path("data") / "uploads" / token_payload["tenant_id"]
        upload_dir.mkdir(parents=True, exist_ok=True)
        preserved_file = upload_dir / "keep.txt"
        preserved_file.write_text("keep me", encoding="utf-8")

        db = self.testing_session_local()
        try:
            db.add(
                DocumentRecord(
                    filename="keep.txt",
                    file_hash="hash_keep",
                    tenant_id=token_payload["tenant_id"],
                    user_id="clear_fail_user",
                )
            )
            db.commit()
        finally:
            db.close()

        with patch.object(admin_routes, "cleanup_tenant_resources", side_effect=RuntimeError("clear failed")):
            clear_response = self.client.delete("/api/v1/clear", headers=headers)

        self.assertEqual(clear_response.status_code, 500, clear_response.text)
        self.assertTrue(preserved_file.exists())
        db = self.testing_session_local()
        try:
            record_count = (
                db.query(DocumentRecord)
                .filter(DocumentRecord.tenant_id == token_payload["tenant_id"])
                .count()
            )
            self.assertEqual(record_count, 1)
        finally:
            db.close()

    def test_chat_stream_failure_returns_error_and_does_not_persist_partial_history(self):
        token_payload = self._register_and_login("stream_fail_user")
        headers = {"Authorization": f"Bearer {token_payload['access_token']}"}
        session_id = "stream_failure_session"

        with patch.object(chat_routes, "stream_rag_answer", _failing_stream_rag_answer):
            chat_response = self.client.post(
                "/api/v1/chat",
                headers=headers,
                json={"question": "Will this fail?", "session_id": session_id},
            )

        self.assertEqual(chat_response.status_code, 200, chat_response.text)
        self.assertIn("partial answer", chat_response.text)
        self.assertIn("Failed to generate a response", chat_response.text)

        history_response = self.client.get(f"/api/v1/history/{session_id}", headers=headers)
        self.assertEqual(history_response.status_code, 200, history_response.text)
        self.assertEqual(history_response.json()["data"], [])

    def test_cleanup_expired_temporary_visitors_removes_tenant_data(self):
        tenant_id = "tenant_visitor_expired_case"
        db = self.testing_session_local()
        try:
            db.add(
                User(
                    username="visitor_expired_case",
                    hashed_password="hashed",
                    tenant_id=tenant_id,
                    is_temporary=True,
                    expires_at=datetime.utcnow() - timedelta(minutes=5),
                )
            )
            db.add(
                DocumentRecord(
                    filename="expired.md",
                    file_hash="expired_hash",
                    tenant_id=tenant_id,
                    user_id="visitor_expired_case",
                )
            )
            db.add(
                ChatHistory(
                    session_id="expired_session",
                    user_query="question",
                    ai_response="answer",
                    tenant_id=tenant_id,
                    user_id="visitor_expired_case",
                )
            )
            db.commit()
        finally:
            db.close()

        upload_dir = Path("data") / "uploads" / tenant_id
        upload_dir.mkdir(parents=True, exist_ok=True)
        (upload_dir / "expired.txt").write_text("temporary", encoding="utf-8")

        with patch.object(database, "clear_all_data", return_value=True):
            cleaned_count = database.cleanup_expired_temporary_visitors()

        self.assertEqual(cleaned_count, 1)
        self.assertFalse(upload_dir.exists())

        db = self.testing_session_local()
        try:
            self.assertEqual(db.query(User).filter(User.tenant_id == tenant_id).count(), 0)
            self.assertEqual(db.query(DocumentRecord).filter(DocumentRecord.tenant_id == tenant_id).count(), 0)
            self.assertEqual(db.query(ChatHistory).filter(ChatHistory.tenant_id == tenant_id).count(), 0)
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
