# ==== OPENTELEMETRY TRACING CONFIGURATION ==== #

"""
OpenTelemetry tracing configuration for hosted APM providers in Octup E²A.

This module provides comprehensive distributed tracing setup with OTLP export,
automatic instrumentation for FastAPI, SQLAlchemy, Redis, and HTTP clients,
and flexible configuration for various APM providers.
"""

import os
from typing import Dict, Any

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor


# ==== TRACING INITIALIZATION ==== #

def init_tracing(service_name: str) -> None:
    """
    Initialize OpenTelemetry tracing with hosted APM provider.
    
    Sets up comprehensive distributed tracing with OTLP export, resource
    attributes, and automatic instrumentation for all major components
    including FastAPI, database, cache, and HTTP clients.
    
    Args:
        service_name (str): Name of the service for tracing identification
    """
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    headers = os.getenv("OTEL_EXPORTER_OTLP_HEADERS")
    
    # ⚠️ Allow local runs without SaaS APM
    if not endpoint:
        return
    
    # --► RESOURCE ATTRIBUTES CONFIGURATION
    resource_attrs = _parse_resource_attributes(
        os.getenv("OTEL_RESOURCE_ATTRIBUTES", "")
    )
    resource_attrs["service.name"] = os.getenv("OTEL_SERVICE_NAME", service_name)
    
    # --► TRACER PROVIDER SETUP
    resource = Resource.create(resource_attrs)
    provider = TracerProvider(resource=resource)
    
    # --► OTLP EXPORTER CONFIGURATION
    exporter = OTLPSpanExporter(
        endpoint=endpoint,
        headers=_parse_headers(headers)
    )
    
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    
    # Auto-instrument common libraries
    _setup_auto_instrumentation()


def _parse_headers(headers_str: str | None) -> Dict[str, str]:
    """Parse OTLP headers from environment variable.
    
    Args:
        headers_str: Comma-separated key=value pairs
        
    Returns:
        Dictionary of headers
    """
    headers = {}
    if not headers_str:
        return headers
        
    for part in headers_str.split(","):
        if "=" in part:
            key, value = part.split("=", 1)
            headers[key.strip()] = value.strip()
    
    return headers


def _parse_resource_attributes(attrs_str: str) -> Dict[str, Any]:
    """Parse OTEL resource attributes from environment variable.
    
    Args:
        attrs_str: Comma-separated key=value pairs
        
    Returns:
        Dictionary of resource attributes
    """
    attrs = {}
    if not attrs_str:
        return attrs
        
    for part in filter(None, map(str.strip, attrs_str.split(","))):
        if "=" in part:
            key, value = part.split("=", 1)
            attrs[key] = value
    
    return attrs


def _setup_auto_instrumentation() -> None:
    """Setup automatic instrumentation for common libraries."""
    try:
        # FastAPI instrumentation will be done in main.py
        SQLAlchemyInstrumentor().instrument()
        RedisInstrumentor().instrument()
        HTTPXClientInstrumentor().instrument()
    except Exception as e:
        # Don't fail startup if instrumentation fails
        print(f"Warning: Failed to setup auto-instrumentation: {e}")


def get_tracer(name: str) -> trace.Tracer:
    """Get a tracer instance for the given module.
    
    Args:
        name: Module name (typically __name__)
        
    Returns:
        Tracer instance
    """
    return trace.get_tracer(name)
