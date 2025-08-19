# Octup E²A Quick Start Guide

**E²A = _Exceptions_ → _Explanations_ → _Actions_**

[![License: CC BY-NC 4.0](https://img.shields.io/badge/License-CC%20BY--NC%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by-nc/4.0/)

## Prerequisites

- Python 3.11+
- Poetry 1.8.0+
- Docker & Docker Compose
- Supabase CLI (for local development)
- OpenRouter API Key (for AI features)

## Technology Stack

**FastAPI** (async, OpenAPI docs), **Supabase/PostgreSQL** (managed, auth, real-time), **Redis** (persistence, atomic ops), **Prefect** (Python-first, cloud-native), **OpenRouter** (cost-effective, multi-model), **Next.js + Prometheus** (real-time dashboard, metrics).

### Design Patterns & Principles

**🔧 Key Architectural Decisions:**

1. **Idempotency Strategy**: Redis-backed duplicate protection with 5-second locks and UPSERT fallback
2. **AI Fallback Strategy**: Hybrid AI + rule-based system with 0.55 confidence threshold and $20/day budget  
3. **Event Sourcing**: Event-driven SLA evaluation with configurable policies and real-time breach detection

**Benefits**: Fast duplicate detection, AI-assisted analysis, real-time SLA monitoring.

## Quick Start

### Option 1: Local Development (Recommended)

Uses local Supabase and optional local Redis for development:

```bash
# 1. Clone the repository
git clone <repository_url>
cd oktup/root

# 2. Install dependencies
poetry install

# 3. Complete local setup (one command!)
make dev-local

# 4. Start the web dashboard (in another terminal)
make web-install
make web-dev
```

This will:
- Set up local environment configuration
- Start local Supabase
- Run database migrations
- Seed demo data
- Start all services

**To start the dashboard:**
```bash
# Install dashboard dependencies
make web-install

# Start dashboard in development mode
make web-dev
```
- Launch the web dashboard at http://localhost:3000

**Available endpoints:**
- **Dashboard**: http://localhost:3000 (simplified single-page view)
- API: http://localhost:8000
- API Docs: http://localhost:8000/docs
- Supabase Studio: http://localhost:54323
- Prefect UI: http://localhost:4200

### Option 2: Cloud Development

Uses cloud services (Supabase Cloud, Redis Cloud):

```bash
# 1. Clone and install
git clone <repository_url>
cd oktup/root
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

### Manual Installation

If you prefer step-by-step setup:

1. **Clone the repository:**
   ```bash
   git clone <repository_url>
   cd oktup/root
   ```

2. **Install dependencies:**
   ```bash
   poetry install
   ```

3. **Choose your environment:**
   ```bash
   # For local development
   make setup-local
   
   # For cloud deployment
   make setup-cloud
   ```

4. **Start Supabase (local only):**
   ```bash
   supabase start
   ```

5. **Run database migrations:**
   ```bash
   make migrate
   ```

6. **Seed demonstration data:**
   ```bash
   make seed
   ```

7. **Start services:**
   ```bash
   # Local development
   make up-local
   
   # Cloud deployment
   make up-cloud
   ```

8. **Verify installation:**
   ```bash
   curl http://localhost:8000/healthz
   ```

## Configuration

### Environment Setup

The project supports two main configurations:

#### Local Development (.env.local)
- **Database**: Local Supabase (started with `supabase start`)
- **Redis**: Local Redis container or Redis Cloud
- **AI**: OpenRouter API
- **Observability**: Next.js dashboard with real-time metrics and Prometheus integration

#### Cloud Deployment (.env.cloud)
- **Database**: Supabase Cloud
- **Redis**: Redis Cloud
- **AI**: OpenRouter API
- **Observability**: Next.js dashboard with real-time metrics and Prometheus integration

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

# Database (Supabase Cloud)
# DATABASE_URL=postgresql+asyncpg://postgres.your-project:${SUPABASE_DB_PASSWORD}@aws-0-eu-central-1.pooler.supabase.com:6543/postgres?ssl=require
# DIRECT_URL=postgresql+asyncpg://postgres.your-project:${SUPABASE_DB_PASSWORD}@aws-0-eu-central-1.pooler.supabase.com:5432/postgres?ssl=require

# Redis (Local or Cloud)
REDIS_URL=redis://localhost:6379/0
# REDIS_URL=rediss://default:${REDIS_PASSWORD}@${REDIS_CLOUD_PUBLIC_ENDPOINT}/0

# AI Configuration
AI_PROVIDER_BASE_URL=https://openrouter.ai/api/v1
AI_MODEL=google/gemini-2.0-flash-exp:free
AI_API_KEY=sk-or-v1-...
AI_MAX_DAILY_TOKENS=200000
AI_MIN_CONFIDENCE=0.55

# Observability (Optional)
# Dashboard runs on http://localhost:3000
# Prometheus metrics available on http://localhost:8000/metrics

# Prefect Local Server (Default)
PREFECT_API_URL=http://localhost:4200/api
PREFECT_WORK_POOL=default-agent-pool

# Prefect Cloud (Alternative - for production)
# PREFECT_API_URL=https://api.prefect.cloud/...
# PREFECT_API_KEY=pnu_...

# Slack Integration (Optional)
SLACK_BOT_TOKEN=xoxb-your-bot-token-here
SLACK_BOT_USER_ID=U1234567890
SLACK_SIGNING_SECRET=your-signing-secret-here
SLACK_DEFAULT_CHANNEL=#oktup-alerts
SLACK_NOTIFICATION_ENABLED=true
```

### AI Configuration

```yaml
# Production settings via OpenRouter
AI_PROVIDER_BASE_URL: https://openrouter.ai/api/v1
AI_MODEL: google/gemini-2.0-flash-exp:free
AI_MAX_DAILY_TOKENS: 200000
AI_MIN_CONFIDENCE: 0.55
AI_TIMEOUT_SECONDS: 3
AI_RETRY_MAX_ATTEMPTS: 2
AI_SAMPLING_SEVERITY: important_only
```

### AI Resilience Features
- **Circuit Breaker Protection**: Prevents cascade failures during AI service outages
- **Fallback Mechanisms**: Rule-based analysis when AI is unavailable (confidence < 0.55)
- **Token Budget Management**: Daily limits (200K tokens) to control costs
- **Confidence Thresholds**: Quality gates for AI-generated content
- **Comprehensive Monitoring**: Prometheus metrics for AI requests, tokens, costs, failures

### AI Implementation Details
**Prompts**: External Jinja2 templates in `/prompts/` directory for maintainability
**JSON Extraction**: Robust parsing with fallback mechanisms for malformed AI responses  
**Error Handling**: Graceful degradation with rule-based fallbacks
**Cost Control**: Daily token budgets and request sampling based on severity 
**RAG Integration**: Foundation compatible with vector databases (Qdrant, Pinecone) and RAG frameworks like [Meulex](https://github.com/chernistry/meulex/) for enhanced Slack bot capabilities

### Switching Between Environments

```bash
# Switch to local development
make setup-local

# Switch to cloud deployment
make setup-cloud
```

### Policy Configuration

Business logic is configured through YAML files:

- **SLA Policies**: `app/business/policies/default_sla.yaml`
- **Billing Tariffs**: `app/business/policies/default_tariffs.yaml`

Changes are loaded automatically on application startup.

## Event Generation & Testing

The project includes a comprehensive event generation system for testing and demonstration:

### Features

- **Shopify Mock API**: Realistic e-commerce data generation with automatic webhook integration
- **Event Streaming**: Configurable order generation with realistic timing
- **Exception Simulation**: 13% natural exception rate with realistic scenarios
- **Multi-tenant Support**: Tenant isolation and correlation tracking

### Usage

```bash
# Start demo system with Shopify Mock API
cd docker
docker-compose --profile demo up -d

# Generate events using run.sh
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

Once started, access the demo interfaces:
- **Shopify Mock API**: http://localhost:8090/docs
- **E²A Dashboard**: http://localhost:3000
- **API Documentation**: http://localhost:8000/docs
- **Prefect UI**: http://localhost:4200

### Configuration

The demo system is configured through environment variables:
```bash
OCTUP_API_URL=http://localhost:8000     # Target API
WEBHOOK_DELAY_SECONDS=2                 # Webhook timing
SHOPIFY_DEMO_API_PRODUCE_MIN_ORDERS=1001  # Batch size range
SHOPIFY_DEMO_API_PRODUCE_MAX_ORDERS=1999
```

## Business Process Flows

E²A includes modern Prefect flows that implement realistic business processes:

### Available Flows

1. **Order Processing Pipeline** - Monitors order fulfillment progress and SLA compliance
2. **Exception Management Pipeline** - Analyzes patterns and attempts automated resolution
3. **Billing Management Pipeline** - Generates invoices and processes adjustments
4. **Business Operations Orchestrator** - Coordinates all business processes

### Running Flows

```bash
# Start Prefect server (if not already running)
prefect server start

# Start a worker (in another terminal)
cd root
prefect worker start --pool default-agent-pool --type process

# Deploy flows
prefect deploy flows/order_processing_flow.py:order_processing_pipeline -n order-processing -p default-agent-pool
prefect deploy flows/exception_management_flow.py:exception_management_pipeline -n exception-management -p default-agent-pool
prefect deploy flows/billing_management_flow.py:billing_management_pipeline -n billing-management -p default-agent-pool
prefect deploy flows/business_operations_orchestrator.py:business_operations_orchestrator -n business-orchestrator -p default-agent-pool

# Run flows manually
prefect deployment run 'order-processing-pipeline/order-processing'
prefect deployment run 'exception-management-pipeline/exception-management'
prefect deployment run 'billing-management-pipeline/billing-management'
prefect deployment run 'business-operations-orchestrator/business-orchestrator'
```

### Flow Configuration

Flows are configured in `prefect.yaml` with default parameters:
- **Tenant**: demo-3pl
- **Lookback Hours**: 24 (for order and billing flows)
- **Analysis Hours**: 168 (for exception management)

## Running the Application


### Development
```bash
# Start all services using run.sh
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
```
