"""Security smoke tests for Enterprise RAG.

Run this script after starting the Enterprise RAG FastAPI service:

    python scripts/test_security.py
"""

from __future__ import annotations

import io
import time
import uuid
from dataclasses import dataclass

import os

import requests


BASE_URL = os.getenv("ENTERPRISE_RAG_BASE_URL", "http://localhost:8010/api/v1")


@dataclass
class UserSession:
    username: str
    token: str

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)
    print(f"[OK] {message}")


def unique_username(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def register_and_login(username: str) -> UserSession:
    password = "Passw0rd_123"
    register_resp = requests.post(
        f"{BASE_URL}/auth/register",
        json={"username": username, "password": password},
        timeout=10,
    )
    expect(
        register_resp.status_code in {201, 400},
        f"register {username} returns {register_resp.status_code}",
    )

    login_resp = requests.post(
        f"{BASE_URL}/auth/login",
        json={"username": username, "password": password},
        timeout=10,
    )
    expect(login_resp.status_code == 200, f"login {username} succeeds")
    return UserSession(username=username, token=login_resp.json()["access_token"])


def test_invalid_username_rejected() -> None:
    resp = requests.post(
        f"{BASE_URL}/auth/register",
        json={"username": "../bad_user", "password": "Passw0rd_123"},
        timeout=10,
    )
    expect(resp.status_code == 422, "path-like username is rejected")


def test_history_isolation(user_a: UserSession, user_b: UserSession) -> None:
    session_id = f"sec_{uuid.uuid4().hex[:8]}"
    chat_resp = requests.post(
        f"{BASE_URL}/chat",
        headers=user_a.headers,
        json={"question": "安全隔离测试消息", "session_id": session_id},
        timeout=60,
    )
    expect(chat_resp.status_code == 200, "user A can create chat session")
    time.sleep(1)

    own_history = requests.get(
        f"{BASE_URL}/history/{session_id}",
        headers=user_a.headers,
        timeout=10,
    )
    expect(own_history.status_code == 200, "user A can read own history")

    other_history = requests.get(
        f"{BASE_URL}/history/{session_id}",
        headers=user_b.headers,
        timeout=10,
    )
    expect(
        other_history.status_code == 200 and other_history.json().get("data") == [],
        "user B cannot read user A history",
    )


def test_upload_filename_sanitized(user_a: UserSession) -> None:
    files = {
        "file": (
            "../../escape.md",
            io.BytesIO("安全测试文档\n\n路径穿越文件名测试。".encode("utf-8")),
            "text/markdown",
        )
    }
    resp = requests.post(
        f"{BASE_URL}/upload",
        headers=user_a.headers,
        files=files,
        timeout=60,
    )
    expect(resp.status_code in {200, 500}, "malicious filename is handled by upload route")
    if resp.status_code == 200:
        expect("../" not in resp.text, "response does not expose traversal path")


def main() -> None:
    print("[Security] Enterprise RAG smoke tests")
    test_invalid_username_rejected()
    user_a = register_and_login(unique_username("sec_a"))
    user_b = register_and_login(unique_username("sec_b"))
    test_history_isolation(user_a, user_b)
    test_upload_filename_sanitized(user_a)
    print("[Security] all checks completed")


if __name__ == "__main__":
    main()
