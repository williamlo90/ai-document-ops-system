from __future__ import annotations

from fastapi.testclient import TestClient


def login(client: TestClient, token: str) -> None:
    response = client.post("/auth/session", json={"access_token": token})
    if response.status_code != 200:
        raise AssertionError(response.text)
