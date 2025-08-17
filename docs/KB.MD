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
├── flows/                   # Prefect flow definitions
├── migrations/              # Alembic database migration scripts
├── scripts/                 # Event simulator and utilities
├── tests/                   # Comprehensive test suite
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

E²A includes a comprehensive set of Python scripts for operational tasks, testing, and maintenance.

### Core Operational Scripts

#### 🔧 **validate_fixes.py** - System Validation
Comprehensive validation of the event processing pipeline and fixes.

**Features**:
- Event processing validation
- SLA evaluation testing
- Exception relationship access verification
- DLQ error handling validation
- Current system status reporting

**Usage**:
```bash
cd root/scripts
python validate_fixes.py
```

#### 🔄 **replay_dlq.py** - DLQ Recovery
Reprocesses failed events from the Dead Letter Queue.

**Features**:
- Batch processing with configurable sizes
- Automatic event type detection
- Mock request creation for replay
- Comprehensive error handling
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
Generates missing invoices for completed orders with validation.

**Features**:
- Missing invoice detection
- Tenant-specific backfill operations
- Dry-run mode for testing
- Comprehensive validation
- Configurable lookback periods

**Usage**:
```bash
cd root/scripts
python generate_invoices.py --tenant demo-3pl --lookback-hours 168
python generate_invoices.py --backfill --tenant demo-3pl --days-back 30
```

### Event Simulator Suite

#### 🎭 **event_simulator/** - Advanced Testing
Comprehensive event simulation for API robustness testing.

**Operating Modes**:
```bash
# Realistic simulation (default)
make simulate              # 6 EPS, realistic delays

# Stress testing
make simulate-fast         # 20 EPS, more bursts

# Chaos testing
./run.sh stream chaos      # High error rates, malformed data

# Replay mode
make simulate-replay       # From prepared events
```

**Configuration**:
```yaml
EPS: "6"                    # Events per second
WORKERS: "4"               # Parallel workers
JITTER_MS: "200"           # Random delay ±200ms
BURST_CHANCE: "0.05"       # 5% chance of burst
DUP_RATE: "0.03"           # 3% duplicates
OOO_RATE: "0.02"           # 2% out-of-order
BAD_RATE: "0.01"           # 1% broken events
SEED: "42"                 # For reproducibility
```

**Advanced Chaos Injection**:
- Malformed payloads and encoding issues
- Timestamp anomalies and field corruption
- Size anomalies and nested structures
- SQL injection and XSS payloads

### Utility Scripts

#### 🚀 **deploy_flows.py** - Prefect Management
Manages Prefect workflow deployment and configuration.

**Features**:
- Automatic flow deployment
- Environment-specific configurations
- Health checks and validation
- Rollback capabilities

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

### Cron Jobs

**Recommended Schedule**:
```bash
# Nightly invoice generation (2 AM)
0 2 * * * cd /path/to/octup/root/scripts && python generate_invoices.py

# DLQ replay every 4 hours
0 */4 * * * cd /path/to/octup/root/scripts && python replay_dlq.py --batch-size 20

# Health check every 5 minutes
*/5 * * * * curl -f http://localhost:8000/health || echo "API down"
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
make status

# View service logs
make logs

# Monitor metrics
make metrics

# Test endpoints
make test-api

# Validate fixes
make validate
```

### Emergency Procedures

**Service Recovery**:
```bash
# Restart all services
make restart

# Restart specific service
make restart-api
make restart-dashboard

# Emergency mode (minimal services)
make emergency-mode
```

**Data Recovery**:
```bash
# Restore from backup
make restore-backup

# Replay failed events
make replay-dlq

# Regenerate invoices
make regenerate-invoices
```

---

**Last Updated**: 2025-01-17  
**Version**: 1.0.0  
**Maintainer**: E²A Team
