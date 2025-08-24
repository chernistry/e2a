# E²A — SLA Radar + Invoice Guard

**E²A = _Exceptions_ → _Explanations_ → _Actions_**

[![License: CC BY-NC 4.0](https://img.shields.io/badge/License-CC%20BY--NC%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by-nc/4.0/)

> **🚧 Demo Implementation Notice**
> 
> This is a **demonstration project** showcasing architecture and patterns for a 3PL exception management system. Several core business logic functions are simplified for demo purposes including billing calculations, SLA detection, and AI PII handling.
> 
> **📖 Documentation**: See [**DEMO.md**](docs/DEMO.md) for demo limitations and [**KB.MD**](docs/KB.MD) for complete technical documentation.

E²A is an AI-powered SLA monitoring and invoice validation tool for logistics. It watches order events, catches SLA breaches in real-time, generates AI explanations, and validates invoices nightly with auto-adjustments.
Includes foundation for Slack integration and realistic Shopify Mock API for demonstration.

![E²A Dashboard](assets/scr_dashboard.png)

## What Problem Does This Solve?

**For Warehouse Operations:**
- **Manual Exception Triage**: Teams spend significant time investigating SLA breaches
- **Reactive Problem Detection**: Issues often found hours/days later
- **Invoice Disputes**: Billing discrepancies can lead to customer disputes
- **Inconsistent Communication**: Customer notifications may vary in quality

**For Customers:**
- **Lack of Visibility**: Limited insight into order delays
- **Poor Communication**: Generic status updates
- **Billing Surprises**: Unexpected charges without justification

## Business Value

- **Designed to reduce** manual exception triage time
- **Real-time Detection** of SLA breaches for faster resolution
- **Automated invoice validation** to reduce billing disputes
- **Improved Customer Experience** with AI-generated explanations

## Core Features

- **Real-time SLA Monitoring**: Detect pick, pack, and shipping delays instantly
- **AI Exception Analyst**: Generate operational and customer-facing narratives using OpenRouter API
- **AI Automated Resolution**: Intelligent automation of common exceptions (payment retries, address validation, inventory reallocation) with confidence-based decision making
- **Invoice Guard**: Nightly invoice validation with auto-adjustments
- **AI Rule-Lint**: Validate business policies and generate test cases with AI assistance
- **Slack Integration Foundation**: Basic Slack bot framework with webhook handling and query processing
- **RAG Service Foundation**: Placeholder RAG service ready for vector database integration (compatible with [Meulex](https://github.com/chernistry/meulex/) RAG stack)
- **Resilience**: Circuit breakers, Dead Letter Queue (DLQ), retry policies, replay, health monitoring
- **Real-Time Dashboard**: Next.js 15 dashboard with live metrics, monitoring, AI insights
- **Shopify Mock API Demo**: Realistic e-commerce data generation with automatic webhook integration and exception simulation

## Dead Letter Queue (DLQ) System

E²A includes a robust Dead Letter Queue system that acts as a safety net for failed operations. When event processing fails (due to network issues, database errors, or other transient failures), items are automatically captured in the DLQ with detailed error context. The system implements exponential backoff retry logic (5 min → 10 min → 20 min) and provides admin endpoints for manual replay, cleanup, and monitoring. This ensures no events are lost and provides operational visibility into system failures, making E²A highly resilient to transient issues.

## AI Integration

E²A integrates AI to assist with exception analysis, automated resolution, and policy validation, designed to reduce manual triage time and automate common operational tasks.

### AI Exception Analyst
Analyzes logistics exceptions and generates:
- **Operational Notes**: Analysis for ops teams based on available data
- **Customer Notes**: User-friendly explanations without internal jargon
- **Classification Labels**: Structured categorization (PICK_DELAY, PACK_DELAY, CARRIER_ISSUE, etc.)
- **Confidence Scores**: AI confidence levels for quality control

**Example Analysis:**
```json
{
  "label": "PICK_DELAY",
  "confidence": 0.85,
  "ops_note": "Order experienced a 60-minute delay during peak hours. Pattern suggests potential capacity constraints during afternoon rush.",
  "client_note": "Your order is taking longer than expected due to high volume. We're prioritizing it and will update you shortly.",
  "reasoning": "Timing and delay percentage indicate potential capacity issue"
}
```

### AI Automated Resolution 
Intelligently analyzes raw order data to determine if exceptions can be automatically resolved without human intervention.
**Supported Automation Actions:** Includes stubs for payment retry with exponential backoff, address validation and postal code correction, inventory reallocation between warehouses, automated system health checks and recovery, and carrier API status synchronization.

**Example Automated Resolution:**
```json
{
  "can_auto_resolve": true,
  "confidence": 0.95,
  "automated_actions": ["payment_retry"],
  "resolution_strategy": "Retry payment with exponential backoff",
  "success_probability": 0.8,
  "reasoning": "Payment failure appears transient based on error code and timing"
}
```

### AI Policy Linting
Reviews business policies (SLA configurations, billing rules) and provides:
- **Validation Issues**: Syntax errors, missing fields, invalid values
- **Best Practice Suggestions**: Optimization recommendations and edge case handling
- **Test Case Generation**: Suggested test scenarios for policy validation
- **Risk Assessment**: Identifies potential operational considerations

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


### AI Implementation Details
**Prompts**: External Jinja2 templates in `/prompts/` directory for maintainability
**JSON Extraction**: Robust parsing with fallback mechanisms for malformed AI responses  
**Error Handling**: Graceful degradation with rule-based fallbacks
**Cost Control**: Daily token budgets and request sampling based on severity 
**RAG Integration**: Foundation compatible with vector databases (Qdrant, Pinecone) and RAG frameworks like [Meulex](https://github.com/chernistry/meulex/) for enhanced Slack bot capabilities 


## Architecture

**🚧 Current Implementation Status**: 
- ✅ **Shopify Mock API**: Fully functional with realistic order generation and webhook integration
- ✅ **Order Analysis**: AI-powered problem detection with rule-based fallback working end-to-end
- ✅ **Exception Management**: Complete pipeline from detection to AI analysis and resolution tracking
- 🔄 **WMS/Carrier Integration**: Schemas and endpoints ready, awaiting real system integration
- ✅ **Prefect Orchestration**: Simplified 2-flow architecture deployed and running (Event Processor: 15min, Business Operations: Daily)
- ✅ **Real-time Dashboard**: Live metrics and monitoring with WebSocket updates
- ✅ **Architecture Simplification**: Consolidated from 5 flows to 2 flows with 60%+ complexity reduction and 40%+ performance improvement

### High-Level Data Flow

```mermaid
flowchart TD
    subgraph "Data Sources"
        SHOPIFY_MOCK[Shopify Mock API<br/>Demo Order Events]
        WMS[WMS System<br/>Pick/Pack Events<br/>Schema Ready]
        CARRIER[Carrier APIs<br/>Shipping Events<br/>Schema Ready]
    end
    
    subgraph "E²A Platform"
        INGEST[Event Ingestion<br/>POST /ingest/events<br/>Idempotency + DLQ]
        EVENT_PROCESSOR[Event Processor Flow<br/>15min intervals<br/>Order Analysis + AI + SLA]
        BUSINESS_OPS[Business Operations Flow<br/>Daily intervals<br/>Billing + Reporting]
    end
    
    subgraph "Outputs"
        EXCEPTIONS[Exception Records<br/>+ AI Analysis]
        INVOICES[Generated Invoices<br/>+ Adjustments]
        DASHBOARD[Real-time Dashboard<br/>Live Metrics]
        REPORTS[Business Analytics<br/>Metrics & Trends]
    end
    
    SHOPIFY_MOCK --> INGEST
    WMS --> INGEST
    CARRIER --> INGEST
    
    INGEST --> EVENT_PROCESSOR
    EVENT_PROCESSOR --> EXCEPTIONS
    EVENT_PROCESSOR --> BUSINESS_OPS
    BUSINESS_OPS --> INVOICES
    BUSINESS_OPS --> REPORTS
    
    EXCEPTIONS --> DASHBOARD
    INVOICES --> DASHBOARD
    REPORTS --> DASHBOARD
    
    style SHOPIFY_MOCK fill:#4caf50
    style WMS fill:#e1f5fe
    style CARRIER fill:#e1f5fe
    style EVENT_PROCESSOR fill:#e8f5e8
    style BUSINESS_OPS fill:#f3e5f5
    style EXCEPTIONS fill:#e8f5e8
    style INVOICES fill:#e8f5e8
    style DASHBOARD fill:#fff3e0
    style REPORTS fill:#f3e5f5
```

### System Components

```mermaid
graph TD
    subgraph "Ingress & API Layer"
        API[FastAPI Service<br/>Port 8000]
        DASHBOARD_UI[Next.js Dashboard<br/>Port 3000]
    end
    
    subgraph "Processing Layer"
        ORDER_ANALYZER[Order Analyzer Service<br/>AI + Rule-based Detection]
        SLA_ENGINE[SLA Engine<br/>Real-time Breach Detection]
        AI_ANALYST[AI Exception Analyst<br/>OpenRouter Integration]
        AI_RESOLUTION[AI Automated Resolution<br/>Smart Resolution Attempts]
        PREFECT_SERVER[Prefect Server<br/>Port 4200]
    end
    
    subgraph "Prefect Flows (Simplified Architecture)"
        EVENT_FLOW[Event Processor Flow<br/>15min intervals<br/>Order Analysis + AI + SLA]
        BUSINESS_FLOW[Business Operations Flow<br/>Daily intervals<br/>Billing + Reporting]
    end
    
    subgraph "Storage Layer"
        SUPABASE[(Supabase/PostgreSQL<br/>Port 54322)]
        REDIS[(Redis<br/>Caching & Sessions)]
        DLQ[Dead Letter Queue<br/>Failed Event Recovery]
    end
    
    subgraph "External Integrations"
        SHOPIFY_MOCK[Shopify Mock API<br/>Port 8090<br/>Demo Data Generator]
        OPENROUTER[OpenRouter API<br/>AI Model Access]
    end
    
    subgraph "Observability"
        PROMETHEUS[Prometheus Metrics<br/>Performance Monitoring]
        SUPABASE_STUDIO[Supabase Studio<br/>Port 54323<br/>Database Management]
    end
    
    API --> ORDER_ANALYZER
    API --> SLA_ENGINE
    API --> AI_ANALYST
    API --> AI_RESOLUTION
    
    PREFECT_SERVER --> EVENT_FLOW
    PREFECT_SERVER --> BUSINESS_FLOW
    
    EVENT_FLOW --> ORDER_ANALYZER
    EVENT_FLOW --> SLA_ENGINE
    EVENT_FLOW --> AI_ANALYST
    EVENT_FLOW --> AI_RESOLUTION
    EVENT_FLOW --> SUPABASE
    
    BUSINESS_FLOW --> SUPABASE
    
    API --> REDIS
    API --> DLQ
    API --> SUPABASE
    SHOPIFY_MOCK --> API
    AI_ANALYST --> OPENROUTER
    AI_RESOLUTION --> OPENROUTER
    
    API --> PROMETHEUS
    DASHBOARD_UI --> API
    SUPABASE --> SUPABASE_STUDIO
```

### Data Flow

```mermaid
sequenceDiagram
    participant Source as Shopify Mock API<br/>(Demo Events)
    participant API as FastAPI<br/>Ingest Endpoint
    participant Redis as Redis<br/>(Idempotency)
    participant DB as Database<br/>(Supabase)
    participant EventFlow as Event Processor Flow<br/>(15min intervals)
    participant AI as AI Services<br/>(Circuit Breaker)
    participant BusinessFlow as Business Operations Flow<br/>(Daily)
    participant Dashboard as Dashboard<br/>(Real-time)

    Note over Source,Dashboard: Event Ingestion & Async Processing
    Source->>API: POST /ingest/events<br/>order_created with problems
    API->>Redis: Check idempotency
    Redis-->>API: Not processed
    API->>DB: Store OrderEvent record
    API-->>Source: 200 OK (fast response)
    
    Note over EventFlow,Dashboard: Background Processing (15min intervals)
    EventFlow->>DB: Query recent OrderEvents
    EventFlow->>EventFlow: Analyze orders for problems
    EventFlow->>DB: Create ExceptionRecords
    EventFlow->>AI: Analyze exceptions (with circuit breaker)
    AI-->>EventFlow: AI analysis results
    EventFlow->>DB: Update exceptions with AI analysis
    EventFlow->>EventFlow: Evaluate SLA breaches
    EventFlow->>DB: Create SLA exceptions
    EventFlow-->>Dashboard: Real-time metrics update
    
    Note over BusinessFlow,Dashboard: Daily Business Operations
    BusinessFlow->>DB: Monitor order fulfillment
    BusinessFlow->>DB: Generate invoices for completed orders
    BusinessFlow->>DB: Validate billing accuracy
    BusinessFlow->>DB: Process adjustments
    BusinessFlow-->>Dashboard: Business metrics update
```

### Business Process Pipeline

```mermaid
flowchart LR
    subgraph "Event Sources"
        E1[order_created<br/>with problems]
        E2[order_paid]
        E3[pick_completed]
        E4[pack_completed]
        E5[ship_label_printed]
        E6[order_fulfilled]
        E7[order_delivered]
    end
    
    subgraph "Event Processor Flow (15min intervals)"
        MONITOR[Monitor Recent<br/>Order Events]
        ANALYZE[Analyze Orders<br/>for Problems]
        SLA_CHECK[Evaluate SLA<br/>Breaches]
        AI_ANALYSIS[AI Exception<br/>Analysis with Circuit Breaker]
        RESOLUTION[Attempt Automated<br/>Resolution]
    end
    
    subgraph "Business Operations Flow (Daily)"
        FULFILLMENT[Monitor Order<br/>Fulfillment Progress]
        BILLING[Generate Invoice<br/>Records]
        VALIDATE[Validate Invoice<br/>Accuracy]
        ADJUST[Process Billing<br/>Adjustments]
        REPORTS[Generate Business<br/>Analytics]
    end
    
    subgraph "Outputs"
        EXCEPTIONS[Exception Records<br/>with AI Analysis]
        INVOICES[Invoice Records<br/>with Adjustments]
        ANALYTICS[Business Metrics<br/>& Reports]
        ALERTS[Real-time Alerts<br/>& Notifications]
    end
    
    E1 --> MONITOR
    E2 --> MONITOR
    E3 --> MONITOR
    E4 --> MONITOR
    E5 --> MONITOR
    E6 --> FULFILLMENT
    E7 --> FULFILLMENT
    
    MONITOR --> ANALYZE
    ANALYZE --> SLA_CHECK
    SLA_CHECK --> AI_ANALYSIS
    AI_ANALYSIS --> RESOLUTION
    RESOLUTION --> EXCEPTIONS
    
    FULFILLMENT --> BILLING
    BILLING --> VALIDATE
    VALIDATE --> ADJUST
    ADJUST --> INVOICES
    REPORTS --> ANALYTICS
    
    EXCEPTIONS --> ALERTS
    EXCEPTIONS --> ANALYTICS
    INVOICES --> ANALYTICS
    
    style E1 fill:#4caf50
    style E2 fill:#e3f2fd
    style E3 fill:#e3f2fd
    style E4 fill:#e3f2fd
    style E5 fill:#e3f2fd
    style E6 fill:#e3f2fd
    style E7 fill:#e3f2fd
    style EXCEPTIONS fill:#e8f5e8
    style INVOICES fill:#e8f5e8
    style ANALYTICS fill:#f3e5f5
    style ALERTS fill:#fff3e0
```

### Technology Stack

**FastAPI** (async, OpenAPI docs), **Supabase/PostgreSQL** (managed, auth, real-time, looks cool), **Redis** (persistence, atomic ops), **Prefect** (Python-first, cloud-native, also looks cool), **OpenRouter** (cost-effective, multi-model), **Next.js + Prometheus** (real-time dashboard, metrics).

### Design Patterns & Principles

**🔧 Key Architectural Decisions:**

1. **Idempotency Strategy**: Redis-backed duplicate protection with 5-second locks and UPSERT fallback
2. **AI Fallback Strategy**: Hybrid AI + rule-based system with 0.55 confidence threshold and $20/day budget  
3. **Event Sourcing**: Event-driven SLA evaluation with configurable policies and real-time breach detection

**Benefits**: Fast duplicate detection, AI-assisted analysis, real-time SLA monitoring.

## Quick Start

**📖 Complete Setup Guide**: See [**KB.MD**](docs/KB.MD) for detailed setup, configuration, deployment, usage, testing, and demo system instructions.

**Key Endpoints:**
- **Dashboard**: http://localhost:3000
- **API**: http://localhost:8000 | **API Docs**: http://localhost:8000/docs
- **Supabase Studio**: http://localhost:54323 | **Prefect UI**: http://localhost:4200
- **Shopify Mock API**: http://localhost:8090 | **Mock API Docs**: http://localhost:8090/docs

**🔧 Advanced Topics**: See [**KB.MD**](docs/KB.MD) for troubleshooting, performance tuning, monitoring, and production deployment.

## Prefect Workflows

![Prefect Workflow Dashboard](assets/scr_prefect.png)

*Prefect UI showing completed business process workflows with task flow, logs, and execution details.*

**Why Prefect?**: Python-first, advanced error handling with retries/circuit breakers, observability, easy local dev w/ Community Server, native async.

E²A uses a **simplified 2-flow architecture** after consolidating from 5 fragmented flows for better performance and maintainability:

- **Event Processor Flow** (15min intervals): Monitors recent order events, analyzes orders for problems using AI + rule-based detection, evaluates SLA breaches in real-time, creates exception records with AI analysis, and attempts automated resolution with circuit breaker protection
- **Business Operations Flow** (Daily): Monitors order fulfillment progress, identifies billable operations, generates invoice records, validates billing accuracy with AI assistance, processes billing adjustments, and generates business intelligence reports

**Key Improvements from Consolidation**:
- **60%+ reduction** in orchestration complexity 
- **40%+ improvement** in processing performance
- **Prefect-native** retry mechanisms replace custom state tracking
- **Async AI processing** improves ingestion throughput
- **Circuit breaker patterns** for AI service resilience

Prefect deployments run these flows on schedules or on-demand via UI, API, or CLI with comprehensive error handling and retry logic.

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

**Last Updated**: 2025-08-24  
