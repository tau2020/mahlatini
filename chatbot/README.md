# Mahlatini AI Chatbot & Lead Management Platform

AI-powered travel concierge and automated lead pipeline for [Mahlatini Luxury Travel](https://mahlatini.com).

Captures enquiries via chatbot and website forms, classifies them with Claude, routes to Outlook with priority categories, creates To Do tasks, and pushes KPIs to Power BI — all in under 30 seconds.

## Architecture

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Backend** | FastAPI (Python 3.11) | API server, RAG orchestration, enquiry tracker |
| **Chat LLM** | Groq llama-3.3-70b | Response generation (RAG confidence 0.82-0.86) |
| **Classification** | Claude Sonnet 4.5 | Lead priority classification (0.95 confidence) |
| **Embeddings** | all-MiniLM-L6-v2 | Semantic search vectors (384 dims) |
| **Vector DB** | Qdrant | Knowledge base — 45,984 vectors |
| **Database** | PostgreSQL 16 | Conversations, leads, analytics, KPI tables |
| **Cache** | Redis 7 | Session store, dead-letter queue, rate limiting |
| **Workflows** | n8n 2.7.5 | 21-node pipeline: Outlook, Claude, To Do, Power BI |
| **Proxy** | Nginx Alpine | Rate limiting, CORS, WebSocket, security headers |
| **Frontend** | Vanilla JS widgets | Embeddable chat + enquiry form |

## Pipeline

```
Website Form / Chatbot → n8n Webhook → Validate → Spam Filter → Normalise
→ Outlook Draft → Claude Classify → Apply Category → Send Email
→ [Postgres Log + To Do Task + Power BI Push] → Respond
```

## Quick Start

### 1. Configure environment

```bash
cp .env.example .env
# Edit .env with your API keys (Anthropic, Groq, MS Graph, Power BI)
```

### 2. Start everything

```bash
./start.sh
```

This will:
- Build and start all 6 Docker services
- Wait for health checks to pass
- Run 31 unit/integration tests
- Run 9 live smoke tests (API, Qdrant, PostgreSQL, Redis, n8n, Nginx, chat, CORS, full pipeline)
- Print all endpoint URLs

### Other commands

```bash
./start.sh up         # Start services only (no tests)
./start.sh test       # Run tests only (services must be running)
./start.sh stop       # Stop all services
./start.sh restart    # Full restart + test
./start.sh logs       # Tail all service logs
./start.sh status     # Quick health overview
```

### 3. Ingest the knowledge base

```bash
docker compose run --rm --profile tools crawler python run_crawler.py --clear \
  --test-search "best safari destinations"
```

### 4. Embed the widget

Chat widget:
```html
<script src="https://your-domain.com/widget/chat-widget.js"
        data-api-url="https://your-domain.com"
        defer></script>
```

Enquiry form:
```html
<script src="https://your-domain.com/widget/enquiry-form.js"
        data-webhook-url="https://your-domain.com/webhook/website-enquiry"
        defer></script>

<form data-mahlatini-enquiry>
  <input name="name" required>
  <input name="email" type="email" required>
  <input name="destination">
  <textarea name="message"></textarea>
  <button type="submit">Send Enquiry</button>
</form>
```

## Services

| Service | Port | Health |
|---------|------|--------|
| Nginx (proxy) | 80, 443 | Proxies all routes |
| FastAPI (API) | 8000 (internal) | `GET /health` |
| Qdrant | 6333, 6334 | Dashboard at `:6333/dashboard` |
| PostgreSQL | 5432 | `pg_isready` |
| Redis | 6379 | `redis-cli ping` |
| n8n | 5678 | Editor at `:5678` |

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/chat/message` | Send a chat message (REST) |
| `WS` | `/api/chat/ws/{session_id}` | Real-time chat (WebSocket) |
| `GET` | `/health` | Service health check |
| `POST` | `/api/chat/n8n-callback` | n8n → chatbot push (HMAC verified) |
| `GET` | `/api/chat/n8n-pending/{session_id}` | Poll pending n8n messages |
| `POST` | `/webhook/website-enquiry` | Website form → n8n pipeline |
| `POST` | `/webhook/new-enquiry` | Chatbot lead → n8n pipeline |
| `GET` | `/api/docs` | Swagger UI (dev only) |

## Enquiry Collection

The chatbot uses a 4-phase state machine to collect booking details conversationally:

| Phase | Description |
|-------|-------------|
| **EXPLORING** | General chat, no booking details yet |
| **COLLECTING** | Actively gathering fields (1 per response) |
| **CONFIRMING** | All required fields filled, awaiting user confirmation |
| **SUBMITTED** | Enquiry sent to n8n, conversation continues informally |

Required fields: destination, travel month, duration, party size, contact name + email.

## Project Structure

```
chatbot/
├── start.sh                    # Start & test script
├── docker-compose.yml          # All 6 services
├── .env                        # Secrets (not in git)
├── nginx/nginx.conf            # Proxy, rate limits, CORS, security
├── config/prompts/             # LLM prompt templates
├── scripts/
│   ├── init_db.sql             # Core schema (8 tables, triggers)
│   ├── create_insert_lead_function.sql
│   ├── migrate_add_powerbi_analytics.sql
│   ├── backfill_leads_from_analytics.sql
│   └── sync-leads.sh           # Cron job for KPI backfill
├── n8n-workflows/
│   └── 02-enquiry-outlook-claude-powerbi.json  # Active workflow (21 nodes)
├── services/
│   ├── api/
│   │   ├── app/
│   │   │   ├── main.py         # FastAPI entry
│   │   │   ├── config.py       # Pydantic Settings
│   │   │   ├── models/schemas.py
│   │   │   ├── routers/chat.py # REST + WebSocket + n8n callback
│   │   │   └── services/
│   │   │       ├── rag.py      # RAG orchestration
│   │   │       ├── classifier.py
│   │   │       ├── lead_scorer.py
│   │   │       ├── n8n_client.py  # Webhook sender + DLQ + subworkflows
│   │   │       ├── enquiry_tracker.py
│   │   │       └── llm/        # LLM factory + Groq/Claude clients
│   │   ├── widget/
│   │   │   ├── chat-widget.js  # Embeddable chatbot
│   │   │   └── enquiry-form.js # Form submission handler
│   │   └── tests/
│   │       ├── conftest.py
│   │       └── test_n8n_integration.py  # 31 tests
│   └── crawler/                # Knowledge base pipeline
└── docs/
    ├── POWERBI_CONTINUATION_PLAN.md
    ├── POWERBI_DASHBOARD_DESIGN.md
    └── UX_REDESIGN.md
```

## n8n Workflow

The active workflow (`6g2SZsGNZiKpP01K`) handles both website forms and chatbot leads:

```
Webhook: Website Enquiry ─┐
                          ├→ Validate → Spam Filter → Normalise → Outlook Draft
Webhook: Chatbot Lead ────┘     → Capture ID → Claude Classify → Parse
                                → Build Patch → Apply Category → Send Email
                                → [Postgres Log | To Do Task | Power BI Push]
                                → Route by Source → Respond to Webhook
```

Classification tiers: **IMMEDIATE** (urgent/high-budget), **IMPORTANT** (mid-budget/occasions), **NOT_IMPORTANT** (browsing/low-score).

## Database

Key tables:
- `conversations` — session tracking
- `messages` — chat history with intent/sentiment
- `leads` — contact info, classification, budget, destination, scoring
- `analytics_events` — JSONB event log (n8n writes here)
- `destinations` — 24 seed destinations
- `powerbi_realtime_kpis` — auto-updated KPI aggregates

See [POWERBI_CONTINUATION_PLAN.md](docs/POWERBI_CONTINUATION_PLAN.md) for BI setup.

## Development

```bash
# Run tests (services must be running)
./start.sh test

# Run API locally (outside Docker)
cd services/api
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Run crawler
docker compose run --rm --profile tools crawler python run_crawler.py

# Deploy n8n workflow update
./start.sh up  # ensure services running
# Edit workflow in n8n UI at http://localhost:5678
# Export: n8n-workflows/02-enquiry-outlook-claude-powerbi.json
```

## License

Proprietary — Mahlatini Luxury Travel 2026
