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
    
    # Start services with correct profiles
    docker-compose -f "$COMPOSE_FILE" --profile prefect up -d
    
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
    docker-compose -f "$COMPOSE_FILE" --profile prefect --profile demo --profile local-redis --profile dashboard --profile observability down --remove-orphans
    log_success "Services stopped"
}

cmd_restart() {
    show_banner
    log_info "Restarting services..."
    docker-compose -f "$COMPOSE_FILE" --profile prefect --profile demo --profile local-redis --profile dashboard --profile observability down --remove-orphans
    sleep 2
    docker-compose -f "$COMPOSE_FILE" --profile prefect up -d
    log_success "Services restarted"
    echo
    echo "Available endpoints:"
    echo "  • API: http://localhost:8000"
    echo "  • API Docs: http://localhost:8000/docs"
    echo "  • Health: http://localhost:8000/healthz"
    echo "  • Supabase Studio: http://127.0.0.1:54323"
    echo "  • Prefect UI: http://localhost:4200"
}

cmd_status() {
    show_banner
    echo "=== SERVICE STATUS ==="
    docker-compose -f "$COMPOSE_FILE" ps
    
    echo
    echo "=== HEALTH CHECKS ==="
    
    # Supabase
    if pg_isready -h 127.0.0.1 -p 54322 -U postgres &> /dev/null; then
        echo -e "  ${GREEN}✓${NC} Supabase Database"
    else
        echo -e "  ${RED}✗${NC} Supabase Database"
    fi
    
    # API Health
    if curl -s http://localhost:8000/healthz &> /dev/null; then
        echo -e "  ${GREEN}✓${NC} API: http://localhost:8000"
    else
        echo -e "  ${RED}✗${NC} API: http://localhost:8000"
    fi
    
    # Prefect
    if curl -s http://localhost:4200/api/health &> /dev/null; then
        echo -e "  ${GREEN}✓${NC} Prefect Server: http://localhost:4200"
    else
        echo -e "  ${RED}✗${NC} Prefect Server: http://localhost:4200"
    fi
    
    # Shopify Mock (if running)
    if curl -s http://localhost:8090/health &> /dev/null; then
        echo -e "  ${GREEN}✓${NC} Shopify Mock: http://localhost:8090"
    else
        echo -e "  ${YELLOW}ℹ${NC} Shopify Mock: http://localhost:8090 (not running)"
    fi
    
    # Dashboard (if running)
    if curl -s http://localhost:3000 &> /dev/null; then
        echo -e "  ${GREEN}✓${NC} Dashboard: http://localhost:3000"
    else
        echo -e "  ${YELLOW}ℹ${NC} Dashboard: http://localhost:3000 (not running - use 'make web-dev')"
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
    
    log_success "Tests completed"
}

cmd_demo() {
    show_banner
    log_info "Starting system demonstration..."
    
    # Start stack if not running
    if ! curl -s http://localhost:8000/healthz &> /dev/null; then
        cmd_start
        sleep 10
    fi
    
    # Start Shopify Mock if not running
    if ! curl -s http://localhost:8090/health &> /dev/null; then
        log_info "Starting Shopify Mock API..."
        docker-compose -f "$COMPOSE_FILE" --profile demo up -d shopify-mock
        sleep 5
    fi
    
    echo
    echo "=== OCTUP E²A DEMO ==="
    echo
    echo "1. System health check:"
    curl -s http://localhost:8000/healthz | jq .
    
    echo
    echo "2. Shopify Mock health:"
    curl -s http://localhost:8090/health | jq .
    
    echo
    echo "3. Current system metrics (before new events):"
    curl -s -H "X-Tenant-Id: demo-3pl" http://localhost:8000/api/dashboard/metrics | jq '{active_exceptions, total_exceptions, orders_processed_today}'
    
    echo
    echo "4. Generating new events via Shopify Mock..."
    echo "   → Generating single order with potential problems:"
    curl -X POST http://localhost:8090/demo/generate-order | jq .
    
    echo
    echo "   → Generating batch of orders (1001-1999 orders with ~13% problems):"
    curl -X POST http://localhost:8090/demo/generate-batch | jq .
    
    echo
    echo "5. Waiting for webhook processing..."
    sleep 8
    
    echo
    echo "6. Updated system metrics (after new events):"
    curl -s -H "X-Tenant-Id: demo-3pl" http://localhost:8000/api/dashboard/metrics | jq '{active_exceptions, total_exceptions, orders_processed_today, ai_total_analyzed}'
    
    echo
    echo "7. Recent exceptions:"
    curl -s -H "X-Tenant-Id: demo-3pl" http://localhost:8000/api/dashboard/exceptions/live?limit=5 | jq '.exceptions[] | {id, order_id, reason_code, severity, status}'
    
    echo
    echo "8. Demo statistics:"
    curl -s http://localhost:8090/demo/stats | jq .
    
    echo
    log_success "Demo completed!"
    echo
    echo "📋 Available endpoints:"
    echo "   • API: http://localhost:8000"
    echo "   • API Docs: http://localhost:8000/docs"
    echo "   • Dashboard: http://localhost:3000 (run 'make web-dev' if not started)"
    echo "   • Shopify Mock: http://localhost:8090"
    echo "   • Shopify Mock Docs: http://localhost:8090/docs"
    echo
    echo "🎯 Next steps:"
    echo "   • Open dashboard: http://localhost:3000/dashboard/overview"
    echo "   • Generate more events: curl -X POST http://localhost:8090/demo/generate-order"
    echo "   • Generate batch: curl -X POST http://localhost:8090/demo/generate-batch"
    echo "   • Clear demo data: curl -X POST http://localhost:8090/demo/clear-orders"
    echo "   • Full database reset: ./run.sh reset"
}

cmd_generate() {
    local type=${1:-single}
    
    # Start Shopify Mock if not running
    if ! curl -s http://localhost:8090/health &> /dev/null; then
        log_info "Starting Shopify Mock API..."
        docker-compose -f "$COMPOSE_FILE" --profile demo up -d shopify-mock
        sleep 5
    fi
    
    case $type in
        "single")
            log_info "Generating single order with potential problems..."
            curl -X POST http://localhost:8090/demo/generate-order | jq .
            ;;
        "batch")
            log_info "Generating batch of orders (1001-1999 orders with ~13% problems)..."
            curl -X POST http://localhost:8090/demo/generate-batch | jq .
            ;;
        "stream")
            local duration=${2:-30}
            log_info "Streaming orders for $duration seconds..."
            echo "Generating orders every 2 seconds for $duration seconds..."
            local end_time=$(($(date +%s) + duration))
            while [ $(date +%s) -lt $end_time ]; do
                curl -X POST http://localhost:8090/demo/generate-order | jq -r '.order_id + " (" + (.has_problems | tostring) + ")"'
                sleep 2
            done
            log_success "Stream completed!"
            ;;
        *)
            echo "Usage: ./run.sh generate [single|batch|stream] [duration_for_stream]"
            echo "  single - Generate one order"
            echo "  batch  - Generate 1001-1999 orders"
            echo "  stream - Generate orders continuously (default: 30 seconds)"
            ;;
    esac
}

cmd_stats() {
    echo "=== SYSTEM STATISTICS ==="
    echo
    echo "1. Shopify Mock Statistics:"
    if curl -s http://localhost:8090/health &> /dev/null; then
        curl -s http://localhost:8090/demo/stats | jq .
    else
        echo "   Shopify Mock not running"
    fi
    
    echo
    echo "2. API Dashboard Metrics:"
    if curl -s http://localhost:8000/healthz &> /dev/null; then
        curl -s -H "X-Tenant-Id: demo-3pl" http://localhost:8000/api/dashboard/metrics | jq '{
            active_exceptions,
            total_exceptions,
            resolved_exceptions,
            orders_processed_today,
            sla_compliance_rate,
            ai_analysis_success_rate,
            ai_total_analyzed,
            revenue_at_risk_cents,
            monthly_adjustments_cents
        }'
    else
        echo "   API not running"
    fi
    
    echo
    echo "3. Recent Exceptions (last 5):"
    if curl -s http://localhost:8000/healthz &> /dev/null; then
        curl -s -H "X-Tenant-Id: demo-3pl" http://localhost:8000/api/dashboard/exceptions/live?limit=5 | jq '.exceptions[] | {
            id,
            order_id,
            reason_code,
            severity,
            status,
            created_at
        }'
    else
        echo "   API not running"
    fi
}

cmd_reset() {
    show_banner
    log_info "🗑️  FULL DATABASE RESET - This will delete ALL data!"
    echo
    echo "⚠️  WARNING: This will permanently delete:"
    echo "   • All exceptions and SLA breaches"
    echo "   • All order events and processing history"
    echo "   • All invoices and adjustments"
    echo "   • All tenant configurations"
    echo "   • All DLQ (Dead Letter Queue) items"
    echo "   • All Shopify Mock demo data"
    echo
    read -p "Are you sure you want to continue? Type 'YES' to confirm: " confirm
    
    if [ "$confirm" != "YES" ]; then
        log_info "Reset cancelled."
        return 0
    fi
    
    echo
    log_info "Starting full database reset..."
    
    # 1. Clear Shopify Mock data first
    if curl -s http://localhost:8090/health &> /dev/null; then
        echo "🧹 Clearing Shopify Mock data..."
        curl -X POST http://localhost:8090/demo/clear-orders | jq . || echo "Shopify Mock clear failed"
    else
        echo "ℹ️  Shopify Mock not running - skipping"
    fi
    
    # 2. Connect to database and clear all tables
    echo "🗄️  Clearing database tables..."
    
    # Check if API is running to get database connection
    if ! curl -s http://localhost:8000/healthz &> /dev/null; then
        log_info "Starting API to access database..."
        cmd_start
        sleep 10
    fi
    
    # Use psql to connect and clear tables
    # Get database URL from .env
    DB_URL=$(grep "^DATABASE_URL=" .env | cut -d'=' -f2- | sed 's/postgresql+asyncpg:/postgresql:/' | sed 's/@127.0.0.1:54322/@localhost:54322/')
    
    if [ -z "$DB_URL" ]; then
        log_error "Could not find DATABASE_URL in .env file"
        return 1
    fi
    
    echo "🔗 Connecting to database..."
    
    # Create SQL script for clearing all tables
    cat > /tmp/reset_db.sql << 'EOF'
-- Disable foreign key checks temporarily
SET session_replication_role = replica;

-- Clear all data from tables (in correct order due to foreign keys)
TRUNCATE TABLE invoice_adjustments CASCADE;
TRUNCATE TABLE invoices CASCADE;
TRUNCATE TABLE exceptions CASCADE;
TRUNCATE TABLE order_events CASCADE;
TRUNCATE TABLE dlq CASCADE;
TRUNCATE TABLE tenants CASCADE;

-- Re-enable foreign key checks
SET session_replication_role = DEFAULT;

-- Reset sequences
ALTER SEQUENCE tenants_id_seq RESTART WITH 1;
ALTER SEQUENCE order_events_id_seq RESTART WITH 1;
ALTER SEQUENCE exceptions_id_seq RESTART WITH 1;
ALTER SEQUENCE invoices_id_seq RESTART WITH 1;
ALTER SEQUENCE invoice_adjustments_id_seq RESTART WITH 1;
ALTER SEQUENCE dlq_id_seq RESTART WITH 1;

-- Show table counts to verify
SELECT 'tenants' as table_name, COUNT(*) as count FROM tenants
UNION ALL
SELECT 'order_events', COUNT(*) FROM order_events
UNION ALL
SELECT 'exceptions', COUNT(*) FROM exceptions
UNION ALL
SELECT 'invoices', COUNT(*) FROM invoices
UNION ALL
SELECT 'invoice_adjustments', COUNT(*) FROM invoice_adjustments
UNION ALL
SELECT 'dlq', COUNT(*) FROM dlq;
EOF
    
    # Execute the SQL script
    if command -v psql >/dev/null 2>&1; then
        echo "📊 Executing database reset..."
        psql "$DB_URL" -f /tmp/reset_db.sql
        rm -f /tmp/reset_db.sql
    else
        # Alternative: use docker to run psql
        echo "📊 Executing database reset via Docker..."
        docker run --rm -i --network host postgres:15 psql "$DB_URL" < /tmp/reset_db.sql
        rm -f /tmp/reset_db.sql
    fi
    
    # 3. Re-seed with fresh demo tenant
    echo "🌱 Re-seeding database with demo tenant..."
    
    # Create a minimal seed script
    cat > /tmp/seed_demo.sql << 'EOF'
-- Insert demo tenant
INSERT INTO tenants (name, display_name, sla_config, billing_config, created_at, updated_at)
VALUES (
    'demo-3pl',
    'Demo 3PL Company',
    '{"delivery_sla_hours": 72, "response_sla_hours": 4, "escalation_threshold": 24}',
    '{"currency": "USD", "billing_model": "per_exception", "rate_cents": 500}',
    NOW(),
    NOW()
);
EOF
    
    if command -v psql >/dev/null 2>&1; then
        psql "$DB_URL" -f /tmp/seed_demo.sql
    else
        docker run --rm -i --network host postgres:15 psql "$DB_URL" < /tmp/seed_demo.sql
    fi
    rm -f /tmp/seed_demo.sql
    
    # 4. Verify reset
    echo
    echo "✅ Database reset completed!"
    echo
    echo "📊 Verification - Current system state:"
    
    if curl -s http://localhost:8000/healthz &> /dev/null; then
        echo "🔍 API Metrics:"
        curl -s -H "X-Tenant-Id: demo-3pl" http://localhost:8000/api/dashboard/metrics | jq '{
            active_exceptions,
            total_exceptions,
            orders_processed_today,
            ai_total_analyzed
        }' || echo "Could not fetch metrics"
    fi
    
    if curl -s http://localhost:8090/health &> /dev/null; then
        echo "🔍 Shopify Mock Stats:"
        curl -s http://localhost:8090/demo/stats | jq . || echo "Could not fetch Shopify stats"
    fi
    
    echo
    log_success "🎉 Full reset completed! Database is now clean and ready for fresh data."
    echo
    echo "🎯 Next steps:"
    echo "   • Generate fresh data: ./run.sh demo"
    echo "   • Generate single order: ./run.sh generate single"
    echo "   • Generate batch: ./run.sh generate batch"
    echo "   • Open dashboard: http://localhost:3000/dashboard/overview"
}

cmd_logs() {
    local service=${1:-api}
    log_info "Showing logs for $service..."
    docker-compose -f "$COMPOSE_FILE" logs -f "$service"
}

cmd_shell() {
    local service=${1:-api}
    log_info "Opening shell in $service container..."
    docker-compose -f "$COMPOSE_FILE" exec "$service" /bin/bash
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
    echo "  restart   - Restart all services"
    echo "  status    - Show service status"
    echo "  demo      - Run system demonstration"
    echo
    echo "Event Generation:"
    echo "  generate  - Generate events [single|batch|stream] [duration]"
    echo "  stats     - Show system statistics"
    echo "  reset     - FULL DATABASE RESET (deletes ALL data)"
    echo
    echo "Development:"
    echo "  migrate   - Run database migrations"
    echo "  test      - Run tests"
    echo "  logs      - Show logs [service]"
    echo "  shell     - Open shell in container [service]"
    echo "  studio    - Open Supabase Studio"
    echo "  prefect   - Open Prefect UI"
    echo
    echo "Examples:"
    echo "  ./run.sh start"
    echo "  ./run.sh demo"
    echo "  ./run.sh generate single"
    echo "  ./run.sh generate batch"
    echo "  ./run.sh generate stream 60"
    echo "  ./run.sh stats"
    echo "  ./run.sh reset"
    echo "  ./run.sh logs api"
    echo "  ./run.sh status"
}

# Main execution
case "${1:-help}" in
    "start")              cmd_start ;;
    "stop")               cmd_stop ;;
    "restart")            cmd_restart ;;
    "status")             cmd_status ;;
    "migrate")            cmd_migrate ;;
    "test")               cmd_test ;;
    "demo")               cmd_demo ;;
    "generate")           cmd_generate "${2:-single}" "${3:-30}" ;;
    "stats")              cmd_stats ;;
    "reset")              cmd_reset ;;
    "logs")               cmd_logs "${2:-api}" ;;
    "shell")              cmd_shell "${2:-api}" ;;
    "studio")             cmd_studio ;;
    "prefect")            cmd_prefect ;;
    "help"|*)             show_help ;;
esac
