#!/usr/bin/env bash

# Octup E²A - Simple Project Runner
# Usage: ./run.sh <command>

set -euo pipefail

# ASCII Art Banner
show_banner() {
    echo
    echo "                         ░██                                         ░██████             "
    echo "                         ░██                                        ░██   ░██            "
    echo " ░███████   ░███████  ░████████ ░██    ░██ ░████████      ░███████        ░██  ░██████   "
    echo "░██    ░██ ░██    ░██    ░██    ░██    ░██ ░██    ░██    ░██    ░██   ░█████        ░██  "
    echo "░██    ░██ ░██           ░██    ░██    ░██ ░██    ░██    ░█████████  ░██       ░███████  "
    echo "░██    ░██ ░██    ░██    ░██    ░██   ░███ ░███   ░██    ░██        ░██       ░██   ░██  "
    echo " ░███████   ░███████      ░████  ░█████░██ ░██░█████      ░███████  ░████████  ░█████░██ "
    echo "                                           ░██                                           "
    echo "                                           ░██                                           "
    echo "                                                                                         "
    echo
}

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly COMPOSE_FILE="${SCRIPT_DIR}/docker/docker-compose.yml"

# Colors
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly RED='\033[0;31m'
readonly BLUE='\033[0;34m'
readonly NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $*"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $*"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

# Check if Supabase is running
check_supabase() {
    if ! pg_isready -h 127.0.0.1 -p 54322 -U postgres &> /dev/null; then
        log_warn "Supabase is not running. Starting..."
        supabase start
        echo
    fi
}

# Main commands
cmd_start() {
    show_banner
    log_info "Starting full Octup E²A stack..."
    
    # Check and start Supabase
    check_supabase
    
    # Start remaining services
    docker-compose -f "$COMPOSE_FILE" up -d api redis-local prefect-server prefect-worker
    
    # Wait for API
    log_info "Waiting for API readiness..."
    sleep 5
    
    log_success "Stack started!"
    echo
    echo "Available endpoints:"
    echo "  • API: http://localhost:8000"
    echo "  • API Docs: http://localhost:8000/docs"
    echo "  • Health: http://localhost:8000/healthz"
    echo "  • Supabase Studio: http://127.0.0.1:54323"
    echo "  • Prefect UI: http://localhost:4200"
}

cmd_stop() {
    show_banner
    log_info "Stopping services..."
    docker-compose -f "$COMPOSE_FILE" down
    log_success "Services stopped"
}

cmd_status() {
    show_banner
    echo "Service status:"
    
    # Supabase
    if pg_isready -h 127.0.0.1 -p 54322 -U postgres &> /dev/null; then
        echo -e "  ${GREEN}✓${NC} Supabase Database"
    else
        echo -e "  ${RED}✗${NC} Supabase Database"
    fi
    
    # API
    if curl -s http://localhost:8000/healthz &> /dev/null; then
        echo -e "  ${GREEN}✓${NC} API"
    else
        echo -e "  ${RED}✗${NC} API"
    fi
    
    # Prefect
    if curl -s http://localhost:4200/api/health &> /dev/null; then
        echo -e "  ${GREEN}✓${NC} Prefect Server"
    else
        echo -e "  ${RED}✗${NC} Prefect Server"
    fi
    
    # Redis
    if docker-compose -f "$COMPOSE_FILE" exec -T redis-local redis-cli ping &> /dev/null; then
        echo -e "  ${GREEN}✓${NC} Redis"
    else
        echo -e "  ${RED}✗${NC} Redis"
    fi
}

cmd_migrate() {
    show_banner
    log_info "Running database migrations..."
    check_supabase
    
    if command -v alembic &> /dev/null; then
        alembic upgrade head
    else
        docker-compose -f "$COMPOSE_FILE" exec api alembic upgrade head
    fi
    
    log_success "Migrations completed"
}

cmd_test() {
    show_banner
    log_info "Running tests..."
    
    if command -v pytest &> /dev/null; then
        pytest
    else
        docker-compose -f "$COMPOSE_FILE" exec api pytest
    fi
}

cmd_demo() {
    show_banner
    log_info "Starting system demonstration..."
    
    # Start stack if not running
    if ! curl -s http://localhost:8000/healthz &> /dev/null; then
        cmd_start
        sleep 10
    fi
    
    echo
    echo "=== OCTUP E²A DEMO ==="
    echo
    echo "1. System health check:"
    curl -s http://localhost:8000/healthz | jq .
    
    echo
    echo "2. Sending test event:"
    curl -X POST http://localhost:8000/ingest/shopify \
      -H "Content-Type: application/json" \
      -H "X-Tenant-Id: demo-3pl" \
      -d '{
        "source": "shopify",
        "event_type": "order_paid", 
        "event_id": "demo-'.$(date +%s)'",
        "order_id": "ord-demo-123",
        "occurred_at": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'"
      }' | jq .
    
    echo
    echo "3. Checking exceptions:"
    curl -s -H "X-Tenant-Id: demo-3pl" http://localhost:8000/exceptions | jq .
    
    echo
    echo "4. Prometheus metrics:"
    curl -s http://localhost:8000/metrics | head -20
    
    echo
    log_success "Demo completed!"
}

cmd_logs() {
    local service=${1:-api}
    docker-compose -f "$COMPOSE_FILE" logs -f "$service"
}

cmd_shell() {
    local service=${1:-api}
    docker-compose -f "$COMPOSE_FILE" exec "$service" bash
}

cmd_prefect() {
    show_banner
    log_info "Opening Prefect UI..."
    open http://localhost:4200 2>/dev/null || echo "Open http://localhost:4200 in your browser"
}

cmd_studio() {
    show_banner
    log_info "Opening Supabase Studio..."
    open http://127.0.0.1:54323 2>/dev/null || echo "Open http://127.0.0.1:54323 in your browser"
}

show_help() {
    show_banner
    echo "Octup E²A - Project Management"
    echo
    echo "Main commands:"
    echo "  start     - Start full stack"
    echo "  stop      - Stop all services"
    echo "  status    - Show service status"
    echo "  demo      - Run system demonstration"
    echo
    echo "Development:"
    echo "  run       - Run database migrations"
    echo "  test      - Run tests"
    echo "  logs      - Show logs [service]"
    echo "  shell     - Open shell in container [service]"
    echo "  studio    - Open Supabase Studio"
    echo "  prefect   - Open Prefect UI"
    echo
    echo "Examples:"
    echo "  ./run.sh start"
    echo "  ./run.sh demo"
    echo "  ./run.sh logs api"
    echo "  ./run.sh status"
}

# Main execution
case "${1:-help}" in
    "start")    cmd_start ;;
    "stop")     cmd_stop ;;
    "status")   cmd_status ;;
    "migrate")  cmd_migrate ;;
    "test")     cmd_test ;;
    "demo")     cmd_demo ;;
    "logs")     cmd_logs "${2:-api}" ;;
    "shell")    cmd_shell "${2:-api}" ;;
    "studio")   cmd_studio ;;
    "prefect")  cmd_prefect ;;
    "help"|*)   show_help ;;
esac
