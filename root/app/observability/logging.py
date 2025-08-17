# ==== STRUCTURED JSON LOGGING ==== #

"""
Structured JSON logging with OpenTelemetry integration for Octup E²A.

This module provides comprehensive structured logging with JSON formatting,
correlation ID tracking, tenant isolation, and OpenTelemetry integration
for complete observability across distributed systems.
"""

import json
import logging
import sys
from typing import Any, Dict

from opentelemetry.instrumentation.logging import LoggingInstrumentor


# ==== JSON FORMATTER CLASS ==== #

class JsonFormatter(logging.Formatter):
    """
    JSON formatter for structured logging.
    
    Provides comprehensive JSON log formatting with correlation tracking,
    tenant isolation, exception handling, and OpenTelemetry integration
    for consistent structured logging across all application components.
    """
    
    def format(self, record: logging.LogRecord) -> str:
        """
        Format log record as structured JSON.
        
        Creates comprehensive JSON log entries with timestamp, level,
        correlation tracking, tenant context, and exception details
        for optimal log aggregation and analysis.
        
        Args:
            record (logging.LogRecord): Log record to format
            
        Returns:
            str: JSON formatted log string with complete context
        """
        log_data: Dict[str, Any] = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        # --► CORRELATION ID TRACKING
        if hasattr(record, 'correlation_id'):
            log_data["correlation_id"] = record.correlation_id
            
        # --► TENANT ISOLATION CONTEXT
        if hasattr(record, 'tenant_id'):
            log_data["tenant_id"] = record.tenant_id
            
        # --► EXCEPTION HANDLING
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
            
        # Add extra fields
        for key, value in record.__dict__.items():
            if key not in {
                'name', 'msg', 'args', 'levelname', 'levelno', 'pathname',
                'filename', 'module', 'lineno', 'funcName', 'created',
                'msecs', 'relativeCreated', 'thread', 'threadName',
                'processName', 'process', 'getMessage', 'exc_info',
                'exc_text', 'stack_info', 'correlation_id', 'tenant_id'
            }:
                log_data[key] = value
        
        return json.dumps(log_data, ensure_ascii=False, default=str)


def init_logging(level: str = "INFO") -> None:
    """Initialize structured JSON logging with OpenTelemetry.
    
    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    # Create JSON formatter
    formatter = JsonFormatter()
    
    # Setup console handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    
    # Reduce noise from third-party libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    
    # Initialize OpenTelemetry logging instrumentation
    try:
        LoggingInstrumentor().instrument(set_logging_format=False)
    except Exception as e:
        print(f"Warning: Failed to setup OpenTelemetry logging: {e}")


class ContextualLogger:
    """Logger that automatically includes context from request state."""
    
    def __init__(self, name: str):
        """Initialize contextual logger.
        
        Args:
            name: Logger name (typically __name__)
        """
        self.logger = logging.getLogger(name)
    
    def _add_context(self, extra: Dict[str, Any] | None = None) -> Dict[str, Any]:
        """Add contextual information to log record.
        
        Args:
            extra: Additional fields to include
            
        Returns:
            Dictionary with context fields
        """
        context = extra or {}
        
        # Try to get context from current request (if available)
        try:
            from opentelemetry import trace
            span = trace.get_current_span()
            if span and span.is_recording():
                span_context = span.get_span_context()
                if span_context.is_valid:
                    context['trace_id'] = format(span_context.trace_id, '032x')
                    context['span_id'] = format(span_context.span_id, '016x')
        except Exception:
            pass
            
        return context
    
    def debug(self, msg: str, **kwargs: Any) -> None:
        """Log debug message with context."""
        self.logger.debug(msg, extra=self._add_context(kwargs))
    
    def info(self, msg: str, **kwargs: Any) -> None:
        """Log info message with context."""
        self.logger.info(msg, extra=self._add_context(kwargs))
    
    def warning(self, msg: str, **kwargs: Any) -> None:
        """Log warning message with context."""
        self.logger.warning(msg, extra=self._add_context(kwargs))
    
    def error(self, msg: str, **kwargs: Any) -> None:
        """Log error message with context."""
        self.logger.error(msg, extra=self._add_context(kwargs))
    
    def critical(self, msg: str, **kwargs: Any) -> None:
        """Log critical message with context."""
        self.logger.critical(msg, extra=self._add_context(kwargs))
