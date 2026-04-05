# 💬 Crevoxega AI Chat Widget Platform

An embeddable, multi-tenant AI chat widget backend that businesses can drop onto any website. Powered by **Google Gemini** via LangChain RAG, it answers visitor questions using each business's own knowledge document, captures leads intelligently, handles complaints empathetically, and collects feedback — all with end-to-end encryption and enterprise-grade rate limiting.

> Built by **Crevoxega** — Want a similar AI chatbot for your business? Contact [Crevoxega.contact@gmail.com](mailto:Crevoxega.contact@gmail.com)

---

## 📋 Table of Contents

- [Overview](#overview)
- [The Problem It Solves](#The-Problem-It-Solves)
- [Features](#features)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Tech Stack](#tech-stack)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [API Reference](#api-reference)
- [Chat Widget Integration](#chat-widget-integration)
- [Conversation Flow](#conversation-flow)
- [Lead Capture Logic](#lead-capture-logic)
- [Security](#security)
- [Rate Limiting](#rate-limiting)
- [Deployment](#deployment)

---

## Overview

This platform provides a **white-label AI chatbot widget** that any business can embed on their website. Businesses register, upload a knowledge document (FAQs, product info, service details), and receive a unique `client_token`. That token is embedded in the website widget (`widget.js`), which connects each visitor's conversation to the correct business's RAG-powered AI assistant.

The system is **fully stateful** — each visitor's conversation history, language preference, lead status, complaints, and feedback are tracked per session in Firebase Firestore.

---

## The Problem It Solves
Most websites suffer from a **"Leaky Funnel"**—potential customers visit the site, look around, and leave because they lack immediate direction or a quick way to get answers. 

* **Uncaptured Leads:** Anonymous visitors browse without leaving contact info, resulting in lost sales opportunities.
* **Lack of Direction:** Without a guided path, users feel overwhelmed by information and drop off before taking action.
* **The "Human Gap":** Small businesses can't monitor their website 24/7. When a lead is ready to engage at 2 AM, there is no one there to guide them, leading to a missed conversion.

### The Solution
This system acts as an intelligent, 24/7 concierge that transforms passive visitors into qualified leads through automated, high-intent conversations.

* **Instant Engagement:** Replaces static contact forms with a proactive AI agent that greets visitors the moment they show interest.
* **Intent Recognition:** The backend uses specialized keyword mapping (`BUY`, `CONTACT`, `DECISION`) to identify high-value visitors and prioritize their needs.
* **Automated Lead Qualification:** Instead of just "chatting," the system is engineered to detect and capture vital contact information (Email/Phone) while filtering out refusals.
* **RAG-Driven Expertise:** Uses Retrieval-Augmented Generation to answer complex, business-specific questions accurately, ensuring the visitor feels "heard" and directed toward the right product or service.
* **Seamless Handover:** Bridges the gap between a "curious visitor" and a "warm lead" by storing interaction history in Firebase, allowing business owners to follow up with full context.

--

## Features

### 🧠 AI & RAG
- **Retrieval-Augmented Generation** using LangChain + FAISS + BM25 ensemble retrieval
- Powered by **Google Gemini 2.5 Flash** for generation
- Per-client knowledge base from uploaded documents (PDF, text)
- Thread-safe RAG bot cache with 30-minute TTL and LRU eviction

### 🎯 Intelligent Chat Flow
- **Intent detection** — automatically identifies buying intent, contact requests, complaints, and decision-making signals
- **Value-first responses** — always answers the question before asking for contact info (reciprocity principle)
- **Engagement hooks** — contextual follow-up prompts injected every 3rd interaction to drive conversion
- **Feedback trigger** — soft feedback request every 5th interaction if feedback hasn't been given

### 📞 Lead Capture
- Captures visitor name, phone, and/or email when high-intent keywords are detected
- Stores leads encrypted in Firestore under the client's collection
- Respects privacy — detects refusal phrases ("no thanks", "not now", "prefer not") and gracefully backs off
- One-ask rule: never requests contact info twice in the same session

### 🗣️ Multi-Language Support
- Supports **English, Hindi, Gujarati, and Hinglish**
- Visitors can switch language anytime with `change_language`
- Language preference is persisted per visitor session

### 😤 Complaint & Feedback Handling
- Dedicated complaint flow with empathy-first responses
- Complaints encrypted and stored per visitor
- Structured feedback extraction — parses ratings (1-5, stars, emoji ⭐), reason extraction with 15+ keyword triggers
- Feedback stored encrypted in Firestore

### 🔒 Security & Encryption
- **Fernet symmetric encryption** for all PII at rest (names, emails, phones, complaints, feedback)
- **bcrypt** password hashing
- **JWT** authentication for the business dashboard (8-hour sessions)
- Deterministic hashing for Firestore document keys (no raw identifiers stored as keys)
- GCP Secret Manager integration with `.env` fallback

### ⚡ Rate Limiting
- Token bucket + multi-window sliding counter (per-minute, per-hour, per-day)
- Burst detection, duplicate message prevention, auto-blocking of suspicious activity
- Rate limits applied per `visitor_id × client_id`

---

## Architecture

```
Website Visitor
      │
      │  POST /chat  {client_token, visitor_id, message}
      ▼
FastAPI (frontend_fastapi.py)
      │
      ├── Rate Limiter ─────────────────── rate_limiter.py
      │
      ├── Token → client_id lookup ─────── backend_firebase.py
      │   (get_client_id_by_token)
      │
      ├── Plan check (must be "paid")
      │
      ├── RAG Cache ────────────────────── RAGCacheManager
      │   HIT  → return cached RAGBot       (30 min TTL, LRU eviction)
      │   MISS → fetch doc → build RAGBot ─ Rag.py
      │                        │
      │                        ├── FAISS + BM25 ensemble retrieval
      │                        └── Gemini 2.5 Flash generation
      │
      └── chat() ──────────────────────── backend_chat.py
              │
              ├── Firestore visitor session read
              ├── State machine (status field):
              │     active → awaiting_contact → active
              │     active → awaiting_language → active
              │     active → handling_complaint → awaiting_contact → active
              │     active → collecting_feedback → active
              ├── Intent detection (buy / contact / decision / complaint)
              ├── Lead capture & encryption
              └── RAG invoke + optional engagement hook
```

---

## Project Structure

```
.
├── frontend_fastapi.py     # FastAPI app — all HTTP routes, RAG cache, widget serving
├── backend_chat.py         # Core chat logic — state machine, intent detection, lead capture
├── backend_firebase.py     # Firebase wrapper — CRUD for chat_clients, customers, JWT
├── encryption_utils.py     # Fernet encryption, bcrypt, singleton logger, validators, db init
├── Rag.py                  # RAGBot — FAISS+BM25, Gemini generation, translation pipeline
├── rate_limiter.py         # Multi-layer rate limiter (token bucket + sliding windows)
├── get_secreats.py         # Secret loading (env vars / GCP Secret Manager)
├── we_are.py               # Widget usage guide injected into every RAG context
├── expr.py                 # Dev utility — decrypt a Fernet-encrypted value
├── Procfile                # Heroku/Render deployment config (gunicorn + uvicorn workers)
├── requirements.txt        # Python dependencies
├── runtime.txt             # Python 3.10.11
└── static/
    ├── index.html          # Business dashboard frontend
    └── widget.js           # Embeddable chat widget script (served at /widget.js)
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Web Framework | FastAPI + Uvicorn |
| Production Server | Gunicorn (2 UvicornWorker processes) |
| AI Model | Google Gemini 2.5 Flash (`langchain-google-genai`) |
| Embeddings | Google Generative AI Embeddings |
| Vector Store | FAISS (`faiss-cpu`) |
| Keyword Retrieval | BM25 (`rank-bm25`) |
| Database | Firebase Firestore (`firebase-admin`) |
| Secrets | GCP Secret Manager + `.env` fallback |
| Encryption | Fernet (`cryptography`) |
| Password Hashing | bcrypt |
| Auth | JWT (`PyJWT`) |
| HTTP | httpx, requests |
| PDF Parsing | PyMuPDF (`fitz`) |
| Session Cache | `cachetools.TTLCache` (in-memory, per visitor interaction count) |
| CORS | FastAPI `CORSMiddleware` |
| Python Version | 3.10.11 |

---

## Prerequisites

- Python 3.10.11 (see `runtime.txt`)
- A **Firebase** project with Firestore enabled and a service account key
- A **Google AI Studio** API key (Gemini + Embeddings)
- A **Fernet key** — generate with:
  ```python
  from cryptography.fernet import Fernet
  print(Fernet.generate_key().decode())
  ```
- A **GCP project** with Secret Manager enabled (optional — can use `.env` only)
- A `JWT_SECRET_KEY` for signing tokens

---

## Installation

```bash
# 1. Clone the repository
git clone https://github.com/your-username/your-repo.git
cd your-repo

# 2. Create and activate a virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment variables
cp .env.example .env
# Edit .env with your values (see Configuration)

# 5. Run the development server
uvicorn frontend_fastapi:app --reload --port 8000
```

---

## Configuration

Create a `.env` file in the project root:

```env
# Encryption
FERNET_KEY=your_44_character_fernet_key

# Google Gemini
GEMINI_API_KEY=your_gemini_api_key

# Firebase
FIREBASE_CREDENTIALS_PATH=/path/to/serviceAccountKey.json

# JWT
JWT_SECRET_KEY=your_jwt_secret

# GCP (if using Secret Manager)
GOOGLE_CLOUD_PROJECT=your_gcp_project_id
```

All secrets are loaded via `get_secreats.py`, which checks environment variables first, then falls back to GCP Secret Manager (secret ID: `Crevoxega`). Sensitive values written to Firestore are always Fernet-encrypted.

---

## API Reference

### Public

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Serve the business dashboard (`static/index.html`) |
| `GET` | `/widget.js` | Serve the embeddable JavaScript chat widget |
| `POST` | `/health` | Health check — returns `{"status": "OK"}` |
| `POST` | `/api/register` | Register a new business (form data + optional doc upload) |
| `POST` | `/api/login` | Authenticate business, returns JWT + client data |

### Chat (Widget)

| Method | Path | Body | Description |
|---|---|---|---|
| `POST` | `/chat` | `{client_token, visitor_id, message}` | Process a visitor message; returns `{"reply": "..."}` |

The `/chat` endpoint is the core of the platform. It resolves the `client_token` to a `client_id`, checks rate limits, loads (or caches) the RAGBot, and runs the full conversation state machine.

> **Plan gate:** Only clients with `Plan == "paid"` receive AI responses. Free-plan clients receive a service unavailable message.

### Business Dashboard (JWT-authenticated)

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/upload-document` | Replace the knowledge document for a client's RAG bot |

Authentication uses a `Bearer <JWT>` header. The JWT is issued on login and expires after 8 hours.

---

## Chat Widget Integration

After registering, businesses receive a `client_token`. Embed the widget on any website:

```html
<!-- Place before </body> -->
<script>
  window.CrevoxegaConfig = {
    clientToken: "YOUR_CLIENT_TOKEN_HERE"
  };
</script>
<script src="https://your-domain.com/widget.js" async></script>
```

The widget script (`widget.js`) handles the chat UI, generates a `visitor_id` (to track the session), and sends messages to `POST /chat`.

---

## Conversation Flow

The chat engine (`backend_chat.py`) is a **state machine** driven by the `status` field stored per visitor in Firestore:

```
new visitor
    │
    └─► status: "active"  (default)
              │
              ├── msg = "help"              → help menu
              ├── msg = "change_language"   → status: "awaiting_language"
              ├── msg = "ask_for"           → status: "awaiting_language" (then contact)
              ├── msg = "complain" / complaint keyword
              │       └─► status: "handling_complaint"
              │               └─► status: "awaiting_contact" (if no lead yet)
              ├── msg = "feedback"          → status: "collecting_feedback"
              ├── high-intent keyword detected + no lead yet
              │       └─► answer first, then status: "awaiting_contact"
              └── default                  → RAG response (+ engagement hook every 3rd)
```

**Commands available to visitors:**

| Command | Effect |
|---|---|
| `help` | Show available commands |
| `change_language` | Switch to English / Hindi / Gujarati / Hinglish |
| `ask_for` | Volunteer contact info for follow-up |
| `complain` | Open complaint flow |
| `feedback` | Open feedback collection |

---

## Lead Capture Logic

The platform uses a **reciprocity-based** lead capture strategy:

1. When a visitor uses a high-intent keyword (pricing, buy, contact, demo, etc.), the bot **answers the question first**.
2. After answering, it smoothly asks for contact info (email or phone).
3. If the visitor provides contact details, they are encrypted and stored as a lead in Firestore.
4. If the visitor refuses (using refusal phrases), the bot acknowledges and never asks again in that session.
5. After lead capture, complaints skip the contact-request step (lead already on file).

**Intent keyword categories:**

- **Buying:** price, cost, fee, plan, payment, buy, purchase, trial
- **Contact:** call, phone, email, demo, appointment, book, meeting
- **Decision:** interested, want, need, tell me more, details, order

---

## Security

### Data at Rest
All PII (visitor names, emails, phone numbers, complaints, feedback) is encrypted with **Fernet** before writing to Firestore. Firestore document keys use deterministic SHA-256 hashes of visitor IDs — no raw identifiers are ever stored as document keys.

### Authentication
- Business login issues a **JWT** (8-hour expiry, HS256)
- Widget authentication uses a `client_token` (URL-safe random 32-byte token generated at registration) — separate from the JWT, so the widget token never grants dashboard access
- Admin operations validate `client_id` format against a strict allowlist regex

### Secrets
`get_secreats.py` always returns plain strings (never Pydantic `SecretStr`), with triple-unwrap logic to handle all Pydantic v1/v2 variants. GCP Secret Manager is the primary store; `.env` is the local fallback.

### Input Handling
- All user messages are sanitized before processing
- Feedback input is length-limited (2,000 chars) with control character stripping
- Phone and email extraction uses strict regex patterns — no raw user input is stored

---

## Rate Limiting

Each incoming `/chat` request is checked against `RateLimiter` keyed on `SHA-256(client_id:visitor_id)`:

| Check | Limit | Response |
|---|---|---|
| Temporary block | Active block period | 429 + retry-after |
| Duplicate message | Same message within 10s | 30s cooldown |
| Message length | > 4,000 characters | Rejected |
| Burst | > 120 requests / 60s | 10s wait |
| Token bucket | 300 req/min refill rate | Dynamic wait |
| Per minute | > 300 req/min | 60s wait |
| Per hour | > 5,000 req/hr | 300s wait |
| Per day | > 50,000 req/day | 3600s wait |
| Suspicious | > 100 req/min | 120s auto-block |

The in-memory rate limiter cleans up inactive users every 5 minutes.

---

## Deployment

### Heroku / Render / Railway

The `Procfile` is pre-configured:

```
web: gunicorn -w 2 -k uvicorn.workers.UvicornWorker frontend_fastapi:app --bind 0.0.0.0:$PORT
```

Steps:
1. Push the repo to your hosting platform.
2. Set all environment variables (see [Configuration](#configuration)) as platform secrets/config vars.
3. The platform will auto-detect the `Procfile` and `runtime.txt` (Python 3.10.11).

### Docker

```dockerfile
FROM python:3.10.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["gunicorn", "-w", "2", "-k", "uvicorn.workers.UvicornWorker", "frontend_fastapi:app", "--bind", "0.0.0.0:8000"]
```

### Firestore Collections

The platform expects the following Firestore structure:

```
chat_clients/                        ← business client documents
  {client_id}/
    (encrypted client fields)
    customer_list/                   ← visitor sessions
      {hash(visitor_id)}/
        status, language, lead_data,
        complaint, feedback, ...
```

---

## License

This project is licensed under the MIT License. See `LICENSE` for details.

---

*Powered by Crevoxega 🚀 — Custom AI automation for your business.*
