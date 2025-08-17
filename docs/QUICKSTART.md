# Octup E²A Quick Start Guide

**E²A = _Exceptions_ → _Explanations_ → _Actions_**

[![License: CC BY-NC 4.0](https://img.shields.io/badge/License-CC%20BY--NC%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by-nc/4.0/)

## Prerequisites

- Python 3.11+
- Poetry 1.8.0+
- Docker & Docker Compose
- Supabase CLI (for local development)
- OpenRouter API Key (for AI features)

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

## Event Simulator

The project includes a sophisticated event simulator for testing and demonstration:

### Features

- **Data Sources**: Olist e-commerce dataset (397K+ orders) or custom NDJSON
- **Modes**: `push` (realistic streaming) or `replay` (fast batch processing)
- **Realistic Load**: Configurable events per second, jitter, random bursts
- **Error Injection**: Simulates duplicates, out-of-order delivery, malformed payloads
- **Observability**: Prometheus metrics on port 9109

### Usage

```bash
# Start realistic event stream (2 EPS)
make simulate

# High-load testing (20 EPS)
make simulate-fast

# Fast replay mode
make simulate-replay

# View simulator logs
make simulate-logs

# Custom configuration
EPS=10 WORKERS=6 BAD_RATE=0.05 make simulate
```

## Running the Application

### Development
```bash
# Start all services
make up

# View logs
make logs SERVICE=api

# Stop services
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
