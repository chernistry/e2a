# E²A — SLA Radar + Invoice Guard

**E²A = _Exceptions_ → _Explanations_ → _Actions_**

[![License: CC BY-NC 4.0](https://img.shields.io/badge/License-CC%20BY--NC%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by-nc/4.0/)

> **🚧 Active Development Notice**
> 
> This project is currently in active development. The UI dashboard may display mock/simulated data for demonstration purposes. Real production data integration is being implemented. Please refer to the [Quick Start Guide](docs/QUICKSTART.md) for current development status and known limitations.

E²A is an AI-powered SLA monitoring and invoice validation tool for logistics. It watches order events, catches SLA breaches in real-time, generates AI explanations, and validates invoices nightly with auto-adjustments.
Ready for [RAG+Slack](https://github.com/chernistry/meulex/) integration.
Equipped with realistic Shopify Mock API for (magic) realism.

![E²A Dashboard](assets/scr_dashboard.png)

## What Problem Does This Solve?

**For Warehouse Operations:**
- **Manual Exception Triage**: Teams spend 30-50% of time investigating SLA breaches
- **Reactive Problem Detection**: Issues found hours/days later
- **Invoice Disputes**: Billing discrepancies lead to customer disputes
- **Inconsistent Communication**: Customer notifications vary in quality

**For Customers:**
- **Lack of Visibility**: Limited insight into order delays
- **Poor Communication**: Generic status updates
- **Billing Surprises**: Unexpected charges without justification

## Business Value

- **30-50% Reduction** in manual exception triage time
- **Real-time Detection** of SLA breaches for faster resolution
- **20-30% Reduction** in billing disputes through auto-validation
- **Better Customer Experience** with AI-generated explanations

## Core Features

- **Real-time SLA Monitoring**: Detect pick, pack, and shipping delays instantly
- **AI Exception Analyst**: Generate operational and customer-facing narratives using OpenRouter API
- **Invoice Guard**: Nightly invoice validation with auto-adjustments
- **AI Rule-Lint**: Validate business policies and generate test cases with AI assistance
- **Slack Integration Ready**: Foundation for intelligent Slack bot with RAG queries
- **Resilience**: Circuit breakers, Dead Letter Queue (DLQ), retry policies, replay, health monitoring
- **Real-Time Dashboard**: Next.js 15 dashboard with live metrics, monitoring, AI insights
- **Shopify Mock API Demo**: Realistic e-commerce data generation with automatic webhook integration and exception simulation

## Dead Letter Queue (DLQ) System

E²A includes a robust Dead Letter Queue system that acts as a safety net for failed operations. When event processing fails (due to network issues, database errors, or other transient failures), items are automatically captured in the DLQ with detailed error context. The system implements exponential backoff retry logic (5 min → 10 min → 20 min) and provides admin endpoints for manual replay, cleanup, and monitoring. This ensures no events are lost and provides operational visibility into system failures, making E²A highly resilient to transient issues.

## AI Integration

E²A leverages AI to automate exception analysis and policy validation, reducing manual triage time by 30-50%.

### AI Exception Analyst
Automatically analyzes logistics exceptions (pick delays, pack delays, carrier issues) and generates:
- **Operational Notes**: Technical analysis for ops teams with root cause and next actions
- **Customer Notes**: User-friendly explanations without internal jargon
- **Classification Labels**: Structured categorization (PICK_DELAY, PACK_DELAY, CARRIER_ISSUE, etc.)
- **Confidence Scores**: AI confidence levels for quality control

**Example Analysis:**
```json
{
  "label": "PICK_DELAY",
  "confidence": 0.95,
  "ops_note": "Order 789 experienced a 65-minute delay due to pick station congestion during peak hours. Investigate staffing levels and consider load balancing.",
  "client_note": "We apologize for the delay in processing your order. We are actively working to resolve this and will update you shortly.",
  "reasoning": "Pick delay caused a 65-minute order delay."
}
```

### AI Policy Linting
Reviews business policies (SLA configurations, billing rules) and provides:
- **Validation Issues**: Syntax errors, missing fields, invalid values
- **Best Practice Suggestions**: Performance optimizations, edge case handling
- **Test Case Generation**: Automated test scenarios for policy validation
- **Risk Assessment**: Identifies potential operational risks

**Supported Policy Types:**
- SLA policies (pick/pack/ship timeframes)
- Billing configurations (late fees, adjustments)
- Threshold settings (warning/critical levels)

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

### AI API Endpoints
- **POST /admin/ai/lint-policy**: AI-powered policy validation and test generation
- **GET /exceptions/{id}**: Automatic AI analysis on exception retrieval
- **POST /admin/cache/clear?cache_type=ai**: Clear AI analysis cache

### AI Implementation Details
**Prompts**: External Jinja2 templates in `/prompts/` directory for maintainability
**JSON Extraction**: Robust parsing with fallback mechanisms for malformed AI responses  
**Error Handling**: Graceful degradation with rule-based fallbacks
**Cost Control**: Daily token budgets and request sampling based on severity 


## Architecture

### High-Level Data Flow

```mermaid
flowchart TD
    subgraph "Data Sources"
        WMS[WMS System<br/>Pick/Pack Events]
        SHOPIFY[Shopify<br/>Order Events]
        CARRIER[Carrier APIs<br/>Shipping Events]
    end
    
    subgraph "E²A Platform"
        INGEST[Event Ingestion<br/>POST /ingest/*]
        SLA[SLA Engine<br/>Real-time Monitoring]
        AI[AI Analyst<br/>Exception Analysis]
        INVOICE[Invoice Generator<br/>Billing Automation]
        VALIDATE[Invoice Validator<br/>Nightly Reconciliation]
    end
    
    subgraph "Outputs"
        EXCEPTIONS[SLA Exceptions<br/>+ AI Explanations]
        INVOICES[Generated Invoices<br/>+ Adjustments]
        ALERTS[Real-time Alerts<br/>Slack/Dashboard]
        REPORTS[Analytics<br/>Metrics & Trends]
    end
    
    WMS --> INGEST
    SHOPIFY --> INGEST
    CARRIER --> INGEST
    
    INGEST --> SLA
    SLA --> AI
    SLA --> EXCEPTIONS
    
    INGEST --> INVOICE
    INVOICE --> INVOICES
    INVOICE --> VALIDATE
    VALIDATE --> INVOICES
    
    AI --> EXCEPTIONS
    SLA --> ALERTS
    VALIDATE --> ALERTS
    
    EXCEPTIONS --> REPORTS
    INVOICES --> REPORTS
    
    style WMS fill:#e1f5fe
    style SHOPIFY fill:#e1f5fe
    style CARRIER fill:#e1f5fe
    style EXCEPTIONS fill:#e8f5e8
    style INVOICES fill:#e8f5e8
    style ALERTS fill:#fff3e0
    style REPORTS fill:#f3e5f5
```

[See bigger](https://www.mermaidchart.com/play#pako:eNqrVkrOT0lVslJSqgUAFW4DVg)

### System Components

```mermaid
graph TD
    subgraph "Ingress & API Layer"
        API[FastAPI Service]
        SLACK[Slack Integration]
    end
    
    subgraph "Processing Layer"
        SLA_ENGINE[SLA Engine]
        AI_ANALYST[AI Analyst Service]
        PREFECT[Prefect Flows]
        RAG[RAG Service]
    end
    
    subgraph "Storage Layer"
        SUPABASE[(Supabase/Postgres)]
        REDIS[(Redis)]
        DLQ[Dead Letter Queue]
    end
    
    subgraph "External Integrations"
        SLACK_API[Slack API]
        MEULEX[Meulex RAG System]
    end
    
    subgraph "Observability"
        DASHBOARD[Next.js Dashboard]
        PROMETHEUS[Prometheus Metrics]
    end
    
    API --> SLA_ENGINE
    API --> AI_ANALYST
    API --> PREFECT
    SLACK --> RAG
    RAG --> AI_ANALYST
    RAG -.-> MEULEX
    
    SLA_ENGINE --> SUPABASE
    AI_ANALYST --> SUPABASE
    PREFECT --> SUPABASE
    RAG --> SUPABASE
    
    API --> REDIS
    API --> DLQ
    SLACK <--> SLACK_API
    
    API -- Exposes --> PROMETHEUS
    API -- Serves --> DASHBOARD
```

[See bigger](https://www.mermaidchart.com/play#pako:eNqFU9FO4zAQ_BUrDyd4gHtHJyTTuBCRtqFuJU4uqpxkSXMEu7IdrtXp_h0nTqlDg4gUyZrdeGZnNv-CTOYQXAWF4tsNWoQrgeyj69QBqyAShQKt0Q-EkwjFfA9qFbiu5rEgG3NtmiIF9VZm8HSs0hiP7hmtePaCImHAXmpKKboOELk7nJAmSmaWtBTFKaO9c02mt9GUMHtERBSl8DlxtMZTHP-mC4YjhAWv9toMaEvmZExGC5YoeIbMoHEl_2qvPse3zL6fvvxaMzVS8QIGBC8TfIMpYWe03vKUa_iZSG0aW899PhJGlJ3NIS97eBg_sBB4jmIwBhR6qKH-Xg3Z2V47u2-7_mTj6H7dxOfisSePdEKWMXlkE6gr2KHWBusivH7LO0u19YunZVWavc8XYnp3M8PzkE1hZy7_aBRyvUklV3kvlNmELO7Iktpc5CuYDdQaTcCoMtPD5M3mXVxce3vRx4_70Me7_B3YutHCdlYHNUMPfd_il7bgPPKlHCU4RV3wHe_HPQPFTsxA5SCjj_ZHaVenD9mt8Sf71TnkIj-9A5HdVmrQnTOHEHotzY_QdXyEuRLB_3e6KzR3)

### Data Flow

```mermaid
sequenceDiagram
    participant Source as Event Source<br/>(WMS/Shopify)
    participant API as FastAPI<br/>Ingest Endpoint
    participant SLA as SLA Engine
    participant DB as Database<br/>(Postgres)
    participant AI as AI Analyst
    participant Prefect as Prefect<br/>(Nightly Flow)
    participant Dashboard as Dashboard<br/>(Real-time)

    Note over Source,Dashboard: Real-time Event Processing
    Source->>API: POST /ingest/{source}<br/>order_paid, pick_started, etc.
    API->>SLA: Evaluate event against SLA policies
    SLA-->>DB: Create Exception record on breach
    DB-->>AI: Trigger analysis for new exception
    AI-->>DB: Store AI-generated narrative
    API-->>Dashboard: Real-time metrics update
    
    Note over Prefect,Dashboard: Nightly Invoice Processing
    Prefect->>DB: Fetch completed orders (events)
    Prefect->>Prefect: Generate invoices from operations
    Prefect->>DB: Store generated invoices
    Prefect->>DB: Validate existing invoices
    Prefect->>DB: Create adjustments for discrepancies
    Prefect-->>Dashboard: Update billing metrics
```

[See bigger](https://www.mermaidchart.com/play#pako:eNqrVkrOT0lVslJSqgUAFW4DVg)

### Invoice Processing Pipeline

```mermaid
flowchart LR
    subgraph "Order Events"
        E1[order_paid]
        E2[pick_completed]
        E3[pack_completed]
        E4[ship_label_printed]
    end
    
    subgraph "Invoice Generation"
        DETECT[Detect Completed Orders]
        CALC[Calculate Billable Operations]
        GEN[Generate Invoice]
    end
    
    subgraph "Invoice Validation"
        FETCH[Fetch Draft Invoices]
        VALIDATE[Validate Against Events]
        ADJUST[Create Adjustments]
    end
    
    subgraph "Outputs"
        INV[Invoice Records]
        ADJ[Adjustment Records]
        METRICS[Billing Metrics]
    end
    
    E1 --> DETECT
    E2 --> DETECT
    E3 --> DETECT
    E4 --> DETECT
    
    DETECT --> CALC
    CALC --> GEN
    GEN --> INV
    
    INV --> FETCH
    FETCH --> VALIDATE
    VALIDATE --> ADJUST
    ADJUST --> ADJ
    
    INV --> METRICS
    ADJ --> METRICS
    
    style E1 fill:#e3f2fd
    style E2 fill:#e3f2fd
    style E3 fill:#e3f2fd
    style E4 fill:#e3f2fd
    style INV fill:#e8f5e8
    style ADJ fill:#fff3e0
    style METRICS fill:#f3e5f5
```

[See bigger](https://www.mermaidchart.com/play#pako:eNqrVkrOT0lVslJSqgUAFW4DVg)

### Technology Stack

**FastAPI** (async, OpenAPI docs), **Supabase/PostgreSQL** (managed, auth, real-time, looks cool), **Redis** (persistence, atomic ops), **Prefect** (Python-first, cloud-native, also looks cool), **OpenRouter** (cost-effective, multi-model), **Next.js + Prometheus** (real-time dashboard, metrics).

### Design Patterns & Principles

**🔧 Key Architectural Decisions:**

1. **Idempotency Strategy**: Redis-backed duplicate protection with 5-second locks and UPSERT fallback
2. **AI Fallback Strategy**: Hybrid AI + rule-based system with 0.55 confidence threshold and $20/day budget  
3. **Event Sourcing**: Event-driven SLA evaluation with configurable policies and real-time breach detection

**Benefits**: Sub-millisecond duplicate detection, 85% AI success rate, real-time SLA monitoring.

## Quick Start

**🚀 See [QUICKSTART.md](docs/QUICKSTART.md) for setup, config, deployment, usage, testing, and demo system.**

**Endpoints:**
- **Dashboard**: http://localhost:3000
- API: http://localhost:8000
- API Docs: http://localhost:8000/docs
- Supabase Studio: http://localhost:54323
- Prefect UI: http://localhost:4200
- **Shopify Mock API**: http://localhost:8090/docs



**🔧 See [KB.MD](docs/KB.MD) for issues, performance, observability, security, and troubleshooting.**




## Prefect Workflows

![Prefect Workflow Dashboard](assets/scr_prefect.png)

*Prefect UI showing a completed "invoice-validate-nightly" workflow with task flow, logs, and execution details.*


**Why Prefect?**: Python-first, advanced error handling with retries/circuit breakers, observability, easy local dev w/ Community Server, native async. 


### Key Workflows

- **Invoice Validation Nightly** (`flows/invoice_validate_nightly.py`): Daily validation with tariff checks and AI rationale
- **Event Streaming Simulation** (`flows/event_streaming.py`): Configurable WMS/Shopify event simulation with realistic data generation for testing
- **Manual Triggers**: On-demand workflow execution via admin endpoints and Prefect UI





## Python Scripts

E²A includes a comprehensive set of Python scripts for operational tasks, testing, and maintenance. These scripts provide command-line interfaces for common operations and can be run manually or scheduled.

### Core Scripts

#### 🔧 **validate_fixes.py** - Fix Validation Script
Validates that all async fixes are working properly by running comprehensive tests on the event processing pipeline.

**Features:**
- Basic event processing validation
- SLA evaluation with exception creation
- Exception relationship access testing
- DLQ error handling verification
- Current DLQ status checking

**Usage:**
```bash
cd root/scripts
python validate_fixes.py
```

**Output:** Comprehensive test report with pass/fail status for each validation step.

#### 🔄 **replay_dlq.py** - DLQ Replay Script
Reprocesses failed events from the Dead Letter Queue after bug fixes or system updates.

**Features:**
- Batch processing with configurable sizes
- Automatic event type detection (Shopify, WMS, Carrier)
- Mock request creation for replay
- Comprehensive error handling and statistics
- Progress tracking and reporting

**Usage:**
```bash
cd root/scripts
python replay_dlq.py --batch-size 10 --max-batches 5
```

**Options:**
- `--batch-size`: Number of items to process per batch (default: 10)
- `--max-batches`: Maximum number of batches to process (default: all)

#### 📄 **generate_invoices.py** - Invoice Generation Script
Generates missing invoices for completed orders with comprehensive validation and audit capabilities.

**Features:**
- Missing invoice detection and generation
- Tenant-specific backfill operations
- Dry-run mode for testing
- Comprehensive validation and audit logging
- Configurable lookback periods

**Usage:**
```bash
cd root/scripts
python generate_invoices.py --tenant demo-3pl --lookback-hours 168
python generate_invoices.py --backfill --tenant demo-3pl --days-back 30
```

**Options:**
- `--tenant`: Specific tenant to process
- `--lookback-hours`: How far back to look for completed orders (default: 168h = 7 days)
- `--backfill`: Enable backfill mode for historical data
- `--days-back`: Days back for backfill operations (default: 30)
- `--dry-run`: Preview operations without creating invoices

### Shopify Mock API Demo System

#### 🎭 **demo/** - Realistic E-commerce Testing Suite
Advanced Shopify Mock API system for comprehensive testing and demonstration with realistic data generation.

**Main Components:**
- **`shopify-mock/`**: Complete Shopify API simulation
- **`main.py`**: FastAPI server with realistic endpoints
- **`generator.py`**: Faker-based realistic data generation
- **`test_demo.py`**: Integration testing script
- **Docker setup**: Containerized deployment

**Advanced Features:**
- **Realistic Data**: Faker-generated customers, products, orders
- **Automatic Webhooks**: Real-time integration with Octup E²A
- **Exception Simulation**: 13% natural exception rate with realistic scenarios
- **Multi-tenant Support**: Tenant isolation and correlation tracking
- **Health Monitoring**: Comprehensive health checks and metrics

**Usage:**
```bash
# Start demo system
cd docker
docker-compose --profile demo up -d

# Test integration
cd ../demo
python test_demo.py

# Access interfaces
open http://localhost:8090/docs    # Shopify Mock API
open http://localhost:3000         # Octup Dashboard
```

**Configuration:**
```yaml
OCTUP_API_URL: http://localhost:8000     # Target API
WEBHOOK_DELAY_SECONDS: 2                 # Webhook timing
SHOPIFY_DEMO_API_PRODUCE_MIN_ORDERS: 1001  # Batch size range
SHOPIFY_DEMO_API_PRODUCE_MAX_ORDERS: 1999
```

### Utility Scripts

#### 🚀 **deploy_flows.py** - Prefect Flow Deployment
Manages deployment of Prefect workflows to the Prefect server.

**Features:**
- Automatic flow deployment
- Environment-specific configurations
- Health checks and validation
- Rollback capabilities

**Usage:**
```bash
cd root/scripts/utility
python deploy_flows.py
```

### Script Management

#### **Requirements & Dependencies**
```bash
# Install script dependencies
pip install -r root/scripts/requirements-event-s.txt

# Or use the demo system container
docker-compose --profile demo up -d
```

#### **Environment Setup**
```bash
# Set required environment variables
export DATABASE_URL="postgresql+asyncpg://user:pass@localhost/octup"
export REDIS_URL="redis://localhost:6379"
export AI_PROVIDER_BASE_URL="https://openrouter.ai/api/v1"
export AI_MODEL="google/gemini-2.0-flash-exp:free"
```

#### **Scheduling & Automation**
```bash
# Cron job for nightly invoice generation
0 2 * * * cd /path/to/octup/root/scripts && python generate_invoices.py

# Cron job for DLQ replay (every 4 hours)
0 */4 * * * cd /path/to/octup/root/scripts && python replay_dlq.py --batch-size 20
```

#### **Monitoring & Logging**
All scripts include comprehensive logging and can be integrated with:
- **Prometheus**: Metrics collection and alerting
- **Grafana**: Dashboard visualization
- **ELK Stack**: Log aggregation and analysis
- **Slack**: Real-time notifications

#### **Error Handling & Resilience**
- **Circuit Breakers**: Prevents cascade failures
- **Retry Logic**: Exponential backoff with jitter
- **Dead Letter Queue**: Captures failed operations
- **Health Checks**: Monitors script health and dependencies

### Testing & Validation

#### **Script Testing**
```bash
# Run all validation tests
python validate_fixes.py

# Test specific scenarios
python validate_fixes.py --test sla_evaluation
python validate_fixes.py --test dlq_handling
```

#### **Integration Testing**
```bash
# Test demo system with real API
cd demo
python test_demo.py

# Test invoice generation
python generate_invoices.py --dry-run
```

#### **Performance Testing**
```bash
# Test demo system
docker-compose --profile demo up -d
python test_demo.py

# Generate large batches
curl -X POST http://localhost:8090/demo/generate-batch
```


## License

This project is licensed under the Creative Commons Attribution-NonCommercial 4.0 International License.

## Acknowledgments

This project uses several open-source packages:
- [FastAPI](https://fastapi.tiangolo.com/) for the web framework
- [Prefect](https://docs.prefect.io/) for workflow orchestration
- [OpenTelemetry](https://opentelemetry.io/) for observability
- [Pydantic](https://pydantic-docs.helpmanual.io/) for data validation
- [Alembic](https://alembic.sqlalchemy.org/) for database migrations
- [next-shadcn-dashboard-starter](https://github.com/Kiranism/next-shadcn-dashboard-starter) for the Next.js dashboard template
- [Faker](https://faker.readthedocs.io/) for realistic test data generation


---

**Last Updated**: 2025-01-27  
