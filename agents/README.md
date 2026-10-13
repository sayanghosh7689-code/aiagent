# 🤖 AI Agent API Platform — Complete MVP

A developer-focused SaaS platform where users configure AI chat agents, ground them in company knowledge (PDFs) via Retrieval-Augmented Generation (RAG), and expose them to frontend websites and backend applications via protected, rate-limited REST APIs.

---

## 🏗️ Architecture & Technology Stack

| Layer | Technology | Responsibility |
|---|---|---|
| **Frontend** | Streamlit | Developer dashboard, multi-turn chat playground, RAG manager, key manager, analytics, billing |
| **Backend** | FastAPI | REST API, auth, CORS middleware, agent execution, per-key rate limiting, quota enforcement |
| **AI / LLM** | Hugging Face Hub / Fallback | Chat completion (`Qwen/Qwen2.5-7B-Instruct`, Llama 3.1, Mistral) with intelligent local fallback |
| **Vector RAG** | ChromaDB + PyPDF | PDF text extraction, 800-char overlapping chunking, semantic vector indexing and retrieval |
| **Database** | PostgreSQL / SQLite (SQLAlchemy) | Users, projects, agents, documents metadata, API keys, conversation messages, usage logs |
| **Payments** | Razorpay | Subscription checkout, HMAC-verified webhooks (`subscription.activated`, `charged`, `cancelled`), and sandbox simulator |
| **Deployment** | Docker & Docker Compose | Containerized multi-service setup (FastAPI + Streamlit + PostgreSQL) |

---

## ✨ Implemented MVP Features

- **User & Project Management**:
  - Secure email/password authentication using PBKDF2-HMAC-SHA256 with per-user salt.
  - Organization into Projects (creates a default project automatically upon signup).
- **Agent Lifecycle**:
  - Create, read, update, and delete agents with custom persona instructions, model selection, and temperature control.
- **Knowledge Base & Document Management (PDF RAG)**:
  - Upload PDF files (policies, FAQs, technical manuals).
  - Text chunking (800 characters with 100 character overlap) and vector indexing in isolated ChromaDB collections.
  - Document management dashboard: view uploaded files, file sizes, chunk counts, and remove documents with vector cleanup.
- **Multi-Turn Conversation Memory**:
  - Supports `conversation_id` parameter to retain chat context across multiple requests.
  - Interactive multi-turn chat in the Streamlit playground with conversation reset controls.
- **Protected REST API Keys**:
  - Issue `sk_...` API keys.
  - Keys are stored securely as SHA-256 hashes (raw keys shown only once upon creation).
  - Key revocation and status inspection.
- **Abuse Prevention & Safeguards**:
  - **Per-Key Rate Limiting**: Sliding window rate limiter (default 60 requests/minute per key) with HTTP 429 and `Retry-After` headers.
  - **Monthly Account Quotas**: Automatically enforced per plan (Free: 100, Starter: 2,000, Pro: 10,000 requests/month).
  - **CORS Middleware**: Enabled for browser-side JavaScript integration.
- **Analytics & Request Logging**:
  - Live metric cards: Monthly requests used, remaining quota, success rate %, average latency in ms.
  - Request audit log: Request ID, Agent, HTTP status, latency, error details, and timestamp.
- **Billing & Subscriptions**:
  - Razorpay checkout integration with HMAC SHA-256 webhook signature verification.
  - Sandbox test mode for local evaluation without live credentials.
- **Automated Test Suite**:
  - Full test coverage with `pytest` covering auth, projects, agents, RAG document indexing, keys, chat, rate limiting, and webhooks.

---

## 🚀 Quickstart Guide

### 1. Local Development

```bash
# 1. Clone repository and install dependencies (use requirements-dev.txt to also get pytest/httpx)
pip install -r requirements-dev.txt

# 2. Set environment variables (optional for local testing)
export HF_TOKEN=hf_...                      # Optional: Hugging Face API token (without it, answers are local mocks)
export HF_MODEL=Qwen/Qwen2.5-7B-Instruct    # Optional: Default LLM model
export ALLOW_SANDBOX_BILLING=true           # Local only: lets the dashboard switch plans without paying
# export DATABASE_URL=postgresql://user:pass@localhost:5432/agents

# 3. Start the FastAPI backend (Terminal 1)
uvicorn main:app --reload --port 8000
# Interactive Swagger API documentation will be available at: http://localhost:8000/docs

# 4. Start the Streamlit dashboard (Terminal 2)
streamlit run app.py --server.port 8501
# Dashboard will be available at: http://localhost:8501
```

### 2. Docker Deployment

Deploy the entire stack (FastAPI Backend + Streamlit Dashboard + PostgreSQL) in one command:

```bash
cp .env.example .env        # then set POSTGRES_PASSWORD (required) and any other values
docker compose up --build -d
```

The PostgreSQL port is not published to the host. Vector data lives in the `chroma_data` volume.
Note: ChromaDB downloads its default embedding model the first time you index or query a document, so the first run needs internet access.

- **Backend API**: `http://localhost:8000`
- **Interactive Swagger Docs**: `http://localhost:8000/docs`
- **Streamlit Dashboard**: `http://localhost:8501`

---

## 🧪 Running Automated Tests

Run the automated test suite with pytest:

```bash
pytest -q
```

Tests use a temporary database and a temporary Chroma directory (your real data is never touched), and every test creates its own user, so they can run in any order. They cover:
- Health check, signup/login validation, and login brute-force throttling
- Tenant isolation (one user cannot read, change, or call another user's agents, keys, or projects)
- Agent lifecycle, per-plan agent limits, PDF upload validation (type, size, magic bytes, filename), RAG indexing and citations
- API keys, protected chat, multi-turn history window, revocation
- Per-key rate limiting (429) and monthly quota enforcement
- LLM failures return 502 and are not billed
- Razorpay webhook signature verification (bad, missing, and unconfigured secret) and sandbox billing switch

---

## 📡 API Reference

### 1. Chat with Agent
```http
POST /api/v1/agents/{agent_id}/chat
```

#### Headers:
```http
Authorization: Bearer sk_your_api_key_here
Content-Type: application/json
```

#### Request Body:
```json
{
  "message": "What is the return policy?",
  "conversation_id": "session-101"
}
```

#### Response:
```json
{
  "response": "According to the company policy, items can be returned within 30 days of purchase with the original receipt [returns.pdf p.2].",
  "sources": [
    "returns.pdf p.2"
  ],
  "conversation_id": "session-101",
  "request_id": "req_84ef812bc901"
}
```

---

### Code Examples

#### cURL
```bash
curl -X POST "http://localhost:8000/api/v1/agents/agt_123/chat" \
  -H "Authorization: Bearer sk_your_api_key" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What is the refund period?",
    "conversation_id": "conv_user_42"
  }'
```

#### Python (`requests`)
```python
import requests

url = "http://localhost:8000/api/v1/agents/agt_123/chat"
headers = {
    "Authorization": "Bearer sk_your_api_key",
    "Content-Type": "application/json"
}
payload = {
    "message": "What is the refund period?",
    "conversation_id": "conv_user_42"
}

response = requests.post(url, json=payload, headers=headers)
print(response.json())
```

#### JavaScript (`fetch`)
```javascript
const response = await fetch("http://localhost:8000/api/v1/agents/agt_123/chat", {
  method: "POST",
  headers: {
    "Authorization": "Bearer sk_your_api_key",
    "Content-Type": "application/json"
  },
  body: JSON.stringify({
    message: "What is the refund period?",
    conversation_id: "conv_user_42"
  })
});
const data = await response.json();
console.log(data.response);
```

---

## 💳 Razorpay & Monetization Setup

1. **Dashboard Setup**:
   - Create subscription plans in Razorpay: Starter (₹299/mo) and Pro (₹999/mo).
   - Set up Webhook URL: `https://YOUR_DOMAIN/webhooks/razorpay` with secret.
   - Subscribed events: `subscription.activated`, `subscription.charged`, `subscription.cancelled`, `subscription.halted`, `subscription.completed`.
2. **Environment Variables**:
   ```bash
   RAZORPAY_KEY_ID=rzp_live_...
   RAZORPAY_KEY_SECRET=...
   RAZORPAY_WEBHOOK_SECRET=...
   RAZORPAY_PLAN_STARTER=plan_...
   RAZORPAY_PLAN_PRO=plan_...
   ```
3. **Sandbox Testing** (local only):
   - Set `ALLOW_SANDBOX_BILLING=true` to test plan upgrades in the dashboard or via `POST /billing/test-upgrade`.
   - It is **off by default** because it grants paid plans without payment. Never enable it in production.
   - The webhook endpoint always requires `RAZORPAY_WEBHOOK_SECRET` and a valid signature.

---

## ⚙️ Configuration Reference

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./platform.db` | SQLAlchemy database URL |
| `CHROMA_PATH` | `./chroma_data` | Vector store location |
| `HF_TOKEN` / `HF_MODEL` | – / Qwen2.5-7B-Instruct | LLM provider. With a token set, provider errors return 502 (no silent mock) |
| `ALLOW_MOCK_LLM` | `true` | Local mock answers when no `HF_TOKEN`; set `false` in production |
| `ALLOW_SANDBOX_BILLING` | `false` | Free plan switching for local testing only |
| `CORS_ORIGINS` | `*` | Comma-separated allowed browser origins |
| `RATE_LIMIT_PER_MINUTE` | `60` | Per API key |
| `AUTH_RATE_LIMIT_PER_MINUTE` | `10` | Login attempts per email (and signups per IP) |
| `PUBLIC_API_URL` | same as `API_URL` | URL shown in dashboard code snippets |

## ⚠️ Known Limitations

- The rate limiter is in-process memory: run a single worker, or move it to Redis before scaling out.
- Dashboard session tokens do not expire (one active session per user). Add a sessions table with expiry before launch.
- Passwords use PBKDF2-SHA256 with 200,000 iterations; raising it requires storing the iteration count per user.
- `conversation_id` values are chosen by the API caller; if you serve several end users with one key, generate unguessable IDs per end user.
