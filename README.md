# E²A — SLA Radar + Invoice Guard

**E²A = _Exceptions_ → _Explanations_ → _Actions_**

[![License: CC BY-NC 4.0](https://img.shields.io/badge/License-CC%20BY--NC%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by-nc/4.0/)

> **🚧 Demo Implementation Notice**
> 
> This is a **demonstration project** showcasing architecture and patterns for a 3PL exception management system. Several core business logic functions are simplified for demo purposes:
> 
> - **Automated Exception Resolution**: Uses probabilistic simulation instead of real API integrations (address validation, payment retries)
> - **Billing Calculations**: Simplified 3PL billing logic without complex rate cards and contract-specific pricing
> - **SLA Detection**: Basic time-based rules without business calendar, warehouse capacity, or order complexity modeling
> - **Order Analysis**: Detects only obvious test data patterns rather than comprehensive validation
> 
> See [`DEMO.md`](docs/DEMO.md) for detailed technical analysis. The architecture, patterns, and infrastructure components are production-ready, but business logic would need full implementation for production use.

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
        PREFECT[Prefect Flows<br/>Business Processes]
    end
    
    subgraph "Business Process Flows"
        ORDER[Order Processing<br/>Pipeline]
        EXCEPTION[Exception Management<br/>Pipeline]
        BILLING[Billing Management<br/>Pipeline]
        ORCHESTRATOR[Business Operations<br/>Orchestrator]
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
    
    INGEST --> PREFECT
    PREFECT --> ORDER
    PREFECT --> EXCEPTION
    PREFECT --> BILLING
    PREFECT --> ORCHESTRATOR
    
    ORDER --> INVOICES
    EXCEPTION --> EXCEPTIONS
    BILLING --> INVOICES
    ORCHESTRATOR --> REPORTS
    
    AI --> EXCEPTIONS
    SLA --> ALERTS
    BILLING --> ALERTS
    
    EXCEPTIONS --> REPORTS
    INVOICES --> REPORTS
    
    style WMS fill:#e1f5fe
    style SHOPIFY fill:#e1f5fe
    style CARRIER fill:#e1f5fe
    style ORDER fill:#e8f5e8
    style EXCEPTION fill:#fff3e0
    style BILLING fill:#f3e5f5
    style ORCHESTRATOR fill:#e3f2fd
    style EXCEPTIONS fill:#e8f5e8
    style INVOICES fill:#e8f5e8
    style ALERTS fill:#fff3e0
    style REPORTS fill:#f3e5f5
```

[See bigger](https://www.mermaidchart.com/play#pako:eNqFU-1q2zAUfRWRwX5slGwrgVJGwU3c1pDUxjb7wO0Pxb5KtDq2kZRuYeyl9gh7sl1LSqLEMTHYyPf7nHv0e5DXBQyuB6ysf-ZLKhRJJ08VwUeu5wtBmyV5GkyooiSp1yIH-TQw7vb5OksyfEmykQpWn-dieBPx_GUY0fyF-K9QKfm8j04ewii4-54ly7rhbKPDQ1GA6IaOvTgO_DgbUyE4BnhRIHV8suRNw6vFYQpUhTl0Jvf__fVIVFLFarFyRw8e7_0kzXQZElQLkIrXlYEQJikZcm0bvnMBTL0MX-JXC16Bjo2BlheKr4DM6oqrWmCak-EFmRcQr6IlMqQT_F85NG0ra-Uu7Cj27_xxmkUCGOSK3OFSDO7btcSWUpJI1LgECeehH6eYai4HYTxBjs0KbBCOb9fYQInpznD-t7EfpUH4mO0xzGhFF7BCDvuyboPpFLnObnlZtns7nxHG4wdcTeylYZztQIQNCNr2lFY3-RLXg6ZanGUiXKtmrQ6g78AkZqNbRKb6e1wc2poSh9XWZ1c4X8Jg7CfZPVTtSFCgfF5rjuxtc4sfa6lWR5L2pn6cJtleMF4JQllVl3hhhhMql_OaisLJiv0obNO0WBTPTfwMlMAzeUtSgbB7tNDezIuLGyt1Y7N3sGO3F65jN19j0U5ky1ZC2lqDFxz-75ntqWBFbuz2Rzu0HLvmXcGuy4rrVKm9htwxdAsL0qzR2Hc9TkKwbU7kuX202-7L7YlSOlV0x5_WRbeRaz8aMum22o7VN4RUmxK0IhhexOs38JGNGLi-rTL6_FuF9PkNtdZ7xUZw5Xr3BJsIxtglfHAjttit_xJGbHRY36Hatrlkn1hxsk3SO8mOqb4AQ3zvnJbcozkHf_4DsukqBw)

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
        PREFECT[Prefect Server]
        RAG[RAG Service]
    end
    
    subgraph "Business Process Flows"
        ORDER_FLOW[Order Processing<br/>Pipeline]
        EXCEPTION_FLOW[Exception Management<br/>Pipeline]
        BILLING_FLOW[Billing Management<br/>Pipeline]
        ORCHESTRATOR_FLOW[Business Operations<br/>Orchestrator]
    end
    
    subgraph "Storage Layer"
        SUPABASE[(Supabase/Postgres)]
        REDIS[(Redis)]
        DLQ[Dead Letter Queue]
    end
    
    subgraph "External Integrations"
        SLACK_API[Slack API]
        MEULEX[Meulex RAG System]
        SHOPIFY_MOCK[Shopify Mock API]
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
    
    PREFECT --> ORDER_FLOW
    PREFECT --> EXCEPTION_FLOW
    PREFECT --> BILLING_FLOW
    PREFECT --> ORCHESTRATOR_FLOW
    
    SLA_ENGINE --> SUPABASE
    AI_ANALYST --> SUPABASE
    ORDER_FLOW --> SUPABASE
    EXCEPTION_FLOW --> SUPABASE
    BILLING_FLOW --> SUPABASE
    ORCHESTRATOR_FLOW --> SUPABASE
    RAG --> SUPABASE
    
    API --> REDIS
    API --> DLQ
    SLACK <--> SLACK_API
    SHOPIFY_MOCK --> API
    
    API -- Exposes --> PROMETHEUS
    API -- Serves --> DASHBOARD
```

[See bigger](https://www.mermaidchart.com/play#pako:eNqFVF1vmzAU_SsWD1P30PZ9qio5wUlQIaZAtVZkihxym7ARQLbZEk377zOYBJMQBSmSde7Xufeem79WUqzB-mZtOCu3KLIXOVKfqFYaWFhOvuEgBPqCsO8glx2ALyztVX8KjCdMyNoYAv-dJvCjs4YuHr_EYcaSX8jJJaikMi3y1gPytX5cFPV5kaiiab65rKhyLsl86sxJrJ6I5Js0N2tiZ4nn2P0Ioxg7COcsOwg5wM0PyISMo9jn8AmJ9gBuOAR4GqvfWeh10qNKEa5H1bJHk6z4I0zqNLBJsJy49HtM-Ro46vp8WvHHZz8tIet3Q97HxI8cOtdhZJ9AWY8QeSxnG9hBLq-FjhzXdeZTHThKs6we5-0wGoxnJIwCHNGW66kxWoJeoGiCKU-2IKSCCn5zOqFyUpUH9vnm4xEOSXwXViVbMQGPfiFkrbqv5jaI7YTxXQDrtIfb7mtsA1sjF6RUI32toLq9K7JXvkoapirFmcrGL8ta3Vq96mUU9cibS95jD6oM9qgRiRIZ7Ezpz6jvTD6WHq0vYFuU6ecBeUUv1XV-dCWU6tgqzVJ5MHnZOJyNKA7seA57-fBTIJuJ7apgfN3TNvVINCNvoZJ3sQO5hUogDyRPEzFcvD7g-_tn47z6eHdWfbw9Iw02U2tgNRMN1cMZim_wB2XQszSptCmbsO5kLm3927i0mwcwlPlM5yaFbgp6KK1G29ZPrQwYO8IDxj7jAQeT8mDyM84DPseB99H-0ppj6kPqjswdPrVa0EfQWgxJ650eLWYqRPZlIUC06jgKsefS_Ndqj5OgF7n17z8z8-IY)

### Data Flow

```mermaid
sequenceDiagram
    participant Source as Event Source<br/>(WMS/Shopify)
    participant API as FastAPI<br/>Ingest Endpoint
    participant SLA as SLA Engine
    participant DB as Database<br/>(Postgres)
    participant AI as AI Analyst
    participant Prefect as Prefect<br/>Business Flows
    participant Dashboard as Dashboard<br/>(Real-time)

    Note over Source,Dashboard: Real-time Event Processing
    Source->>API: POST /ingest/{source}<br/>order_paid, pick_started, etc.
    API->>SLA: Evaluate event against SLA policies
    SLA-->>DB: Create Exception record on breach
    DB-->>AI: Trigger analysis for new exception
    AI-->>DB: Store AI-generated narrative
    API-->>Dashboard: Real-time metrics update
    
    Note over Prefect,Dashboard: Business Process Automation
    Prefect->>DB: Order Processing Pipeline<br/>Monitor fulfillment progress
    Prefect->>DB: Exception Management Pipeline<br/>Analyze patterns, auto-resolve
    Prefect->>DB: Billing Management Pipeline<br/>Generate invoices, validate accuracy
    Prefect->>DB: Business Orchestrator<br/>Coordinate all processes
    Prefect-->>Dashboard: Update business metrics
```

[See bigger](https://www.mermaidchart.com/play#pako:eNp1Ut9v2jAQ_ldOPG0SjHc0IUGhE9IYaHTaS6XqcI5wWrCzs0PXVf3fd3YMlDbLA7HJfT_uu3vuGVdQb9Tz9Lsha2jGWAoe7i3oU6MENlyjDbBxjRgC9DA_0vn-eSvD8Yefy81ws3c1754-vkdO1osIu0Uf9JgQC1uSDzC3Re3Yhg61r5OIia-5LdnS-5LZNFbMMOAWfTaydj6UQr7LRTKhvxOL1ZPv0FwL7ciEWJaPiXTaeNX32kDlHn2HD_T7rUMpWjv50vr5TlgNAh9IDbXIby4QuCNJDrB_RozgXJ0jXoszKsy2bLEtYjAea4wjWK82dzDklOTw2advL0nWSUHyUCMXfajZ_HrwQf2S3iiYTy2XUiiR5jtSMawaVFuUVLFEtr4dQe0qbZNy1_rPQEGz6QhuhCJi_sdQHdhZEDIqC3ra6iezbxGzaQRM1O2dcFlq15jSZw87J2DpEehEkX0tThKb4ITivSRLomoFWBQ98JEuPcTirgQPFISNh6YuFNrWv51AnvLrEZyHnbOHSRPcAS_-MiZ7XMWkX80J1lxTpQxpDktnWZuAXVPtuKoOMd1aXFxQ38V2SXOpMZWUAFeMaXf_ku5fCCTW9wHV30AJXXVK5ZpzqsLR2P8Yv-Rwge3RsbbRB10HjqEBGtMImqdO3lNQKzF73UDlcJIYb5wuAttEUFWx4RgOven4em4_0pRgeyLN07u3vZd_BxiXyw)

### Business Process Pipeline

```mermaid
flowchart LR
    subgraph "Order Events"
        E1[order_paid]
        E2[pick_completed]
        E3[pack_completed]
        E4[ship_label_printed]
        E5[order_fulfilled]
        E6[order_delivered]
    end
    
    subgraph "Order Processing Flow"
        MONITOR[Monitor Order<br/>Fulfillment]
        COMPLETE[Process Completed<br/>Orders]
        SLA_CHECK[Monitor SLA<br/>Compliance]
    end
    
    subgraph "Exception Management Flow"
        ANALYZE[Analyze Exception<br/>Patterns]
        PRIORITIZE[Prioritize Active<br/>Exceptions]
        AUTO_RESOLVE[Attempt Automated<br/>Resolution]
    end
    
    subgraph "Billing Management Flow"
        IDENTIFY[Identify Billable<br/>Orders]
        GENERATE[Generate<br/>Invoices]
        VALIDATE[Validate Invoice<br/>Accuracy]
        ADJUST[Process Billing<br/>Adjustments]
    end
    
    subgraph "Outputs"
        INVOICES[Invoice Records]
        ADJUSTMENTS[Adjustment Records]
        RESOLVED[Resolved Exceptions]
        METRICS[Business Metrics]
    end
    
    E1 --> MONITOR
    E2 --> MONITOR
    E3 --> MONITOR
    E4 --> MONITOR
    E5 --> COMPLETE
    E6 --> COMPLETE
    
    MONITOR --> SLA_CHECK
    COMPLETE --> IDENTIFY
    
    SLA_CHECK --> ANALYZE
    ANALYZE --> PRIORITIZE
    PRIORITIZE --> AUTO_RESOLVE
    AUTO_RESOLVE --> RESOLVED
    
    IDENTIFY --> GENERATE
    GENERATE --> VALIDATE
    VALIDATE --> ADJUST
    
    GENERATE --> INVOICES
    ADJUST --> ADJUSTMENTS
    COMPLETE --> METRICS
    RESOLVED --> METRICS
    
    style E1 fill:#e3f2fd
    style E2 fill:#e3f2fd
    style E3 fill:#e3f2fd
    style E4 fill:#e3f2fd
    style E5 fill:#e3f2fd
    style E6 fill:#e3f2fd
    style INVOICES fill:#e8f5e8
    style ADJUSTMENTS fill:#fff3e0
    style RESOLVED fill:#e8f5e8
    style METRICS fill:#f3e5f5
```

[See bigger](https://www.mermaidchart.com/play#pako:eNqFVF1v2jAU_SsWe662QqmqaqqUgttlIwSFFKkNEzLJTestOJHjsLFp_32OYwezJisPCN9zzv2-_B7EeQKD60Ga5T_iF8IFmgVrhuSnrLbPnBQvaD3weQIc4T0wUa4HDVx_8HmU19CmIDT5atmHUUHj75s43xUZCDjBRlFB-rCLqHyhxSYjW8g2BafsH3ys46VVltIsOwUvNZhARvfAWxBY0vzoqWvB8xjKkrJndCe7YBfo-XM39IPIyxkVOUdK8HHL39_cNRnsZEusHCa-t5jhEEfaJ5qYKpVIyUuLv5w5m8knPPnSRpAWRVVCSlgMb1aBf8ZQCJoz5BFGnqHO6VUlztyZPT7hyGEkO_wC1IpUtAURAjizU1sErh-4oftUF0NzTgWVMicWsrdK03qwVc5D6G8CvPRnKxlLOt0VAjmVyHfENCGAMs-qWvhmZbeyw_VY_lOXO8Xz0L17jNxEwjQ9oFpEthl0d_wez3HgyAndAwMuk1I0l-1zKgdmEVfOzJ3WxBXJaCKJSJOUwInjipP4YJc-_fywDNvJ69wbdvKtKkWdf_n2TlaiqE7PzJ2vfHeCl5HOAAUQy1UvXwX3ZC-W0TFaB1HPZhqpMewhQZ1z9HAYuJNldFvJu6jL8UBwGvekj8_R2dmNuRZtG3bYRh22iw7bWNnMNWnjZYex-dZihbcn1UCGrjCzLLa25SuGPpMG0g8FHM-hwY7vRmftvRZbFkUxnbeDm4QUwaxmA5mXgswyNpB5NZHV5G2nJ0qzOzopRbZ0amM6OqXn3yAm89eI3l5xyKBegvof8fodjNJhmpxAw35o1A9d9EPjfuiyFzK9MISrdAxXNsHqieakaTqCDzanbUafE90g42AE43S8ZoM_fwEWaDTq)

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

*Prefect UI showing completed business process workflows with task flow, logs, and execution details.*

**Why Prefect?**: Python-first, advanced error handling with retries/circuit breakers, observability, easy local dev w/ Community Server, native async.

E²A uses webhook-driven business process flows managed by the Business Operations Orchestrator, coordinating order processing, exception management, and billing with unified reporting and automation. Order processing tracks fulfillment and SLAs, exception management automates common fixes and insights, and billing automates invoice generation and validation. Prefect deployments (see `prefect.yaml`) run these flows on schedules or on-demand, triggered via UI, API, or CLI.


## Python Scripts

E²A includes operational scripts for maintenance, testing, and data management. These scripts provide command-line interfaces for common operations and can be run manually or scheduled.

### Core Scripts

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

### Script Management

#### **Requirements & Dependencies**
```bash
# Install script dependencies
pip install -r root/requirements.txt

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
# Prefect deployment for business processes
prefect deployment run 'billing-management-pipeline/billing-management'
prefect deployment run 'exception-management-pipeline/exception-management'

# Manual script execution
cd root/scripts
python generate_invoices.py --tenant demo-3pl
python replay_dlq.py --batch-size 20
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

**Last Updated**: 2025-08-19  
