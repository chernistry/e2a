# ==== ENHANCED STRUCTURED LOGGING WITH LOGURU ==== #

"""
Enhanced structured logging with loguru for Octup E²A.

This module provides comprehensive structured logging with JSON formatting,
correlation ID tracking, tenant isolation, log rotation, and OpenTelemetry 
integration using loguru for superior developer experience and production features.
"""

import json
import logging
import sys
from typing import Any, Dict
from pathlib import Path

from loguru import logger
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
    """Initialize enhanced structured logging with loguru.
    
    Provides JSON formatting, log rotation, compression, and OpenTelemetry
    integration with superior performance and developer experience.
    
    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    # Remove default loguru handler
    logger.remove()
    
    # Console handler with JSON formatting for production
    logger.add(
        sys.stdout,
        format="{message}",
        serialize=True,  # JSON output
        level=level.upper(),
        enqueue=True,  # Async logging for better performance
        colorize=False,  # Disable colors for JSON logs
        backtrace=True,  # Enhanced exception tracing
        diagnose=True,   # Detailed error context
    )
    
    # File handler with rotation and compression
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)
    
    logger.add(
        logs_dir / "octup_{time:YYYY-MM-DD}.log",
        rotation="100 MB",
        retention="30 days",
        compression="gz",
        serialize=True,  # JSON format for files too
        level="DEBUG",   # More verbose for file logs
        enqueue=True,
        backtrace=True,
        diagnose=True,
    )
    
    # Error-specific log file for critical issues
    logger.add(
        logs_dir / "octup_errors_{time:YYYY-MM-DD}.log",
        rotation="50 MB",
        retention="90 days",  # Keep errors longer
        compression="gz",
        serialize=True,
        level="ERROR",
        enqueue=True,
        backtrace=True,
        diagnose=True,
    )
    
    # Intercept standard logging to route through loguru
    class InterceptHandler(logging.Handler):
        def emit(self, record):
            # Get corresponding Loguru level if it exists
            try:
                level = logger.level(record.levelname).name
            except ValueError:
                level = record.levelno

            # Find caller from where originated the logged message
            frame, depth = logging.currentframe(), 2
            while frame.f_code.co_filename == logging.__file__:
                frame = frame.f_back
                depth += 1

            logger.opt(depth=depth, exception=record.exc_info).log(
                level, record.getMessage()
            )
    
    # Replace standard logging handlers
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
    
    # Reduce noise from third-party libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    
    # Initialize OpenTelemetry logging instrumentation
    try:
        LoggingInstrumentor().instrument(set_logging_format=False)
        logger.info("OpenTelemetry logging instrumentation initialized")
    except Exception as e:
        logger.warning(f"Failed to setup OpenTelemetry logging: {e}")
    
    logger.info("Enhanced structured logging initialized with loguru", 
                level=level, 
                features=["JSON formatting", "log rotation", "compression", "async logging"])


class ContextualLogger:
    """Enhanced logger using loguru with automatic context injection.
    
    Provides structured logging with correlation IDs, tenant isolation,
    OpenTelemetry integration, and enhanced debugging capabilities.
    """
    
    def __init__(self, name: str):
        """Initialize contextual logger.
        
        Args:
            name: Logger name (typically __name__)
        """
        self.name = name
        self.logger = logger.bind(logger_name=name)
    
    def _add_context(self, extra: Dict[str, Any] | None = None) -> Dict[str, Any]:
        """Add contextual information to log record.
        
        Args:
            extra: Additional fields to include
            
        Returns:
            Dictionary with context fields
        """
        context = {"logger_name": self.name}
        
        if extra:
            context.update(extra)
        
        # Try to get OpenTelemetry context
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
        context = self._add_context(kwargs)
        self.logger.bind(**context).debug(msg)
    
    def info(self, msg: str, **kwargs: Any) -> None:
        """Log info message with context."""
        context = self._add_context(kwargs)
        self.logger.bind(**context).info(msg)
    
    def warning(self, msg: str, **kwargs: Any) -> None:
        """Log warning message with context."""
        context = self._add_context(kwargs)
        self.logger.bind(**context).warning(msg)
    
    def error(self, msg: str, **kwargs: Any) -> None:
        """Log error message with context."""
        context = self._add_context(kwargs)
        self.logger.bind(**context).error(msg)
    
    def critical(self, msg: str, **kwargs: Any) -> None:
        """Log critical message with context."""
        context = self._add_context(kwargs)
        self.logger.bind(**context).critical(msg)
    
    def exception(self, msg: str, **kwargs: Any) -> None:
        """Log exception with full traceback and context."""
        context = self._add_context(kwargs)
        self.logger.bind(**context).exception(msg)


# ==== ENHANCED LOGGING UTILITIES ==== #

def get_logger(name: str) -> ContextualLogger:
    """Get a contextual logger instance.
    
    Args:
        name: Logger name (typically __name__)
        
    Returns:
        ContextualLogger instance with enhanced features
    """
    return ContextualLogger(name)


def log_performance(operation: str, duration: float, **context: Any) -> None:
    """Log performance metrics with structured data.
    
    Args:
        operation: Name of the operation
        duration: Duration in seconds
        **context: Additional context fields
    """
    perf_logger = logger.bind(
        operation=operation,
        duration_seconds=round(duration, 3),
        performance_log=True,
        **context
    )
    
    if duration > 10.0:
        perf_logger.warning(f"Slow operation detected: {operation}")
    elif duration > 5.0:
        perf_logger.info(f"Operation completed: {operation}")
    else:
        perf_logger.debug(f"Operation completed: {operation}")


def log_business_event(event_type: str, tenant: str, **context: Any) -> None:
    """Log business events with structured data.
    
    Args:
        event_type: Type of business event
        tenant: Tenant identifier
        **context: Additional business context
    """
    logger.bind(
        event_type=event_type,
        tenant=tenant,
        business_event=True,
        **context
    ).info(f"Business event: {event_type}")


# ==== BACKWARD COMPATIBILITY ==== #

# Keep JsonFormatter for any existing code that might use it directly
class JsonFormatter(logging.Formatter):
    """
    JSON formatter for structured logging (legacy compatibility).
    
    Note: This is maintained for backward compatibility.
    New code should use loguru-based logging directly.
    """
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as structured JSON."""
        log_data: Dict[str, Any] = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        # Add correlation ID tracking
        if hasattr(record, 'correlation_id'):
            log_data["correlation_id"] = record.correlation_id
            
        # Add tenant isolation context
        if hasattr(record, 'tenant_id'):
            log_data["tenant_id"] = record.tenant_id
            
        # Add exception handling
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
