# Mahlatini AI Chatbot

AI-powered travel concierge for [Mahlatini Luxury Travel](https://mahlatini.com), built with open-source technologies.

## Architecture

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Backend** | FastAPI (Python) | API server, RAG orchestration |
| **LLM** | Mistral-7B via Ollama | Response generation |
| **Embeddings** | all-MiniLM-L6-v2 | Semantic search vectors |
| **Vector DB** | Qdrant | Knowledge base storage |
| **Database** | PostgreSQL 16 | Conversations, leads, analytics |
| **Cache** | Redis 7 | Session store, rate limiting |
| **Workflows** | n8n | Jira, email, Power BI automation |
| **Proxy** | Nginx | TLS, rate limiting, WebSocket |
| **Frontend** | Vanilla JS widget | Embeddable chat interface |

## Quick Start

### 1. Configure environment

```bash
cp .env.example .env
# Edit .env with your credentials
```

### 2. Start services

```bash
docker compose up -d
```

### 3. Pull the LLM model

```bash
docker compose exec ollama ollama pull mistral:7b-instruct-v0.3-q4_K_M
```

### 4. Ingest the knowledge base

```bash
docker compose run --rm crawler python run_crawler.py --clear \
  --test-search "best safari destinations"
```

### 5. Embed the widget

Add this to any page on the Mahlatini website:

```html
<script src="http://localhost/widget/chat-widget.js"
        data-api-url="http://localhost"
        defer></script>
```

## Project Structure

```
chatbot/
├── docker-compose.yml         # All services
├── .env.example               # Environment template
├── nginx/nginx.conf           # Reverse proxy config
├── config/prompts/            # LLM prompt templates
├── scripts/init_db.sql        # Database schema + seeds
├── services/
│   ├── api/                   # FastAPI backend
│   │   ├── app/
│   │   │   ├── main.py        # App entry point
│   │   │   ├── config.py      # Settings
│   │   │   ├── models/        # Pydantic schemas
│   │   │   ├── routers/       # Chat + Admin endpoints
│   │   │   └── services/      # LLM, RAG, classifier, etc.
│   │   └── widget/            # Chat widget JS/CSS
│   └── crawler/               # Knowledge base pipeline
│       ├── parser.py          # HTML content extraction
│       ├── chunker.py         # Content chunking
│       ├── ingest.py          # Qdrant embedding + storage
│       └── run_crawler.py     # Pipeline orchestrator
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/chat/message` | Send a chat message (REST) |
| `WS` | `/api/chat/ws/{session_id}` | Real-time chat (WebSocket) |
| `GET` | `/health` | Service health check |
| `GET` | `/api/admin/knowledge-base` | KB statistics |
| `GET` | `/api/docs` | Swagger UI (dev only) |

## Development

```bash
# Run API locally (outside Docker)
cd services/api
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Run crawler locally
cd services/crawler
pip install -r requirements.txt
python run_crawler.py --website-dir ../../www.mahlatini.com --qdrant-host localhost
```

## License

Proprietary — Mahlatini Luxury Travel © 2026
