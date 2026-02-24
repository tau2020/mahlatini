#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════
# Mahlatini Chatbot — Start & Test Script
# ═══════════════════════════════════════════════════════════
# Usage:
#   ./start.sh            Start all services + run smoke tests
#   ./start.sh up         Start services only (no tests)
#   ./start.sh test       Run tests only (services must be running)
#   ./start.sh stop       Stop all services
#   ./start.sh restart    Restart all services + test
#   ./start.sh logs       Tail all service logs
#   ./start.sh status     Show service status + quick health check
# ═══════════════════════════════════════════════════════════

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Colours
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

pass() { echo -e "  ${GREEN}✓${NC} $1"; }
fail() { echo -e "  ${RED}✗${NC} $1"; FAILURES=$((FAILURES + 1)); }
info() { echo -e "${CYAN}→${NC} $1"; }
header() { echo -e "\n${BOLD}$1${NC}"; }

FAILURES=0

# ─── Pre-flight checks ───────────────────────────────────
preflight() {
    header "Pre-flight checks"

    if ! command -v docker &>/dev/null; then
        echo -e "${RED}Error: docker not found. Install Docker Desktop first.${NC}"
        exit 1
    fi
    pass "docker installed"

    if ! docker info &>/dev/null; then
        echo -e "${RED}Error: Docker daemon not running. Start Docker Desktop.${NC}"
        exit 1
    fi
    pass "Docker daemon running"

    if [ ! -f .env ]; then
        echo -e "${RED}Error: .env file missing. Copy .env.example and fill in credentials.${NC}"
        exit 1
    fi
    pass ".env file exists"

    if [ ! -f docker-compose.yml ]; then
        echo -e "${RED}Error: docker-compose.yml not found. Run from chatbot/ directory.${NC}"
        exit 1
    fi
    pass "docker-compose.yml found"
}

# ─── Start services ──────────────────────────────────────
start_services() {
    header "Starting services"

    info "Building API image (if needed)..."
    docker compose build api 2>&1 | tail -1

    info "Starting all services..."
    docker compose up -d 2>&1 | tail -5

    info "Waiting for services to become healthy..."
    local max_wait=90
    local waited=0
    local all_healthy=false

    while [ $waited -lt $max_wait ]; do
        local healthy_count
        healthy_count=$(docker compose ps --format json 2>/dev/null | python3 -c "
import sys, json
healthy = 0
for line in sys.stdin:
    line = line.strip()
    if not line: continue
    svc = json.loads(line)
    status = svc.get('Health', svc.get('Status', ''))
    if 'healthy' in status or svc.get('Service') in ('nginx', 'n8n'):
        healthy += 1
print(healthy)
" 2>/dev/null || echo "0")

        if [ "$healthy_count" -ge 6 ]; then
            all_healthy=true
            break
        fi

        printf "\r  Waiting... %ds (${healthy_count}/6 services ready)" "$waited"
        sleep 3
        waited=$((waited + 3))
    done
    echo ""

    if $all_healthy; then
        pass "All services started"
    else
        fail "Some services failed to start within ${max_wait}s"
    fi
}

# ─── Show status ─────────────────────────────────────────
show_status() {
    header "Service status"
    docker compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null
}

# ─── Smoke tests ─────────────────────────────────────────
run_tests() {
    header "Smoke tests"
    FAILURES=0

    # 1. API health
    info "API health check..."
    local health
    health=$(curl -sf http://localhost/health 2>/dev/null || echo "FAIL")
    if echo "$health" | grep -q '"healthy"'; then
        pass "API healthy — $(echo "$health" | python3 -c "import sys,json; d=json.load(sys.stdin); svcs=', '.join(f'{k}={v}' for k,v in d.get('services',{}).items()); print(svcs)" 2>/dev/null || echo "ok")"
    else
        fail "API health check failed"
    fi

    # 2. Qdrant vectors
    info "Qdrant vector store..."
    local vectors
    vectors=$(curl -sf http://localhost:6333/collections/mahlatini_kb 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin)['result']['points_count'])" 2>/dev/null || echo "0")
    if [ "$vectors" -gt 0 ] 2>/dev/null; then
        pass "Qdrant: ${vectors} vectors indexed"
    else
        fail "Qdrant: no vectors found (run crawler to index)"
    fi

    # 3. PostgreSQL tables
    info "PostgreSQL database..."
    local tables
    tables=$(docker exec chatbot-postgres-1 psql -U mahlatini -d mahlatini_chatbot -tAc \
        "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'" 2>/dev/null || echo "0")
    if [ "$tables" -gt 5 ] 2>/dev/null; then
        pass "PostgreSQL: ${tables} tables"
    else
        fail "PostgreSQL: only ${tables} tables found"
    fi

    # 4. Redis ping
    info "Redis cache..."
    local redis_ok
    redis_ok=$(docker exec chatbot-redis-1 redis-cli ping 2>/dev/null || echo "FAIL")
    if [ "$redis_ok" = "PONG" ]; then
        pass "Redis: PONG"
    else
        fail "Redis not responding"
    fi

    # 5. n8n workflow active
    info "n8n workflow engine..."
    local n8n_status
    n8n_status=$(curl -sf http://localhost:5678/healthz 2>/dev/null || echo "FAIL")
    if [ "$n8n_status" != "FAIL" ]; then
        pass "n8n: running on :5678"
    else
        fail "n8n not responding"
    fi

    # 6. Nginx proxy
    info "Nginx proxy..."
    local nginx_status
    nginx_status=$(curl -sf -o /dev/null -w "%{http_code}" http://localhost/ 2>/dev/null || echo "000")
    if [ "$nginx_status" = "200" ]; then
        pass "Nginx: proxying on :80"
    else
        fail "Nginx returned HTTP ${nginx_status}"
    fi

    # 7. Chat endpoint
    info "Chat endpoint (live LLM call)..."
    local chat_resp
    chat_resp=$(curl -sf -m 30 -X POST http://localhost/api/chat/message \
        -H 'Content-Type: application/json' \
        -d '{"session_id":"startup-test","message":"Hello, what destinations do you recommend?"}' 2>/dev/null || echo "FAIL")
    if echo "$chat_resp" | grep -q '"reply"'; then
        local provider
        provider=$(echo "$chat_resp" | python3 -c "import sys,json; print(json.load(sys.stdin).get('provider','?'))" 2>/dev/null || echo "?")
        pass "Chat working (provider: ${provider})"
    else
        fail "Chat endpoint not responding"
    fi

    # 8. Website serving
    info "Mahlatini website..."
    local website_status
    website_status=$(curl -sf -o /dev/null -w "%{http_code}" http://localhost:8080/ 2>/dev/null || echo "000")
    if [ "$website_status" = "200" ]; then
        pass "Website: serving on :8080"
    else
        fail "Website returned HTTP ${website_status}"
    fi

    # 9. Webhook endpoint (CORS preflight)
    info "Webhook CORS preflight (9/10)..."
    local cors_status
    cors_status=$(curl -sf -o /dev/null -w "%{http_code}" -X OPTIONS http://localhost/webhook/website-enquiry \
        -H "Origin: https://www.mahlatini.com" \
        -H "Access-Control-Request-Method: POST" 2>/dev/null || echo "000")
    if [ "$cors_status" = "204" ]; then
        pass "Webhook CORS: 204 No Content"
    else
        fail "Webhook CORS returned HTTP ${cors_status}"
    fi

    # 10. n8n webhook (full pipeline test)
    info "n8n pipeline (website form → Outlook + Claude)..."
    local webhook_resp
    webhook_resp=$(curl -sf -m 30 -X POST http://localhost/webhook/website-enquiry \
        -H 'Content-Type: application/json' \
        -d "{
            \"source\": \"website_form\",
            \"timestamp\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",
            \"form_data\": {
                \"name\": \"Startup Test\",
                \"email\": \"startup-test@example.com\",
                \"destination\": \"Kenya\",
                \"message\": \"Start script smoke test\",
                \"budget_range\": \"£5000\"
            },
            \"metadata\": {\"page_url\": \"startup-test\"}
        }" 2>/dev/null || echo "FAIL")
    if echo "$webhook_resp" | grep -q '"classification"'; then
        local classification
        classification=$(echo "$webhook_resp" | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'{d.get(\"classification\",\"?\")} ({d.get(\"confidence\",0)})')" 2>/dev/null || echo "?")
        pass "n8n pipeline: ${classification}"
    else
        fail "n8n pipeline failed: ${webhook_resp:0:100}"
    fi

    # Summary
    header "Results"
    if [ $FAILURES -eq 0 ]; then
        echo -e "${GREEN}${BOLD}All tests passed!${NC}"
    else
        echo -e "${RED}${BOLD}${FAILURES} test(s) failed${NC}"
    fi
    echo ""
    echo -e "  ${BOLD}Endpoints:${NC}"
    echo "    Website:       http://localhost:8080"
    echo "    Chatbot API:   http://localhost/api/chat/message"
    echo "    WebSocket:     ws://localhost/api/chat/ws/{session_id}"
    echo "    Health:        http://localhost/health"
    echo "    Webhook:       http://localhost/webhook/website-enquiry"
    echo "    n8n Editor:    http://localhost:5678"
    echo "    Qdrant UI:     http://localhost:6333/dashboard"
    echo ""

    return $FAILURES
}

# ─── Unit tests ──────────────────────────────────────────
run_unit_tests() {
    header "Unit / integration tests"
    info "Running pytest..."
    if command -v python3 &>/dev/null && python3 -c "import pytest" 2>/dev/null; then
        cd "$SCRIPT_DIR/services/api"
        python3 -m pytest tests/ -v --tb=short 2>&1
        cd "$SCRIPT_DIR"
    else
        echo -e "  ${YELLOW}⚠${NC} pytest not installed locally — skipping (run: pip install pytest pytest-asyncio)"
    fi
}

# ─── Stop services ───────────────────────────────────────
stop_services() {
    header "Stopping services"
    docker compose down 2>&1
    pass "All services stopped"
}

# ─── Tail logs ───────────────────────────────────────────
tail_logs() {
    docker compose logs -f --tail=50
}

# ─── Main ────────────────────────────────────────────────
CMD="${1:-start}"

case "$CMD" in
    start)
        preflight
        start_services
        show_status
        run_unit_tests
        run_tests
        ;;
    up)
        preflight
        start_services
        show_status
        ;;
    test)
        run_unit_tests
        run_tests
        ;;
    stop)
        stop_services
        ;;
    restart)
        stop_services
        preflight
        start_services
        show_status
        run_tests
        ;;
    logs)
        tail_logs
        ;;
    status)
        show_status
        echo ""
        # Quick health
        curl -sf http://localhost/health 2>/dev/null | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(f\"API: {d['status']}\")
for k,v in d.get('services',{}).items():
    print(f'  {k}: {v}')
" 2>/dev/null || echo "API: not responding"
        ;;
    *)
        echo "Usage: ./start.sh [start|up|test|stop|restart|logs|status]"
        exit 1
        ;;
esac
