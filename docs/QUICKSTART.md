# E²A Quick Start Guide

**E²A = _Exceptions_ → _Explanations_ → _Actions_**

[![License: CC BY-NC 4.0](https://img.shields.io/badge/License-CC%20BY--NC%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by-nc/4.0/)

## Prerequisites

- Python 3.11+
- Poetry 1.8.0+
- Docker & Docker Compose
- Supabase CLI (for local development)
- OpenRouter API Key (for AI features)

## Technology Stack

**FastAPI** (async, OpenAPI), **Supabase/PostgreSQL** (managed, real-time), **Redis** (persistence, atomic ops), **Prefect** (Python-first, cloud-native), **OpenRouter** (cost-effective, multi-model), **Next.js + Prometheus** (real-time dashboard, metrics).

## Quick Start

### Option 1: Local Development (Recommended)

```bash
# 1. Clone the repository
git clone <repository_url>
cd octup/root

# 2. Install dependencies
poetry install

# 3. Complete local setup (one command!)
make dev-local

# 4. Start the web dashboard (separate terminal)
make web-install && make web-dev
```

This will:
- Set up local environment configuration
- Start local Supabase
- Run database migrations (including resolution tracking)
- Seed demo data
- Start all services

**Available endpoints:**
- **Dashboard**: http://localhost:3000
- API: http://localhost:8000
- API Docs: http://localhost:8000/docs
- Supabase Studio: http://localhost:54323
- Prefect UI: http://localhost:4200

### Option 2: Cloud Development

```bash
# 1. Clone and install
git clone <repository_url>
cd octup/root
poetry install

# 2. Setup cloud configuration
make setup-cloud

# 3. Edit .env with your cloud credentials
# DATABASE_URL, REDIS_URL, AI_API_KEY

# 4. Deploy
make migrate
make seed
make up-cloud
```

## Configuration

### Environment Variables

Key variables in `.env`:

```bash
# Core Application
APP_ENV=dev
SERVICE_NAME=octup-e2a
LOG_LEVEL=INFO

# Database (Local Supabase)
DATABASE_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:54322/postgres
DIRECT_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:54322/postgres

# Redis (Local or Cloud)
REDIS_URL=redis://localhost:6379/0

# AI Configuration
AI_PROVIDER_BASE_URL=https://openrouter.ai/api/v1
AI_MODEL=google/gemini-2.0-flash-exp:free
AI_API_KEY=sk-or-v1-...
AI_MAX_DAILY_TOKENS=200000
AI_MIN_CONFIDENCE=0.55

# Resolution Tracking (NEW)
OCTUP_MAX_RESOLUTION_ATTEMPTS=2  # Default: 2, configurable

# Prefect Local Server
PREFECT_API_URL=http://localhost:4200/api
PREFECT_WORK_POOL=default-agent-pool
```

### Resolution Tracking Configuration

**New Feature**: Prevents repeated failed automation attempts.

```bash
# Configure max attempts per exception
export OCTUP_MAX_RESOLUTION_ATTEMPTS=3  # Default: 2

# AI confidence thresholds
AI_MIN_CONFIDENCE=0.7
AI_MIN_SUCCESS_PROBABILITY=0.6
LOW_CONFIDENCE_BLOCK_THRESHOLD=0.3
```

**Benefits:**
- **Efficiency**: 80-85% reduction in unnecessary processing
- **Resource Optimization**: No wasted cycles on hopeless cases
- **Operational Clarity**: Full visibility into attempt history
- **Configurability**: Easy adjustment via environment variables

### AI Configuration

```yaml
AI_PROVIDER_BASE_URL: https://openrouter.ai/api/v1
AI_MODEL: google/gemini-2.0-flash-exp:free
AI_MAX_DAILY_TOKENS: 200000
AI_MIN_CONFIDENCE: 0.55
AI_TIMEOUT_SECONDS: 3
AI_RETRY_MAX_ATTEMPTS: 2
```

**AI Resilience Features:**
- **Circuit Breaker Protection**: Prevents cascade failures
- **Fallback Mechanisms**: Rule-based analysis when AI unavailable
- **Token Budget Management**: Daily limits (200K tokens)
- **Confidence Thresholds**: Quality gates for AI content

## Event Generation & Testing

### Demo System with Shopify Mock API

```bash
# Start demo system
cd docker
docker-compose --profile demo up -d

# Generate test data
cd root

# Generate single order
./run.sh generate single

# Generate batch of orders (1001-1999 orders)
./run.sh generate batch

# Stream orders continuously
./run.sh generate stream 60    # Stream for 60 seconds

# View system statistics
./run.sh stats
```

### Demo System Access

- **Shopify Mock API**: http://localhost:8090/docs
- **E²A Dashboard**: http://localhost:3000
- **API Documentation**: http://localhost:8000/docs
- **Prefect UI**: http://localhost:4200

### Configuration

```bash
OCTUP_API_URL=http://localhost:8000
WEBHOOK_DELAY_SECONDS=2
SHOPIFY_DEMO_API_PRODUCE_MIN_ORDERS=1001
SHOPIFY_DEMO_API_PRODUCE_MAX_ORDERS=1999
```

## Business Process Flows

### Available Flows

1. **Order Processing Pipeline** - Monitors fulfillment progress and SLA compliance
2. **Exception Management Pipeline** - Analyzes patterns and attempts automated resolution with tracking
3. **Billing Management Pipeline** - Generates invoices and processes adjustments
4. **Business Operations Orchestrator** - Coordinates all business processes

### Running Flows

```bash
# Start Prefect server (if not already running)
prefect server start

# Start a worker (separate terminal)
cd root
prefect worker start --pool default-agent-pool --type process

# Deploy flows
prefect deploy flows/order_processing_flow.py:order_processing_pipeline -n order-processing -p default-agent-pool
prefect deploy flows/exception_management_flow.py:exception_management_pipeline -n exception-management -p default-agent-pool
prefect deploy flows/billing_management_flow.py:billing_management_pipeline -n billing-management -p default-agent-pool
prefect deploy flows/business_operations_orchestrator.py:business_operations_orchestrator -n business-orchestrator -p default-agent-pool

# Run flows manually
prefect deployment run 'exception-management-pipeline/exception-management'
prefect deployment run 'order-processing-pipeline/order-processing'
prefect deployment run 'billing-management-pipeline/billing-management'
prefect deployment run 'business-operations-orchestrator/business-orchestrator'
```

### Flow Configuration

Flows configured in `prefect.yaml`:
- **Tenant**: demo-3pl
- **Lookback Hours**: 24 (order/billing flows)
- **Analysis Hours**: 168 (exception management)

## Resolution Tracking System

### Database Migration

The resolution tracking system requires a database migration:

```bash
# Apply migration automatically (included in make dev-local)
python scripts/apply_resolution_tracking.py

# Or manually
alembic upgrade head
```

### Testing Resolution Tracking

```bash
# Test the resolution tracking system
python test_resolution_tracking.py

# Test with custom max attempts
OCTUP_MAX_RESOLUTION_ATTEMPTS=1 python test_resolution_tracking.py
```

### Expected Behavior

**First Flow Run:**
- Processes all eligible exceptions (e.g., 106 OPEN exceptions)
- Each gets `resolution_attempts = 1`
- Some resolve, others fail

**Second Flow Run:**
- Only processes exceptions with `resolution_attempts < max_resolution_attempts`
- Failed exceptions get `resolution_attempts = 2`
- After max attempts, exceptions get `resolution_blocked = true`

**Third Flow Run:**
- Only processes new exceptions
- Blocked exceptions are skipped
- 80-85% reduction in processing load

## Running the Application

### Development
```bash
# Start all services
./run.sh start

# Or use make commands
make up                    # Start API only
make up-local             # Start with local Redis
make up-demo              # Start with demo system

# View logs
make logs SERVICE=api
docker logs <service_name>

# Stop services
./run.sh stop
make down
```

### Production
```bash
# Direct FastAPI server
uvicorn app.main:app --host 0.0.0.0 --port 8000

# With Gunicorn
gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker
```

## Deployment

### Docker
```bash
# Build image
docker build -t octup-e2a .

# Run container
docker run -p 8000:8000 --env-file .env octup-e2a
```

### Kubernetes
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: octup-e2a
spec:
  replicas: 3
  selector:
    matchLabels:
      app: octup-e2a
  template:
    metadata:
      labels:
        app: octup-e2a
    spec:
      containers:
      - name: api
        image: octup-e2a:latest
        ports:
        - containerPort: 8000
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: octup-secrets
              key: database-url
        - name: OCTUP_MAX_RESOLUTION_ATTEMPTS
          value: "2"
```

## Testing

```bash
# Run all tests
pytest

# With coverage
pytest --cov=app --cov-report=html

# Specific test categories
pytest tests/unit/          # Unit tests
pytest tests/integration/   # Integration tests
pytest tests/e2e/          # End-to-end tests

# Test resolution tracking specifically
pytest tests/unit/test_ai_automated_resolution.py
```

## Troubleshooting

### Common Issues

**Resolution tracking not working:**
```bash
# Check migration applied
python scripts/apply_resolution_tracking.py

# Verify database schema
psql -c "\d exceptions" | grep resolution
```

**AI service problems:**
```bash
# Check circuit breaker status
curl http://localhost:8000/api/circuit-breakers

# Reset if needed
curl -X POST http://localhost:8000/api/circuit-breakers/ai_service/reset
```

**Database connection issues:**
```bash
# Quick health check
curl http://localhost:8000/health

# Check Supabase status
supabase status
```

### Performance Monitoring

```bash
# View system statistics
./run.sh stats

# Check resolution tracking performance
python test_resolution_tracking.py

# Monitor Prometheus metrics
curl http://localhost:8000/metrics | grep resolution
```

## Next Steps

1. **Explore the Dashboard**: http://localhost:3000
2. **Generate Test Data**: `./run.sh generate batch`
3. **Run Business Flows**: Use Prefect UI at http://localhost:4200
4. **Monitor Resolution Tracking**: `python test_resolution_tracking.py`
5. **Check API Documentation**: http://localhost:8000/docs

**🔧 See [KB.MD](KB.MD) for advanced troubleshooting, performance tuning, and operational guidance.**

---

**Last Updated**: 2025-08-20
