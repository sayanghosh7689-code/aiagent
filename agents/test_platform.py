"""Test suite for the AI Agent API Platform.

Each test creates its own user, so tests are independent and can run in any order.
Run with:  pytest -q
"""
import os, io, hmac, hashlib, json, tempfile, uuid
import pytest

# --- Isolated environment: must be set BEFORE importing main -----------------
_TMP = tempfile.mkdtemp(prefix="agent_platform_test_")
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP}/test_platform.db"
os.environ["CHROMA_PATH"] = f"{_TMP}/chroma"          # never touch real ./chroma_data
os.environ["RAZORPAY_WEBHOOK_SECRET"] = "test_webhook_secret_123"
os.environ["RATE_LIMIT_PER_MINUTE"] = "10"
os.environ["AUTH_RATE_LIMIT_PER_MINUTE"] = "1000"    # auth throttling has its own test
os.environ["ALLOW_SANDBOX_BILLING"] = "true"
os.environ["ALLOW_MOCK_LLM"] = "true"
os.environ.pop("HF_TOKEN", None)
os.environ.pop("RAZORPAY_KEY_ID", None)

from fastapi.testclient import TestClient
import main
from main import app, Base, engine

client = TestClient(app)
PASSWORD = "strongpassword123"


@pytest.fixture(scope="session", autouse=True)
def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture(autouse=True)
def reset_rate_limits():
    main._rate_limit_records.clear()
    yield


def _pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def create_sample_pdf(content: str = "Our store return policy permits returns within 30 days of purchase.") -> bytes:
    """Build a valid single-page PDF with correct xref offsets (no extra dependencies)."""
    stream = f"BT\n/F1 12 Tf\n100 700 Td\n({_pdf_escape(content)}) Tj\nET\n".encode("latin-1")
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"endstream",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_pos = len(out)
    out += f"xref\n0 {len(objs) + 1}\n".encode() + b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode()
    return bytes(out)


def new_user():
    email = f"user_{uuid.uuid4().hex[:10]}@example.com"
    r = client.post("/auth/signup", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return email, {"Authorization": f"Bearer {r.json()['token']}"}


def new_agent(headers, name="Test Agent", **extra):
    r = client.post("/agents", json={"name": name, "instructions": "Help customers.", **extra}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def new_key(headers, agent_id):
    r = client.post(f"/agents/{agent_id}/keys", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["api_key"], r.json()["id"]


def set_plan(headers, plan):
    assert client.post("/billing/test-upgrade", json={"plan": plan}, headers=headers).status_code == 200


# ----------------------------- generic -----------------------------
def test_health_check():
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "healthy"
    assert "database" not in r.json()


def test_sample_pdf_is_valid_and_readable():
    from pypdf import PdfReader
    text = PdfReader(io.BytesIO(create_sample_pdf("Refunds (within 30 days) apply."))).pages[0].extract_text()
    assert "Refunds (within 30 days) apply." in text


# ----------------------------- auth -----------------------------
def test_signup_login_and_errors():
    email, _ = new_user()
    assert client.post("/auth/signup", json={"email": email, "password": PASSWORD}).status_code == 409
    assert client.post("/auth/signup", json={"email": "not-an-email", "password": PASSWORD}).status_code == 422
    assert client.post("/auth/signup", json={"email": "a@b.co", "password": "short"}).status_code == 422
    ok = client.post("/auth/login", json={"email": email.upper(), "password": PASSWORD})
    assert ok.status_code == 200 and "token" in ok.json()
    assert client.post("/auth/login", json={"email": email, "password": "wrongpassword"}).status_code == 401
    assert client.post("/auth/login", json={"email": "nobody@example.com", "password": PASSWORD}).status_code == 401


def test_protected_routes_require_valid_token():
    assert client.get("/agents").status_code == 401
    assert client.get("/agents", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_login_brute_force_is_throttled(monkeypatch):
    monkeypatch.setattr(main, "AUTH_RATE_LIMIT_PER_MINUTE", 3)
    email, _ = new_user()
    codes = [client.post("/auth/login", json={"email": email, "password": "wrongpassword"}).status_code for _ in range(5)]
    assert codes[:3] == [401, 401, 401]
    assert codes[3] == 429


# ----------------------------- projects -----------------------------
def test_project_crud_and_delete_guard():
    _, h = new_user()
    assert len(client.get("/projects", headers=h).json()) >= 1  # default project from signup
    p = client.post("/projects", json={"name": "Support", "description": "x"}, headers=h).json()
    upd = client.put(f"/projects/{p['id']}", json={"name": "Support HQ"}, headers=h)
    assert upd.status_code == 200 and upd.json()["name"] == "Support HQ"
    agent_id = new_agent(h, project_id=p["id"])
    assert client.delete(f"/projects/{p['id']}", headers=h).status_code == 409  # has agents
    client.delete(f"/agents/{agent_id}", headers=h)
    assert client.delete(f"/projects/{p['id']}", headers=h).status_code == 200


# ----------------------------- tenant isolation -----------------------------
def test_users_cannot_touch_each_others_resources():
    _, a = new_user()
    _, b = new_user()
    agent_a = new_agent(a)
    key_a, key_a_id = new_key(a, agent_a)
    proj_a = client.get("/projects", headers=a).json()[0]["id"]

    assert client.get(f"/agents/{agent_a}", headers=b).status_code == 404
    assert client.put(f"/agents/{agent_a}", json={"name": "hacked"}, headers=b).status_code == 404
    assert client.delete(f"/agents/{agent_a}", headers=b).status_code == 404
    assert client.get(f"/agents/{agent_a}/documents", headers=b).status_code == 404
    assert client.post(f"/agents/{agent_a}/playground", json={"message": "hi"}, headers=b).status_code == 404
    assert client.delete(f"/keys/{key_a_id}", headers=b).status_code == 404
    # cannot attach own agent to someone else's project
    assert client.post("/agents", json={"name": "x", "project_id": proj_a}, headers=b).status_code == 404

    # A's key must not work on B's agent
    agent_b = new_agent(b)
    r = client.post(f"/api/v1/agents/{agent_b}/chat", json={"message": "hi"}, headers={"Authorization": f"Bearer {key_a}"})
    assert r.status_code == 401


# ----------------------------- agents, plans & RAG -----------------------------
def test_agent_lifecycle_rag_chat_and_keys():
    _, h = new_user()
    agent_id = new_agent(h, "Refund Policy Agent", temperature=2)
    assert any(a["id"] == agent_id for a in client.get("/agents", headers=h).json())

    up = client.post(f"/agents/{agent_id}/documents", headers=h,
                     files={"file": ("policy.pdf", create_sample_pdf("Refund policy allows returns up to 30 days with receipt."), "application/pdf")})
    assert up.status_code == 200, up.text
    doc_id = up.json()["document_id"]
    assert up.json()["chunks_indexed"] >= 1
    assert any(d["id"] == doc_id for d in client.get(f"/agents/{agent_id}/documents", headers=h).json())

    api_key, key_id = new_key(h, agent_id)
    ch = {"Authorization": f"Bearer {api_key}"}
    r1 = client.post(f"/api/v1/agents/{agent_id}/chat", json={"message": "What is the return window?", "conversation_id": "conv_1"}, headers=ch)
    assert r1.status_code == 200, r1.text
    data = r1.json()
    assert {"response", "request_id", "sources", "latency_ms"} <= data.keys()
    assert data["conversation_id"] == "conv_1"
    assert any("policy.pdf" in src for src in data["sources"])      # citation present

    assert client.post(f"/api/v1/agents/{agent_id}/chat", json={"message": "No receipt?", "conversation_id": "conv_1"}, headers=ch).status_code == 200
    hist = client.get(f"/agents/{agent_id}/conversations/conv_1", headers=h).json()
    assert [m["role"] for m in hist] == ["user", "assistant", "user", "assistant"]
    assert client.get("/usage", headers=h).json()["used_this_month"] >= 2

    assert client.delete(f"/keys/{key_id}", headers=h).status_code == 200
    assert client.post(f"/api/v1/agents/{agent_id}/chat", json={"message": "hello"}, headers=ch).status_code == 401
    assert client.delete(f"/agents/{agent_id}/documents/{doc_id}", headers=h).status_code == 200
    assert client.delete(f"/agents/{agent_id}", headers=h).status_code == 200


def test_chat_history_window_uses_most_recent_messages(monkeypatch):
    _, h = new_user()
    agent_id = new_agent(h)
    seen = {}
    real = main.run_agent_workflow

    def spy(a, message, history=None):
        seen["history"] = history
        return real(a, message, history=history)

    monkeypatch.setattr(main, "run_agent_workflow", spy)
    for i in range(8):  # 16 stored messages
        assert client.post(f"/agents/{agent_id}/playground", json={"message": f"msg {i}", "conversation_id": "c1"}, headers=h).status_code == 200
        main._rate_limit_records.clear()
    client.post(f"/agents/{agent_id}/playground", json={"message": "latest", "conversation_id": "c1"}, headers=h)
    contents = [m["content"] for m in seen["history"]]
    assert len(contents) == 10
    assert "msg 7" in contents and "msg 0" not in contents      # newest kept, oldest dropped


def test_invalid_conversation_id_rejected():
    _, h = new_user()
    agent_id = new_agent(h)
    r = client.post(f"/agents/{agent_id}/playground", json={"message": "hi", "conversation_id": "../etc passwd"}, headers=h)
    assert r.status_code == 422


def test_free_plan_agent_limit_enforced():
    _, h = new_user()
    new_agent(h, "first")
    assert client.post("/agents", json={"name": "second"}, headers=h).status_code == 403
    set_plan(h, "starter")
    for i in range(4):
        new_agent(h, f"extra {i}")                              # 5 total on Starter
    assert client.post("/agents", json={"name": "sixth"}, headers=h).status_code == 403


def test_upload_validation():
    _, h = new_user()
    agent_id = new_agent(h)
    url = f"/agents/{agent_id}/documents"
    assert client.post(url, headers=h, files={"file": ("notes.txt", b"hello", "text/plain")}).status_code == 400
    assert client.post(url, headers=h, files={"file": ("fake.pdf", b"not a pdf at all", "application/pdf")}).status_code == 400
    assert client.post(url, headers=h, files={"file": ("broken.pdf", b"%PDF-1.4 garbage", "application/pdf")}).status_code == 400
    big = b"%PDF-" + b"0" * (main.MAX_UPLOAD_MB * 1024 * 1024 + 10)
    assert client.post(url, headers=h, files={"file": ("big.pdf", big, "application/pdf")}).status_code == 413
    # path tricks in filename are neutralised
    ok = client.post(url, headers=h, files={"file": ("../../evil name.pdf", create_sample_pdf(), "application/pdf")})
    assert ok.status_code == 200 and "/" not in ok.json()["filename"] and ".." not in ok.json()["filename"]


# ----------------------------- rate limit & quota -----------------------------
def test_per_key_rate_limit():
    _, h = new_user()
    agent_id = new_agent(h)
    key, _ = new_key(h, agent_id)
    ch = {"Authorization": f"Bearer {key}"}
    for i in range(10):
        assert client.post(f"/api/v1/agents/{agent_id}/chat", json={"message": f"ping {i}"}, headers=ch).status_code == 200
    r = client.post(f"/api/v1/agents/{agent_id}/chat", json={"message": "one too many"}, headers=ch)
    assert r.status_code == 429 and "Rate limit exceeded" in r.json()["detail"] and "Retry-After" in r.headers


def test_monthly_quota_blocks_requests(monkeypatch):
    monkeypatch.setitem(main.QUOTAS, "free", 2)
    _, h = new_user()
    agent_id = new_agent(h)
    key, _ = new_key(h, agent_id)
    ch = {"Authorization": f"Bearer {key}"}
    for _ in range(2):
        assert client.post(f"/api/v1/agents/{agent_id}/chat", json={"message": "hi"}, headers=ch).status_code == 200
    r = client.post(f"/api/v1/agents/{agent_id}/chat", json={"message": "hi"}, headers=ch)
    assert r.status_code == 429 and "quota" in r.json()["detail"].lower()


def test_llm_failure_returns_502_and_is_not_billed(monkeypatch):
    _, h = new_user()
    agent_id = new_agent(h)

    def boom(*a, **k):
        raise RuntimeError("provider down: secret-internal-detail")

    monkeypatch.setattr(main, "execute_llm", boom)
    r = client.post(f"/agents/{agent_id}/playground", json={"message": "hi"}, headers=h)
    assert r.status_code == 502 and "secret-internal-detail" not in r.text
    assert client.get("/usage", headers=h).json()["used_this_month"] == 0


# ----------------------------- billing & webhooks -----------------------------
def _signed(payload: dict, secret="test_webhook_secret_123"):
    raw = json.dumps(payload).encode()
    return raw, hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()


def test_sandbox_subscribe_and_signed_webhook_upgrade():
    _, h = new_user()
    sub = client.post("/billing/subscribe", json={"plan": "starter"}, headers=h)
    assert sub.status_code == 200 and sub.json()["subscription_id"]
    b = client.get("/billing", headers=h).json()
    assert b["plan"] == "starter" and b["quota"] == 2000

    raw, sig = _signed({"event": "subscription.charged", "payload": {"subscription": {"entity": {"id": sub.json()["subscription_id"], "notes": {"plan": "pro"}}}}})
    wh = client.post("/webhooks/razorpay", content=raw, headers={"Content-Type": "application/json", "X-Razorpay-Signature": sig})
    assert wh.status_code == 200
    assert client.get("/billing", headers=h).json()["plan"] == "pro"

    raw, sig = _signed({"event": "subscription.cancelled", "payload": {"subscription": {"entity": {"id": sub.json()["subscription_id"]}}}})
    client.post("/webhooks/razorpay", content=raw, headers={"Content-Type": "application/json", "X-Razorpay-Signature": sig})
    assert client.get("/billing", headers=h).json()["plan"] == "free"


def test_webhook_rejects_bad_or_missing_signature():
    raw, _ = _signed({"event": "subscription.charged", "payload": {}})
    for sig in ("", "deadbeef"):
        r = client.post("/webhooks/razorpay", content=raw, headers={"Content-Type": "application/json", "X-Razorpay-Signature": sig})
        assert r.status_code == 400


def test_webhook_refuses_unsigned_events_when_secret_unset(monkeypatch):
    monkeypatch.setattr(main, "RZP_WEBHOOK_SECRET", "")
    r = client.post("/webhooks/razorpay", content=b"{}", headers={"Content-Type": "application/json"})
    assert r.status_code == 503


def test_sandbox_billing_disabled_blocks_free_upgrades(monkeypatch):
    monkeypatch.setattr(main, "ALLOW_SANDBOX_BILLING", False)
    _, h = new_user()
    assert client.post("/billing/subscribe", json={"plan": "pro"}, headers=h).status_code == 503
    assert client.post("/billing/test-upgrade", json={"plan": "pro"}, headers=h).status_code == 404
    assert client.get("/billing", headers=h).json()["plan"] == "free"
