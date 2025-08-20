# Octup E²A Knowledge Base

**E²A = _Exceptions_ → _Explanations_ → _Actions_**

[![License: CC BY-NC 4.0](https://img.shields.io/badge/License-CC%20BY--NC%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by-nc/4.0/)

## Table of Contents

1. [Quick Start](#quick-start)
2. [System Architecture](#system-architecture)
3. [Resolution Tracking System](#resolution-tracking-system)
4. [Data Enrichment Pipeline](#data-enrichment-pipeline)
5. [Configuration & Environment](#configuration--environment)
6. [Business Process Flows](#business-process-flows)
7. [Monitoring & Operations](#monitoring--operations)
8. [Deployment & Production](#deployment--production)
9. [Troubleshooting](#troubleshooting)

---

## Quick Start

### Prerequisites

- Python 3.11+
- Poetry 1.8.0+
- Docker & Docker Compose
- Supabase CLI (for local development)
- OpenRouter API Key (for AI features)

### Technology Stack

**FastAPI** (async, OpenAPI), **Supabase/PostgreSQL** (managed, real-time), **Redis** (persistence, atomic ops), **Prefect** (Python-first, cloud-native), **OpenRouter** (cost-effective, multi-model), **Next.js + Prometheus** (real-time dashboard, metrics).

### Local Development Setup

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

### Cloud Development Setup

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

### Demo System with Event Generation

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

---

## System Architecture

### Overview
The Octup E²A system provides **systematic AI-powered exception processing** with **guaranteed completeness**, **automatic reprocessing**, and **comprehensive monitoring**. The architecture ensures no data is lost in incomplete states and provides full visibility into processing health.

### Core Principles
1. **Single Responsibility**: Each service has one clear purpose
2. **No Overlap**: Services don't duplicate functionality
3. **Clear Boundaries**: Well-defined interfaces between services
4. **Real-World Alignment**: Architecture mirrors actual e-commerce operations
5. **Scalable Design**: Services can be scaled independently

### Service Layer Architecture

#### 1. Data Processing Services

**`ProcessingStageService`**
- **Purpose**: Manages order processing pipeline stages and dependencies
- **Responsibilities**:
  - Initialize processing stages for new orders
  - Track stage progression and dependencies
  - Handle stage failures and retries
  - Provide stage metrics and monitoring
- **Used By**: Order Processing Flow
- **Database Tables**: `order_processing_stages`

**`DataCompletenessService`**
- **Purpose**: Validates data completeness across processing stages
- **Responsibilities**:
  - Create and manage completeness checks
  - Validate data quality and completeness
  - Track validation results and metrics
- **Used By**: Order Processing Flow (via ProcessingStageService)
- **Database Tables**: `data_completeness_checks`

#### 2. Business Logic Services

**`SLAEngine`**
- **Purpose**: Monitors SLA compliance and detects breaches
- **Responsibilities**:
  - Evaluate SLA compliance for orders
  - Create exception records for breaches
  - Calculate SLA metrics and reporting
- **Used By**: Order Processing Flow, Exception Management Flow
- **Database Tables**: `exceptions`, `order_events`

**`AIAutomatedResolution`**
- **Purpose**: Provides AI-powered exception resolution
- **Responsibilities**:
  - Analyze exceptions for automated resolution potential
  - Execute automated resolution actions
  - Track resolution success rates
- **Used By**: Exception Management Flow
- **Database Tables**: `exceptions`

**`AIExceptionAnalyst`**
- **Purpose**: AI analysis of exceptions for insights and categorization
- **Responsibilities**:
  - Analyze exception patterns and root causes
  - Provide AI-powered exception insights
  - Generate resolution recommendations
- **Used By**: Exception Management Flow, SLA Engine
- **Database Tables**: `exceptions`

#### 3. Financial Services

**`InvoiceGeneratorService`**
- **Purpose**: Generates invoices for completed orders
- **Responsibilities**:
  - Create invoices from order data
  - Calculate billing amounts and adjustments
  - Handle invoice lifecycle management
- **Used By**: Order Processing Flow, Billing Management Flow
- **Database Tables**: `invoices`, `invoice_adjustments`

**`BillingService`**
- **Purpose**: Manages billing operations and validations
- **Responsibilities**:
  - Validate billing data and calculations
  - Process billing adjustments
  - Generate billing reports and metrics
- **Used By**: Billing Management Flow
- **Database Tables**: `invoices`, `invoice_adjustments`

#### 4. Infrastructure Services

**`IdempotencyService`**
- **Purpose**: Ensures operation idempotency across the system
- **Responsibilities**:
  - Track operation execution to prevent duplicates
  - Provide idempotency keys and validation
  - Clean up expired idempotency records
- **Used By**: All flows and services
- **Database Tables**: Redis cache

**`ResilienceManager`**
- **Purpose**: Handles system resilience and error recovery
- **Responsibilities**:
  - Implement retry logic and circuit breakers
  - Handle graceful degradation
  - Manage system health monitoring
- **Used By**: All services
- **Database Tables**: `dlq`

### Flow Layer Architecture

#### 1. Business Operations Orchestrator
- **Purpose**: Master orchestrator for all business processes
- **Responsibilities**:
  - Coordinate execution of all business flows
  - Handle inter-flow dependencies
  - Provide overall business process monitoring
- **Schedule**: Every hour
- **Calls**: All other flows in proper sequence

#### 2. Order Processing Flow
- **Purpose**: End-to-end order processing pipeline
- **Responsibilities**:
  - Monitor order fulfillment progress
  - Manage processing stages and data completeness
  - Detect SLA breaches
  - Generate invoices for completed orders
- **Schedule**: Every 30 minutes
- **Services Used**: ProcessingStageService, DataCompletenessService, SLAEngine, InvoiceGeneratorService

#### 3. Exception Management Flow
- **Purpose**: Proactive exception handling and resolution
- **Responsibilities**:
  - Analyze exception patterns and trends
  - Prioritize exceptions for resolution
  - Execute automated resolution attempts
  - Escalate unresolved exceptions
- **Schedule**: Every 2 hours
- **Services Used**: AIAutomatedResolution, AIExceptionAnalyst, SLAEngine

#### 4. Billing Management Flow
- **Purpose**: Financial operations and billing validation
- **Responsibilities**:
  - Process billing cycles
  - Validate billing data and calculations
  - Generate billing reports
  - Handle billing adjustments
- **Schedule**: Daily at 2 AM
- **Services Used**: BillingService, InvoiceGeneratorService

### Data Flow Architecture

```
Order Events (Webhooks)
    ↓
Order Processing Flow
    ├── ProcessingStageService → order_processing_stages
    ├── DataCompletenessService → data_completeness_checks
    ├── SLAEngine → exceptions
    └── InvoiceGeneratorService → invoices
    
Exception Management Flow
    ├── AIAutomatedResolution → exceptions (resolution tracking)
    ├── AIExceptionAnalyst → exceptions (analysis)
    └── SLAEngine → exceptions (monitoring)
    
Billing Management Flow
    ├── BillingService → invoices, invoice_adjustments
    └── InvoiceGeneratorService → invoices
```

---

## Resolution Tracking System

### Overview

The resolution tracking system prevents repeated failed automation attempts on exception records, addressing the issue where the exception management flow would attempt to resolve ALL exceptions on every run, including those that had already failed multiple times.

### Problem Solved

**Before:** The exception management flow processed all active exceptions without tracking previous attempts, leading to:
- Wasted computational resources on repeatedly failed attempts
- Noise in logs from repeated failures
- No visibility into processing history
- Potential infinite loops on problematic exceptions

**After:** Smart tracking system that:
- Limits resolution attempts per exception (configurable, default: 2)
- Blocks exceptions after max attempts reached
- Provides full visibility into attempt history
- Prevents processing of blocked exceptions

### Database Schema Changes

#### New Fields in `exceptions` Table

```sql
-- Resolution attempt tracking
resolution_attempts INTEGER NOT NULL DEFAULT 0,
max_resolution_attempts INTEGER NOT NULL DEFAULT 2,
last_resolution_attempt_at TIMESTAMP NULL,
resolution_blocked BOOLEAN NOT NULL DEFAULT FALSE,
resolution_block_reason TEXT NULL,

-- New index for efficient querying
CREATE INDEX ix_exceptions_resolution_eligible ON exceptions 
(tenant, status, resolution_attempts, resolution_blocked);
```

### Configuration

#### Environment Variable

```bash
# Set max attempts to 3 (default is 2)
export OCTUP_MAX_RESOLUTION_ATTEMPTS=3

# AI confidence thresholds
AI_MIN_CONFIDENCE=0.7
AI_MIN_SUCCESS_PROBABILITY=0.6
LOW_CONFIDENCE_BLOCK_THRESHOLD=0.3
```

### Model Methods

```python
# Check if exception is eligible for resolution
if exception.is_resolution_eligible:
    # Attempt resolution
    pass

# Increment attempt counter
exception.increment_resolution_attempt()

# Block exception from further attempts
exception.block_resolution("Custom reason")

# Reset tracking (for manual intervention)
exception.reset_resolution_tracking()
```

### Flow Behavior Changes

#### Before Resolution Tracking

```python
# OLD: Processed ALL active exceptions every time
active_exceptions = db.query(ExceptionRecord).filter(
    ExceptionRecord.status.in_(['OPEN', 'IN_PROGRESS'])
).all()

# Result: 174 exceptions processed every run
```

#### After Resolution Tracking

```python
# NEW: Only processes resolution-eligible exceptions
eligible_exceptions = db.query(ExceptionRecord).filter(
    and_(
        ExceptionRecord.status.in_(['OPEN', 'IN_PROGRESS']),
        ExceptionRecord.resolution_blocked == False,
        ExceptionRecord.resolution_attempts < ExceptionRecord.max_resolution_attempts
    )
).all()

# Result: Only new exceptions + those under attempt limit
```

### Blocking Logic

#### Automatic Blocking Conditions

1. **Max Attempts Reached**: After `max_resolution_attempts` failed attempts
2. **Low AI Confidence**: AI confidence < 0.3 (immediate block)
3. **Repeated AI Failures**: Multiple AI analysis failures
4. **Manual Blocking**: Via `block_resolution()` method

#### Block Reasons

- `"Maximum resolution attempts (2) reached"`
- `"AI confidence too low (0.15) - manual review required"`
- `"Repeated AI analysis failures: Connection timeout"`
- Custom reasons via manual blocking

### Performance Impact

#### Database Performance

- **New Index**: Efficient querying of resolution-eligible exceptions
- **Reduced Load**: Fewer exceptions processed per run
- **Better Scaling**: O(new_exceptions) vs O(all_exceptions)

#### Processing Efficiency

**Before:**
- 174 exceptions processed every run
- Repeated AI analysis on same failed cases
- High computational waste

**After:**
- ~20-30 new/eligible exceptions per run
- No repeated processing of blocked exceptions
- 80-85% reduction in unnecessary processing

---

## Data Enrichment Pipeline

### Executive Summary

The Octup E²A data enrichment pipeline provides **systematic AI-powered data processing** with **guaranteed completeness**, **automatic reprocessing**, and **comprehensive monitoring**. This architecture ensures no data is lost in incomplete states and provides full visibility into enrichment health.

### Critical Problems Solved

#### Before: Dangerous Data Inconsistency
- ❌ Records with `ai_confidence = NULL` were abandoned forever
- ❌ No systematic reprocessing of failed AI enrichment
- ❌ Inconsistent enrichment states across different AI services
- ❌ No visibility into data completeness or quality
- ❌ Silent failures in AI processing pipeline

#### After: Bulletproof Data Pipeline
- ✅ **Systematic Reprocessing**: All failed enrichment is automatically retried
- ✅ **State Tracking**: Complete visibility into enrichment progress
- ✅ **Quality Monitoring**: Real-time metrics and alerting
- ✅ **Failure Recovery**: Robust error handling with escalation
- ✅ **Completeness Guarantee**: No records left in incomplete states

### Sequential Enrichment Pipeline

#### Enrichment Stages (Sequential Dependencies)

1. **Order Analysis** (`ai_order_analyzer`)
   - AI-powered order problem detection
   - Replaces hardcoded pattern matching
   - **Input**: Raw order data
   - **Output**: Problem analysis with confidence scores

2. **Exception Classification** (`ai_exception_analyst`)
   - AI classification of exception types
   - Confidence scoring and labeling
   - **Input**: Exception data + order analysis
   - **Output**: `ai_confidence`, `ai_label`, analysis notes

3. **Automated Resolution** (`ai_automated_resolution`)
   - AI-powered resolution possibility analysis
   - Action recommendation and execution
   - **Input**: Classified exceptions with high confidence
   - **Output**: Resolution analysis and automated actions

### Data State Management

#### Enrichment State Tracking

```python
@dataclass
class EnrichmentState:
    record_id: int
    record_type: str  # "exception" or "order"
    
    # Stage completion status
    order_analysis: EnrichmentStatus = PENDING
    classification: EnrichmentStatus = PENDING  
    automation: EnrichmentStatus = PENDING
    
    # Failure tracking
    last_attempt: Optional[datetime] = None
    retry_count: int = 0
    error_messages: List[str] = []
```

#### Status Values
- `PENDING`: Not yet processed
- `IN_PROGRESS`: Currently being processed
- `COMPLETED`: Successfully completed
- `FAILED`: Failed, needs retry
- `SKIPPED`: Skipped due to conditions (e.g., low confidence)

#### NULL Field Handling (Critical)

**When AI Fails:**
```python
# CORRECT: Set fields to NULL for reprocessing
record.ai_confidence = None
record.ai_label = None

# WRONG: Set default values (masks failures)
record.ai_confidence = 0.0  # ❌ Don't do this!
```

**Reprocessing Query:**
```sql
SELECT * FROM exception_records 
WHERE ai_confidence IS NULL 
   OR ai_label IS NULL
   OR (ai_confidence < 0.7 AND updated_at < NOW() - INTERVAL '24 hours');
```

### Reprocessing Workflow

#### Automatic Reprocessing Triggers

1. **Scheduled Pipeline** (every 4 hours)
   - Identifies records needing enrichment
   - Processes in batches with retry logic
   - Updates enrichment state tracking

2. **Failure Detection** (real-time)
   - Monitors AI service responses
   - Detects NULL field returns
   - Queues for immediate reprocessing

3. **Quality Monitoring** (continuous)
   - Tracks enrichment completeness rates
   - Alerts on quality degradation
   - Triggers manual intervention when needed

#### Retry Strategy

```python
# Exponential backoff with jitter
retry_delays = [1min, 5min, 15min, 1hour, 4hours]
max_retries = 5

# Conditions for retry
if (
    ai_confidence is None or 
    ai_label is None or
    (ai_confidence < 0.7 and retry_count < max_retries)
):
    schedule_retry(record, next_delay)
```

---

## Configuration & Environment

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

# Resolution Tracking
OCTUP_MAX_RESOLUTION_ATTEMPTS=2  # Default: 2, configurable

# Prefect Local Server
PREFECT_API_URL=http://localhost:4200/api
PREFECT_WORK_POOL=default-agent-pool
```

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

### Demo System Configuration

```bash
OCTUP_API_URL=http://localhost:8000
WEBHOOK_DELAY_SECONDS=2
SHOPIFY_DEMO_API_PRODUCE_MIN_ORDERS=1001
SHOPIFY_DEMO_API_PRODUCE_MAX_ORDERS=1999
```

---

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

---

## Monitoring & Operations

### Key Metrics

#### 1. Completeness Metrics
- `enrichment_completeness_rate`: % of records fully enriched
- `enrichment_backlog_size`: Number of records awaiting processing
- `enrichment_processing_duration`: Time to process batches

#### 2. Quality Metrics
- `enrichment_quality_score`: Overall quality score (0-100)
- `ai_confidence_distribution`: Distribution of confidence scores
- `enrichment_failure_rate`: % of enrichment attempts that fail

#### 3. Performance Metrics
- `records_processed_per_hour`: Processing throughput
- `average_processing_time`: Time per record
- `pipeline_success_rate`: % of successful pipeline runs

#### 4. Resolution Tracking Metrics
- `resolution_attempt_distribution`: Distribution of attempt counts
- `blocked_exceptions_count`: Number of blocked exceptions
- `automation_success_rate`: % of successful automated resolutions

### Alert Thresholds

```python
thresholds = {
    "completeness_critical": 70.0,    # Below 70% = CRITICAL
    "completeness_warning": 85.0,     # Below 85% = WARNING
    "quality_critical": 60.0,         # Below 60% = CRITICAL
    "quality_warning": 80.0,          # Below 80% = WARNING
    "backlog_critical": 1000,         # >1000 pending = CRITICAL
    "failure_rate_critical": 20.0     # >20% failures = CRITICAL
}
```

### Automated Responses

- **CRITICAL Alerts**: Page on-call engineer, auto-scale processing
- **WARNING Alerts**: Slack notification, increase monitoring frequency
- **INFO Alerts**: Dashboard notification, trend analysis

### Daily Operations

#### Morning Health Check
```bash
# Check enrichment status
curl -X GET /api/enrichment/health/demo-3pl

# Review overnight processing
curl -X GET /api/enrichment/report/demo-3pl

# Check resolution tracking performance
python test_resolution_tracking.py
```

#### Backlog Management
```bash
# Check current backlog
curl -X GET /api/enrichment/backlog/demo-3pl

# Trigger manual processing if needed
curl -X POST /api/enrichment/process/demo-3pl
```

### Database Monitoring Queries

```sql
-- Get resolution statistics
SELECT 
    resolution_attempts,
    COUNT(*) as count
FROM exceptions 
GROUP BY resolution_attempts;

-- Get blocked exceptions
SELECT 
    id, order_id, reason_code, 
    resolution_attempts, resolution_block_reason
FROM exceptions 
WHERE resolution_blocked = true;

-- Get resolution-eligible exceptions
SELECT COUNT(*) as eligible_count
FROM exceptions 
WHERE status IN ('OPEN', 'IN_PROGRESS')
  AND resolution_blocked = false
  AND resolution_attempts < max_resolution_attempts;
```

---

## Deployment & Production

### Docker Deployment

```bash
# Build image
docker build -t octup-e2a .

# Run container
docker run -p 8000:8000 --env-file .env octup-e2a
```

### Kubernetes Deployment

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

### Production Considerations

#### Database Migration

```bash
# Apply resolution tracking migration
python scripts/apply_resolution_tracking.py

# Or manually with Alembic
alembic upgrade head
```

#### Environment Setup

```bash
# Production environment variables
export APP_ENV=production
export OCTUP_MAX_RESOLUTION_ATTEMPTS=3
export AI_MIN_CONFIDENCE=0.7
export LOG_LEVEL=INFO
```

#### Performance Benchmarks

- **Processing Rate**: >100 records/minute
- **Completeness Rate**: >95% within 24 hours
- **Quality Score**: >85 average
- **Failure Rate**: <5% of processing attempts

---

## Troubleshooting

### Common Issues

#### Resolution tracking not working:
```bash
# Check migration applied
python scripts/apply_resolution_tracking.py

# Verify database schema
psql -c "\d exceptions" | grep resolution
```

#### AI service problems:
```bash
# Check circuit breaker status
curl http://localhost:8000/api/circuit-breakers

# Reset if needed
curl -X POST http://localhost:8000/api/circuit-breakers/ai_service/reset
```

#### Database connection issues:
```bash
# Quick health check
curl http://localhost:8000/health

# Check Supabase status
supabase status
```

#### All exceptions are blocked:
- Check if `max_resolution_attempts` is set too low
- Verify migration was applied correctly
- Review blocking logic for bugs

#### Exceptions not being blocked after failures:
- Verify `increment_resolution_attempt()` is being called
- Check database schema has resolution tracking fields
- Review exception processing flow logic

### Performance Monitoring

```bash
# View system statistics
./run.sh stats

# Check resolution tracking performance
python test_resolution_tracking.py

# Monitor Prometheus metrics
curl http://localhost:8000/metrics | grep resolution
```

### Reset Blocked Exceptions

```sql
-- Reset all blocked exceptions (use carefully!)
UPDATE exceptions 
SET resolution_attempts = 0,
    resolution_blocked = false,
    resolution_block_reason = null,
    last_resolution_attempt_at = null
WHERE resolution_blocked = true;
```

### Quality Assurance Checks

#### Data Integrity Validation

```sql
-- No records should be stuck in incomplete states
SELECT COUNT(*) FROM exception_records 
WHERE ai_confidence IS NULL 
  AND created_at < NOW() - INTERVAL '1 day';
-- Should be 0 or very low

-- High confidence rate should be >80%
SELECT 
  COUNT(*) FILTER (WHERE ai_confidence >= 0.7) * 100.0 / COUNT(*) as high_confidence_rate
FROM exception_records 
WHERE ai_confidence IS NOT NULL;

-- No records should exceed max retry count
SELECT COUNT(*) FROM exception_records 
WHERE enrichment_retry_count > 5;
-- Should be 0
```

### Testing

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
python test_resolution_tracking.py
```

---

## Success Metrics

### Business Impact
- **Data Completeness**: 99%+ of records fully enriched
- **Processing Reliability**: 99.9% uptime for enrichment pipeline
- **Quality Consistency**: <2% variance in quality scores
- **Operational Efficiency**: 90% reduction in manual data intervention
- **Resolution Efficiency**: 80-85% reduction in unnecessary processing

### Technical Performance
- **Zero Data Loss**: No records abandoned in incomplete states
- **Automatic Recovery**: 95%+ of failures resolved automatically
- **Monitoring Coverage**: 100% visibility into pipeline health
- **Alert Accuracy**: <1% false positive rate
- **Processing Optimization**: Only new/eligible exceptions processed

---

**Last Updated**: 2025-08-20
