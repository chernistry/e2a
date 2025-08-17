# ==== PROMETHEUS METRICS ==== #

"""
Prometheus metrics for monitoring application performance in Octup E²A.

This module provides comprehensive application metrics with Prometheus integration
including request tracking, SLA monitoring, AI service metrics, and system
health indicators for complete operational observability.
"""

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse
from prometheus_client import (
    Counter, 
    Gauge, 
    Histogram, 
    generate_latest, 
    REGISTRY
)


# ==== REQUEST METRICS ==== #

ingest_success_total = Counter(
    "octup_ingest_success_total",
    "Total successful event ingests by tenant and source",
    ["tenant", "source", "event_type"]
)

ingest_errors_total = Counter(
    "octup_ingest_errors_total", 
    "Total ingest errors by tenant, source, and error type",
    ["tenant", "source", "error_type"]
)

ingest_latency_seconds = Histogram(
    "octup_ingest_latency_seconds",
    "Event ingest request latency in seconds",
    ["tenant", "source", "event_type"]
)


# ==== SLA MONITORING METRICS ==== #

sla_breach_count = Counter(
    "octup_sla_breach_count",
    "Total SLA breaches detected by tenant and reason code",
    ["tenant", "reason_code"]
)

sla_evaluation_duration_seconds = Histogram(
    "octup_sla_evaluation_duration_seconds",
    "Time spent evaluating SLA rules in seconds",
    ["tenant"]
)

# AI metrics
ai_requests_total = Counter(
    "octup_ai_requests_total",
    "Total AI requests made",
    ["provider", "model", "operation"]
)

ai_tokens_total = Counter(
    "octup_ai_tokens_total",
    "Total AI tokens consumed",
    ["provider", "model", "type"]  # type: prompt, completion
)

ai_cost_cents_total = Counter(
    "octup_ai_cost_cents_total",
    "Total AI cost in cents",
    ["provider", "model"]
)

ai_failures_total = Counter(
    "octup_ai_failures_total",
    "Total AI request failures",
    ["provider", "error_type"]
)

ai_fallback_rate = Gauge(
    "octup_ai_fallback_rate",
    "Rate of AI fallback usage (0.0-1.0)",
    ["operation"]
)

ai_confidence_score = Histogram(
    "octup_ai_confidence_score",
    "AI confidence scores",
    ["operation"],
    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
)

# Cache metrics
cache_hits_total = Counter(
    "octup_cache_hits_total",
    "Total cache hits",
    ["cache_type", "operation"]
)

cache_misses_total = Counter(
    "octup_cache_misses_total",
    "Total cache misses", 
    ["cache_type", "operation"]
)

# DLQ metrics
dlq_depth = Gauge(
    "octup_dlq_depth",
    "Number of items in dead letter queue",
    ["tenant"]
)

dlq_items_total = Counter(
    "octup_dlq_items_total",
    "Total items added to DLQ",
    ["tenant", "error_type"]
)

replay_success_total = Counter(
    "octup_replay_success_total",
    "Total successful replays from DLQ",
    ["tenant"]
)

replay_failures_total = Counter(
    "octup_replay_failures_total",
    "Total failed replays from DLQ",
    ["tenant", "error_type"]
)

# Database metrics
db_connections_active = Gauge(
    "octup_db_connections_active",
    "Number of active database connections"
)

db_query_duration_seconds = Histogram(
    "octup_db_query_duration_seconds",
    "Database query duration in seconds",
    ["operation", "table"]
)

# Business metrics
active_exceptions = Gauge(
    "octup_active_exceptions",
    "Number of open exceptions",
    ["tenant", "reason_code"]
)

invoice_adjustments_total = Counter(
    "octup_invoice_adjustments_total",
    "Total invoice adjustments created",
    ["tenant", "reason"]
)

invoice_adjustment_amount_cents = Histogram(
    "octup_invoice_adjustment_amount_cents",
    "Invoice adjustment amounts in cents",
    ["tenant", "reason"]
)

# System metrics
app_info = Gauge(
    "octup_app_info",
    "Application information",
    ["version", "environment", "service_name"]
)

# Slack integration metrics
SLACK_EVENTS_TOTAL = Counter(
    "octup_slack_events_total",
    "Total Slack events processed",
    ["event_type", "status", "tenant"]
)

slack_notifications_sent_total = Counter(
    "octup_slack_notifications_sent_total",
    "Total Slack notifications sent",
    ["tenant", "channel", "status"]
)

slack_query_duration_seconds = Histogram(
    "octup_slack_query_duration_seconds",
    "Slack query processing duration in seconds",
    ["tenant", "query_type"]
)

slack_rag_confidence_score = Histogram(
    "octup_slack_rag_confidence_score",
    "Slack RAG response confidence scores",
    ["tenant"],
    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
)


def init_metrics(app) -> None:
    """Initialize metrics collection.
    
    Args:
        app: FastAPI application instance
    """
    # Set application info
    from app.settings import settings
    app_info.labels(
        version="0.1.0",
        environment=settings.APP_ENV,
        service_name=settings.SERVICE_NAME
    ).set(1)


# Metrics router for Prometheus scraping
metrics_router = APIRouter()


@metrics_router.get("/metrics")
def get_metrics() -> PlainTextResponse:
    """Expose Prometheus metrics for scraping.
    
    Returns:
        Prometheus metrics in text format
    """
    return PlainTextResponse(
        generate_latest(REGISTRY).decode("utf-8"),
        media_type="text/plain"
    )
