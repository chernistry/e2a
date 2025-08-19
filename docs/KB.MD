# E²A Knowledge Base

**E²A = _Exceptions_ → _Explanations_ → _Actions_**

[![License: CC BY-NC 4.0](https://img.shields.io/badge/License-CC%20BY--NC%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by-nc/4.0/)

Welcome to the E²A Knowledge Base - your comprehensive guide to troubleshooting, performance tuning, and operational excellence. This document covers everything from common issues to advanced scripting and monitoring.

## 📁 Project Structure

```
root/
├── alembic.ini              # Database migration configuration
├── app/                     # Main FastAPI application
│   ├── business/            # Core business logic and policies
│   │   ├── policies/        # SLA and billing configuration files
│   │   └── reason_codes.py  # Exception classification logic
│   ├── integrations/        # External service integrations
│   │   └── slack/           # Slack bot integration with RAG support
│   ├── main.py              # FastAPI application entrypoint
│   ├── middleware/          # Custom request/response middleware
│   ├── observability/       # Logging, metrics, and tracing setup
│   ├── resilience/          # Circuit breakers, retry policies, health monitoring
│   ├── routes/              # API endpoint definitions
│   ├── schemas/             # Pydantic data models
│   ├── security/            # Authentication and authorization
│   ├── services/            # Service-layer logic (AI, SLA, Billing)
│   ├── settings.py          # Application configuration management
│   └── storage/             # Database and cache interaction
├── docker/                  # Docker configurations
├── docs/                    # Documentation including Slack integration guide
├── flows/                   # Prefect business process flow definitions
│   ├── business_operations_orchestrator.py  # Master coordinator
│   ├── order_processing_flow.py            # Order fulfillment monitoring
│   ├── exception_management_flow.py        # Exception analysis & auto-resolution
│   └── billing_management_flow.py          # Invoice generation & validation
├── migrations/              # Alembic database migration scripts
├── scripts/                 # Operational and utility scripts
│   ├── replay_dlq.py        # DLQ recovery script
│   ├── generate_invoices.py # Invoice generation script
│   └── utility/             # Utility scripts
│       └── deploy_flows.py  # Prefect flow deployment
├── tests/                   # Comprehensive test suite
├── demo/                    # Shopify Mock API demo system
├── prefect.yaml             # Prefect deployment configuration
├── run.sh                   # Operational script for common tasks
└── pyproject.toml           # Project dependencies (Poetry)
```

## 🚨 Common Issues & Quick Fixes

### Database Connection Issues
**Symptoms**: Connection timeouts, migration failures, API errors
```bash
# Quick checks
make migrate                    # Apply pending migrations
curl http://localhost:8000/health  # Verify API health
docker logs supabase-db        # Check database logs
```

**Common Causes**:
- Incorrect `DATABASE_URL` in `.env`
- Supabase project paused or down
- Network connectivity issues
- Insufficient connection pool size

### AI Service Problems
**Symptoms**: Timeouts, circuit breaker open, fallback to rule-based analysis
```bash
# Check AI service status
curl http://localhost:8000/api/circuit-breakers
curl http://localhost:8000/api/health

# Reset circuit breaker if needed
curl -X POST http://localhost:8000/api/circuit-breakers/ai_service/reset
```

**Quick Fixes**:
- Verify `AI_API_KEY` in `.env`
- Check OpenRouter API quota usage
- Increase `AI_TIMEOUT_SECONDS` if needed
- System automatically falls back to rule-based analysis

### Dashboard Issues
**Symptoms**: Dashboard not loading, missing data, API errors
```bash
# Verify all services
curl http://localhost:3000     # Dashboard health
curl http://localhost:8000     # API health
curl http://localhost:4200     # Prefect UI
```

**Common Solutions**:
- Restart dashboard: `make dashboard-restart`
- Check API connectivity
- Verify environment variables

### Redis Problems
**Symptoms**: Cache failures, connection errors, performance degradation
```bash
# Check Redis status
docker logs redis
curl http://localhost:8000/api/health
```

**Configuration Tips**:
- Use `rediss://` for SSL connections
- Verify Redis Cloud instance status
- Check SSL certificate configuration

## ⚡ Performance Tuning

### Database Optimization
```bash
# Connection pool tuning
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=30
DATABASE_POOL_PRE_PING=true
DATABASE_POOL_RECYCLE=3600
```

**Performance Tips**:
- Monitor connection pool usage
- Use read replicas for heavy queries
- Implement query result caching
- Regular VACUUM and ANALYZE

### Redis Performance
```bash
# Connection optimization
REDIS_MAX_CONNECTIONS=50
REDIS_SOCKET_KEEPALIVE=True
REDIS_SOCKET_CONNECT_TIMEOUT=5
REDIS_SOCKET_TIMEOUT=5
```

**Best Practices**:
- Use connection pooling
- Implement circuit breakers
- Monitor memory usage
- Set appropriate TTL values

### AI Service Tuning
```bash
# Timeout and retry configuration
AI_TIMEOUT_SECONDS=3
AI_MAX_RETRIES=2
AI_CIRCUIT_BREAKER_FAILURE_THRESHOLD=3
AI_CIRCUIT_BREAKER_RECOVERY_TIMEOUT=30
```

**Optimization Strategies**:
- Batch AI requests when possible
- Implement request caching
- Use appropriate model sizes
- Monitor token usage

### System Resilience
```bash
# Health check configuration
HEALTH_CHECK_INTERVAL=30
HEALTH_CACHE_TTL=30
CIRCUIT_BREAKER_MONITORING=true
```

## 📊 Observability & Monitoring

### Prometheus Metrics

E²A exposes 25+ custom metrics for comprehensive monitoring:

```bash
# View all metrics
curl http://localhost:8000/metrics

# Key business metrics
octup_ingest_success_total{source,event_type,tenant}
octup_sla_breach_count{reason_code,severity,tenant}
octup_ai_requests_total{provider,model,status}
octup_ai_fallback_rate{operation}
octup_cache_hits_total{cache_type}

# System health metrics
octup_circuit_breaker_state_changes_total{service,from_state,to_state}
octup_circuit_breaker_requests_total{service,state,result}
octup_retry_attempts_total{service,operation,attempt}
octup_service_health_status{service,check_type}
octup_overall_system_health
```

### OpenTelemetry Tracing

**Features**:
- Distributed tracing across services
- Correlation IDs for request tracking
- Performance monitoring with latency percentiles
- Error tracking with detailed stack traces

**Configuration**:
```yaml
OTEL_SERVICE_NAME: e2a-platform
OTEL_EXPORTER_OTLP_ENDPOINT: http://otel-collector:4317
OTEL_TRACES_SAMPLER: parentbased_traceidratio
OTEL_TRACES_SAMPLER_ARG: 0.1
```

### Alerting & Notifications

**Recommended Alerts**:
```yaml
# Critical alerts
- API error rate >5% for 5 minutes
- AI service error rate >10% for 5 minutes
- Circuit breaker open for >2 minutes
- Service health degraded for >5 minutes

# Business alerts
- Daily AI token budget >75% consumed
- SLA breach rate >threshold for tenant
- Database connection failures >10/minute
- DLQ depth >100 items for >1 hour
```

## 🔒 Security & Compliance

### Authentication & Authorization

**JWT Configuration**:
```bash
JWT_SECRET_KEY=your-secure-secret
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
```

**API Key Management**:
- Service-to-service authentication
- Multi-tenant isolation
- Rate limiting per endpoint and tenant

### Data Protection

**PII Handling**:
- Automatic redaction before AI processing
- Input validation with Pydantic schemas
- SQL injection prevention
- CORS configuration for web integration

**Production Security Checklist**:
- [ ] Change default JWT secret
- [ ] Enable HTTPS/TLS
- [ ] Configure firewall rules
- [ ] Set up log aggregation
- [ ] Enable audit logging
- [ ] Regular security updates
- [ ] Database encryption at rest
- [ ] Network segmentation

## 🛠️ Operational Scripts

E²A includes operational scripts for maintenance, testing, and data management.

### Core Operational Scripts

#### 🔄 **replay_dlq.py** - DLQ Recovery
Reprocesses failed events from the Dead Letter Queue after bug fixes or system updates.

**Features**:
- Batch processing with configurable sizes
- Automatic event type detection (Shopify, WMS, Carrier)
- Mock request creation for replay
- Comprehensive error handling and statistics
- Progress tracking and reporting

**Usage**:
```bash
cd root/scripts
python replay_dlq.py --batch-size 10 --max-batches 5
```

**Options**:
- `--batch-size`: Items per batch (default: 10)
- `--max-batches`: Maximum batches to process (default: all)

#### 📄 **generate_invoices.py** - Invoice Management
Generates missing invoices for completed orders with comprehensive validation.

**Features**:
- Missing invoice detection and generation
- Tenant-specific backfill operations
- Dry-run mode for testing
- Comprehensive validation and audit logging
- Configurable lookback periods

**Usage**:
```bash
cd root/scripts
python generate_invoices.py --tenant demo-3pl --lookback-hours 168
python generate_invoices.py --backfill --tenant demo-3pl --days-back 30
```

**Options**:
- `--tenant`: Specific tenant to process
- `--lookback-hours`: How far back to look for completed orders (default: 168h = 7 days)
- `--backfill`: Enable backfill mode for historical data
- `--days-back`: Days back for backfill operations (default: 30)
- `--dry-run`: Preview operations without creating invoices

### Utility Scripts

#### 🚀 **deploy_flows.py** - Prefect Flow Management
Manages deployment of Prefect business process workflows to the Prefect server.

**Features**:
- Automatic flow deployment
- Environment-specific configurations
- Health checks and validation
- Rollback capabilities

**Usage**:
```bash
cd root/scripts/utility
python deploy_flows.py
```

### Operational Management Script

#### 🎯 **run.sh** - System Operations
Comprehensive operational script for common system management tasks.

**Features**:
- Service lifecycle management (start, stop, status)
- Event generation and testing
- Database operations (reset, migrations)
- System demonstration and statistics

**Usage**:
```bash
# Service management
./run.sh start          # Start all services
./run.sh stop           # Stop all services
./run.sh status         # Show service status

# Event generation
./run.sh generate single    # Generate one order
./run.sh generate batch     # Generate 1001-1999 orders
./run.sh generate stream 60 # Stream orders for 60 seconds

# System operations
./run.sh demo           # Run system demonstration
./run.sh stats          # Show system statistics
./run.sh reset          # Full database reset (WARNING: deletes ALL data)
```

### Demo System

#### 🎭 **demo/** - Shopify Mock API
Realistic e-commerce testing suite with comprehensive data generation.

**Components**:
- **Shopify Mock API**: Complete API simulation with realistic endpoints
- **Automatic Webhooks**: Real-time integration with E²A platform
- **Exception Simulation**: 13% natural exception rate with realistic scenarios
- **Multi-tenant Support**: Tenant isolation and correlation tracking

**Usage**:
```bash
# Start demo system
cd docker
docker-compose --profile demo up -d

# Access demo API
open http://localhost:8090/docs
```

## 📈 Monitoring & Maintenance

### Health Checks

**Endpoint Monitoring**:
```bash
# System health
curl http://localhost:8000/api/health

# Service status
curl http://localhost:8000/api/degraded

# Circuit breaker status
curl http://localhost:8000/api/circuit-breakers
```

### Log Management

**Log Levels**:
- `DEBUG`: Detailed debugging information
- `INFO`: General operational messages
- `WARNING`: Warning conditions
- `ERROR`: Error conditions
- `CRITICAL`: Critical system failures

**Log Rotation**:
```bash
# Configure log rotation
logrotate /etc/logrotate.d/e2a

# Monitor log sizes
du -sh /var/log/e2a/*
```

### Backup & Recovery

**Database Backups**:
```bash
# Create backup
pg_dump -h localhost -U postgres -d octup > backup.sql

# Restore backup
psql -h localhost -U postgres -d octup < backup.sql
```

**Configuration Backups**:
```bash
# Backup environment files
cp .env .env.backup.$(date +%Y%m%d)

# Backup policies
cp -r app/business/policies/ policies.backup.$(date +%Y%m%d)
```

## 🔄 Automation & Scheduling

### Prefect Business Process Flows

**Current Deployments** (see `prefect.yaml`):
```bash
# Business process flows
prefect deployment run 'order-processing-pipeline/order-processing'
prefect deployment run 'exception-management-pipeline/exception-management'
prefect deployment run 'billing-management-pipeline/billing-management'
prefect deployment run 'business-operations-orchestrator/business-orchestrator'
```

**Flow Descriptions**:
- **Order Processing**: Hourly monitoring of order fulfillment progress and SLA compliance
- **Exception Management**: Every 4 hours analysis and automated resolution of exceptions
- **Billing Management**: Daily invoice generation and validation with adjustments
- **Business Orchestrator**: On-demand coordination of all business processes

### Cron Jobs

**Recommended Schedule**:
```bash
# Manual script execution (if not using Prefect)
0 2 * * * cd /path/to/octup/root/scripts && python generate_invoices.py

# DLQ replay every 4 hours
0 */4 * * * cd /path/to/octup/root/scripts && python replay_dlq.py --batch-size 20

# Health check every 5 minutes
*/5 * * * * curl -f http://localhost:8000/health || echo "API down"

# System statistics (optional)
0 */6 * * * cd /path/to/octup/root && ./run.sh stats
```

### CI/CD Integration

**GitHub Actions Example**:
```yaml
name: E²A Deployment
on:
  push:
    branches: [main]
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Deploy to staging
        run: |
          make deploy-staging
          make health-check
```

## 🚀 Troubleshooting Workflows

### Issue Resolution Process

1. **Identify**: Check logs, metrics, and health endpoints
2. **Isolate**: Determine affected components and scope
3. **Diagnose**: Use debugging tools and scripts
4. **Fix**: Apply appropriate solution
5. **Verify**: Test the fix and monitor recovery
6. **Document**: Update this knowledge base

### Common Debugging Commands

```bash
# Check system status
./run.sh status

# View service logs
make logs
docker logs <service_name>

# Monitor metrics
curl http://localhost:8000/metrics

# Test endpoints
curl http://localhost:8000/health
curl http://localhost:8000/api/health

# System statistics
./run.sh stats

# Generate test data
./run.sh generate batch
```

### Emergency Procedures

**Service Recovery**:
```bash
# Restart all services
./run.sh stop && ./run.sh start

# Restart specific services
make down && make up

# Check service status
./run.sh status
```

**Data Recovery**:
```bash
# Restore from backup
pg_dump -h localhost -U postgres -d octup > backup.sql
psql -h localhost -U postgres -d octup < backup.sql

# Replay failed events
cd scripts && python replay_dlq.py

# Regenerate invoices
cd scripts && python generate_invoices.py --tenant demo-3pl
```

---

**Last Updated**: 2025-08-19  
**Version**: 1.0.0  
**Maintainer**: E²A Team
