import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app


@pytest.fixture(autouse=True)
def _never_call_real_gemini(monkeypatch):
    """.env may hold a real GEMINI_API_KEY; tests must never spend it. Two layers:

    1. the key is blanked (tests that need one set their own and must mock `google.genai.Client`);
    2. tripwire: a socket connection to any non-loopback address fails the test. The suite is in-process (SQLite in
       memory, ASGI TestClient); loopback is allowed because asyncio/anyio use it internally on Windows, so a
       non-loopback connect() means a test is about to hit the real network, Gemini included.
    """
    import socket

    from app.config import settings

    monkeypatch.setattr(settings, "gemini_api_key", None)

    real_connect, real_connect_ex = socket.socket.connect, socket.socket.connect_ex

    def _is_loopback(address) -> bool:
        host = address[0] if isinstance(address, tuple) else None  # None = AF_UNIX path, local by definition
        return host is None or host in ("127.0.0.1", "::1", "localhost")

    def _guard(real):
        def wrapper(self, address, *args, **kwargs):
            if not _is_loopback(address):
                raise RuntimeError(f"network access attempted in a test: connect({address!r})")
            return real(self, address, *args, **kwargs)

        return wrapper

    monkeypatch.setattr(socket.socket, "connect", _guard(real_connect))
    monkeypatch.setattr(socket.socket, "connect_ex", _guard(real_connect_ex))


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture()
def repo_id(client):
    resp = client.post("/repos", json={"name": "sample-repo", "url": "https://example.com/sample-repo"})
    assert resp.status_code == 201
    return resp.json()["id"]
