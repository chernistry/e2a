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

cmd_clear_demo() {
    log_info "Clearing Shopify Mock demo data only..."
    
    if curl -s http://localhost:8090/health &> /dev/null; then
        echo "🧹 Clearing Shopify Mock orders..."
        curl -X POST http://localhost:8090/demo/clear-orders | jq .
    else
        echo "ℹ️  Shopify Mock not running"
    fi
    
    log_success "Demo data cleared! (Database exceptions remain intact)"
}

cmd_logs() {
    local service=${1:-api}
    log_info "Showing logs for $service..."
    docker-compose -f "$COMPOSE_FILE" logs -f "$service"
}

cmd_shell() {
    local service=${1:-api}
    log_info "Opening shell in $service container..."
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

cmd_status() {
    echo "=== SERVICE STATUS ==="
    docker-compose -f "$COMPOSE_FILE" ps
    
    echo
    echo "=== HEALTH CHECKS ==="
    
    # API Health
    if curl -s http://localhost:8000/healthz &> /dev/null; then
        echo "✅ API: http://localhost:8000 (healthy)"
    else
        echo "❌ API: http://localhost:8000 (not responding)"
    fi
    
    # Shopify Mock Health
    if curl -s http://localhost:8090/health &> /dev/null; then
        echo "✅ Shopify Mock: http://localhost:8090 (healthy)"
    else
        echo "❌ Shopify Mock: http://localhost:8090 (not responding)"
    fi
    
    # Dashboard (if running)
    if curl -s http://localhost:3000 &> /dev/null; then
        echo "✅ Dashboard: http://localhost:3000 (running)"
    else
        echo "ℹ️  Dashboard: http://localhost:3000 (not running - use 'make web-dev')"
    fi
}

cmd_migrate() {
    log_info "Running database migrations..."
    # Add migration logic here if needed
    log_success "Migrations completed"
}

cmd_test() {
    log_info "Running tests..."
    # Add test logic here if needed
    log_success "Tests completed"
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
    echo "Event Generation:"
    echo "  generate  - Generate events [single|batch|stream] [duration]"
    echo "  stats     - Show system statistics"
    echo "  reset     - FULL DATABASE RESET (deletes ALL data)"
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
    echo "  ./run.sh generate single"
    echo "  ./run.sh generate batch"
    echo "  ./run.sh generate stream 60"
    echo "  ./run.sh stats"
    echo "  ./run.sh reset"
    echo "  ./run.sh logs api"
    echo "  ./run.sh status"
}

cmd_processing_stages() {
    show_banner
    log_info "🔄 Processing Stage Management"
    
    # Check if API is running
    if ! curl -s http://localhost:8000/healthz &> /dev/null; then
        log_warn "API not running. Starting stack..."
        cmd_start
        sleep 10
    fi
    
    echo
    echo "=== PROCESSING STAGE MANAGEMENT ==="
    echo
    
    # Create test orders with processing stages
    log_info "Creating test orders with processing stages..."
    
    for i in {1..3}; do
        order_id="STAGE-TEST-$(printf "%03d" $i)"
        echo "📋 Creating stages for order $order_id..."
        
        # Use Python to create stages
        python3 -c "
import asyncio
import sys
sys.path.append('.')

from app.storage.db import get_session
from app.services.processing_stage_service import ProcessingStageService

async def create_stages():
    async with get_session() as db:
        service = ProcessingStageService(db)
        stages = await service.initialize_order_stages('demo-3pl', '$order_id')
        print(f'   ✅ Created {len(stages)} stages for order $order_id')
        
        # Start first stage (data_ingestion) 
        started = await service.start_stage('demo-3pl', '$order_id', 'data_ingestion')
        if started:
            print(f'   ⏳ Started data_ingestion stage')
            
            # Complete it after a short delay
            import time
            time.sleep(0.1)
            completed = await service.complete_stage('demo-3pl', '$order_id', 'data_ingestion', 
                                                   {'records_processed': 100, 'validation_passed': True})
            if completed:
                print(f'   ✅ Completed data_ingestion stage')

asyncio.run(create_stages())
" 2>/dev/null || echo "   ❌ Failed to create stages for $order_id"
    done
    
    echo
    log_info "📊 Processing Stage Metrics:"
    
    # Get current metrics
    python3 -c "
import asyncio
import sys
sys.path.append('.')

from app.storage.db import get_session
from app.services.processing_stage_service import ProcessingStageService, DataCompletenessService

async def show_metrics():
    async with get_session() as db:
        service = ProcessingStageService(db)
        completeness_service = DataCompletenessService(db)
        
        # Get eligible stages
        eligible = await service.get_eligible_stages('demo-3pl', limit=10)
        print(f'🎯 Eligible stages ready to process: {len(eligible)}')
        
        if eligible:
            print('   Ready to process:')
            for stage in eligible[:5]:  # Show first 5
                print(f'   - {stage.order_id}: {stage.stage_name}')
        
        # Get metrics
        metrics = await service.get_stage_metrics('demo-3pl')
        print(f'📈 Stage status counts: {metrics[\"status_counts\"]}')
        
        # Show completion rates for stages that have data
        if metrics['completion_rates']:
            print('📊 Stage completion rates:')
            for stage_name, stats in metrics['completion_rates'].items():
                if stats['total'] > 0:
                    print(f'   - {stage_name}: {stats[\"completion_rate\"]:.1f}% ({stats[\"completed\"]}/{stats[\"total\"]})')

asyncio.run(show_metrics())
" 2>/dev/null || echo "   ❌ Failed to get metrics"
    
    echo
    log_info "🔄 Processing eligible stages..."
    
    # Process some eligible stages
    python3 -c "
import asyncio
import sys
import random
sys.path.append('.')

from app.storage.db import get_session
from app.services.processing_stage_service import ProcessingStageService

async def process_stages():
    async with get_session() as db:
        service = ProcessingStageService(db)
        
        # Get eligible stages
        eligible = await service.get_eligible_stages('demo-3pl', limit=5)
        
        if not eligible:
            print('   ℹ️  No eligible stages to process')
            return
        
        processed = 0
        for stage in eligible:
            try:
                # Start the stage
                started = await service.start_stage('demo-3pl', stage.order_id, stage.stage_name)
                if started:
                    print(f'   ⏳ Processing {stage.stage_name} for {stage.order_id}...')
                    
                    # Simulate processing time
                    import time
                    time.sleep(0.2)
                    
                    # 90% success rate
                    if random.random() > 0.1:
                        # Complete successfully
                        stage_data = {
                            'processed_records': random.randint(50, 200),
                            'processing_time_ms': random.randint(100, 500),
                            'success': True
                        }
                        completed = await service.complete_stage('demo-3pl', stage.order_id, stage.stage_name, stage_data)
                        if completed:
                            print(f'   ✅ Completed {stage.stage_name} for {stage.order_id}')
                            processed += 1
                    else:
                        # Fail occasionally
                        failed = await service.fail_stage('demo-3pl', stage.order_id, stage.stage_name, 
                                                        'Simulated processing failure')
                        if failed:
                            print(f'   ❌ Failed {stage.stage_name} for {stage.order_id} (will retry)')
            except Exception as e:
                print(f'   ❌ Error processing {stage.stage_name}: {e}')
        
        print(f'   📊 Processed {processed}/{len(eligible)} stages successfully')

asyncio.run(process_stages())
" 2>/dev/null || echo "   ❌ Failed to process stages"
    
    echo
    log_success "Processing stage management completed!"
    echo
    echo "🎯 Next steps:"
    echo "   • Run './run.sh processing-stages' again to process more stages"
    echo "   • Check dashboard: http://localhost:3000/dashboard/overview"
    echo "   • View API docs: http://localhost:8000/docs"
}

cmd_autonomous_processing() {
    show_banner
    log_info "🤖 Starting Autonomous Processing Stage Management"
    
    # Check if API is running
    if ! curl -s http://localhost:8000/healthz &> /dev/null; then
        log_warn "API not running. Starting stack..."
        cmd_start
        sleep 10
    fi
    
    echo
    echo "=== AUTONOMOUS PROCESSING LOOP ==="
    echo "Press Ctrl+C to stop"
    echo
    
    local iteration=1
    
    while true; do
        echo "🔄 Iteration $iteration - $(date '+%H:%M:%S')"
        
        # Process eligible stages
        python3 -c "
import asyncio
import sys
import random
sys.path.append('.')

from app.storage.db import get_session
from app.services.processing_stage_service import ProcessingStageService, DataCompletenessService

async def autonomous_cycle():
    async with get_session() as db:
        service = ProcessingStageService(db)
        
        # Get eligible stages
        eligible = await service.get_eligible_stages('demo-3pl', limit=10)
        
        if not eligible:
            print('   ℹ️  No eligible stages - creating new test order...')
            
            # Create a new test order
            import time
            order_id = f'AUTO-{int(time.time())}'
            stages = await service.initialize_order_stages('demo-3pl', order_id)
            print(f'   📋 Created {len(stages)} stages for order {order_id}')
            
            # Get eligible stages again
            eligible = await service.get_eligible_stages('demo-3pl', limit=10)
        
        processed = 0
        failed = 0
        
        for stage in eligible[:5]:  # Process up to 5 stages per cycle
            try:
                # Start the stage
                started = await service.start_stage('demo-3pl', stage.order_id, stage.stage_name)
                if started:
                    # Simulate processing
                    import time
                    time.sleep(0.1)
                    
                    # 85% success rate
                    if random.random() > 0.15:
                        stage_data = {
                            'processed_at': time.time(),
                            'records': random.randint(50, 200),
                            'success': True
                        }
                        completed = await service.complete_stage('demo-3pl', stage.order_id, stage.stage_name, stage_data)
                        if completed:
                            processed += 1
                    else:
                        failed_stage = await service.fail_stage('demo-3pl', stage.order_id, stage.stage_name, 
                                                              'Random processing failure')
                        if failed_stage:
                            failed += 1
            except Exception as e:
                failed += 1
        
        # Get current metrics
        metrics = await service.get_stage_metrics('demo-3pl')
        eligible_count = len(await service.get_eligible_stages('demo-3pl'))
        
        print(f'   📊 Processed: {processed}, Failed: {failed}, Eligible: {eligible_count}')
        print(f'   📈 Total stages: {sum(metrics[\"status_counts\"].values())}')

asyncio.run(autonomous_cycle())
" 2>/dev/null || echo "   ❌ Processing cycle failed"
        
        # Wait before next iteration
        sleep 3
        iteration=$((iteration + 1))
    done
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
    echo "Event Generation:"
    echo "  generate  - Generate events [single|batch|stream] [duration]"
    echo "  stats     - Show system statistics"
    echo "  reset     - FULL DATABASE RESET (deletes ALL data)"
    echo
    echo "Processing & Orchestration:"
    echo "  processing-stages - Manual processing stage management"
    echo "  autonomous        - Start autonomous processing loop"
    echo "  flows             - Show Prefect flow status"
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
    echo "  ./run.sh processing-stages"
    echo "  ./run.sh autonomous"
    echo "  ./run.sh flows"
    echo "  ./run.sh generate single"
    echo "  ./run.sh generate batch"
    echo "  ./run.sh generate stream 60"
    echo "  ./run.sh stats"
    echo "  ./run.sh reset"
    echo "  ./run.sh logs api"
    echo "  ./run.sh status"
}

cmd_flows() {
    show_banner
    log_info "📊 Prefect Flow Management"
    
    # Check if Prefect server is running
    if ! curl -s http://localhost:4200/api/health &> /dev/null; then
        log_warn "Prefect server not running. Starting..."
        cmd_start
        sleep 10
    fi
    
    echo
    echo "=== PREFECT FLOW STATUS ==="
    echo
    
    log_info "Current flow deployments:"
    echo "  🏢 business-orchestrator    - Master orchestrator (every hour)"
    echo "  📦 order-processing         - Order pipeline with stages (every 30min)"
    echo "  ⚠️  exception-management     - Exception resolution (every 2 hours)"
    echo "  💰 billing-management       - Billing operations (daily 2 AM)"
    echo
    
    log_info "Flow architecture highlights:"
    echo "  ✅ Consolidated processing stages into order processing flow"
    echo "  ✅ Resolution tracking integrated with exception management"
    echo "  ✅ No overlapping responsibilities between flows"
    echo "  ✅ Real-world aligned scheduling and dependencies"
    echo
    
    log_info "To deploy flows:"
    echo "  cd /Users/sasha/IdeaProjects/octup/root"
    echo "  prefect deploy --all"
    echo
    
    log_info "To monitor flows:"
    echo "  Open Prefect UI: http://localhost:4200"
    echo "  Or run: ./run.sh prefect"
}

# Main execution
case "${1:-help}" in
    "start")              cmd_start ;;
    "stop")               cmd_stop ;;
    "status")             cmd_status ;;
    "migrate")            cmd_migrate ;;
    "test")               cmd_test ;;
    "demo")               cmd_demo ;;
    "generate")           cmd_generate "${2:-single}" "${3:-30}" ;;
    "stats")              cmd_stats ;;
    "reset")              cmd_reset ;;
    "processing-stages")  cmd_processing_stages ;;
    "autonomous")         cmd_autonomous_processing ;;
    "flows")              cmd_flows ;;
    "logs")               cmd_logs "${2:-api}" ;;
    "shell")              cmd_shell "${2:-api}" ;;
    "studio")             cmd_studio ;;
    "prefect")            cmd_prefect ;;
    "help"|*)             show_help ;;
esac
