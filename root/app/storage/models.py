"""SQLAlchemy models for Octup E²A application."""

import datetime as dt
from typing import Dict, Any, Optional

from sqlalchemy import (
    String, Integer, JSON, ForeignKey, UniqueConstraint, 
    Text, DateTime, Float, Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.storage.db import Base


class Tenant(Base):
    """Tenant configuration and metadata."""
    
    __tablename__ = "tenants"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=True)
    sla_config: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=True)
    billing_config: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, 
        default=dt.datetime.utcnow,
        nullable=False
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime,
        default=dt.datetime.utcnow,
        onupdate=dt.datetime.utcnow,
        nullable=False
    )
    
    # Relationships
    order_events = relationship("OrderEvent", back_populates="tenant_rel")
    exceptions = relationship("ExceptionRecord", back_populates="tenant_rel")


class OrderEvent(Base):
    """Order and warehouse events from various sources."""
    
    __tablename__ = "order_events"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.name"), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    order_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    occurred_at: Mapped[dt.datetime] = mapped_column(DateTime, nullable=False)
    payload: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime,
        default=dt.datetime.utcnow,
        nullable=False
    )
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=True, index=True)
    
    # Constraints
    __table_args__ = (
        UniqueConstraint("tenant", "source", "event_id", name="uq_event"),
        Index("ix_order_events_tenant_order_occurred", "tenant", "order_id", "occurred_at"),
        Index("ix_order_events_tenant_created", "tenant", "created_at"),
    )
    
    # Relationships
    tenant_rel = relationship("Tenant", back_populates="order_events")


class ExceptionRecord(Base):
    """SLA breach exceptions with AI analysis."""
    
    __tablename__ = "exceptions"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.name"), nullable=False, index=True)
    order_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    reason_code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), default="OPEN", nullable=False)
    severity: Mapped[str] = mapped_column(String(16), default="MEDIUM", nullable=False)
    
    # AI analysis fields
    ai_label: Mapped[str] = mapped_column(String(32), nullable=True)
    ai_confidence: Mapped[float] = mapped_column(Float, nullable=True)
    ops_note: Mapped[str] = mapped_column(Text, nullable=True)
    client_note: Mapped[str] = mapped_column(Text, nullable=True)
    
    # Resolution attempt tracking
    resolution_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_resolution_attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    last_resolution_attempt_at: Mapped[dt.datetime] = mapped_column(DateTime, nullable=True)
    resolution_blocked: Mapped[bool] = mapped_column(default=False, nullable=False)
    resolution_block_reason: Mapped[str] = mapped_column(Text, nullable=True)
    
    # Audit fields
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime,
        default=dt.datetime.utcnow,
        nullable=False
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime,
        default=dt.datetime.utcnow,
        onupdate=dt.datetime.utcnow,
        nullable=False
    )
    resolved_at: Mapped[dt.datetime] = mapped_column(DateTime, nullable=True)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=True, index=True)
    
    # Additional context
    context_data: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=True)
    
    # Indexes
    __table_args__ = (
        Index("ix_exceptions_tenant_status", "tenant", "status"),
        Index("ix_exceptions_tenant_reason", "tenant", "reason_code"),
        Index("ix_exceptions_tenant_created", "tenant", "created_at"),
        Index("ix_exceptions_resolution_eligible", "tenant", "status", "resolution_attempts", "resolution_blocked"),
    )
    
    # Relationships
    tenant_rel = relationship("Tenant", back_populates="exceptions")
    
    @property
    def delay_minutes(self) -> Optional[int]:
        """Get delay minutes from context data."""
        if self.context_data and "delay_minutes" in self.context_data:
            return self.context_data["delay_minutes"]
        return None
    
    @property
    def is_resolution_eligible(self) -> bool:
        """Check if exception is eligible for automated resolution attempts."""
        return (
            self.status in ['OPEN', 'IN_PROGRESS'] and
            not self.resolution_blocked and
            self.resolution_attempts < self.max_resolution_attempts
        )
    
    def increment_resolution_attempt(self) -> None:
        """Increment resolution attempt counter and update timestamp."""
        self.resolution_attempts += 1
        self.last_resolution_attempt_at = dt.datetime.utcnow()
        
        # Block further attempts if max reached
        if self.resolution_attempts >= self.max_resolution_attempts:
            self.resolution_blocked = True
            self.resolution_block_reason = f"Maximum resolution attempts ({self.max_resolution_attempts}) reached"
    
    def block_resolution(self, reason: str) -> None:
        """Block this exception from further automated resolution attempts."""
        self.resolution_blocked = True
        self.resolution_block_reason = reason
    
    def reset_resolution_tracking(self) -> None:
        """Reset resolution tracking (useful for manual intervention)."""
        self.resolution_attempts = 0
        self.resolution_blocked = False
        self.resolution_block_reason = None
        self.last_resolution_attempt_at = None


class Invoice(Base):
    """Invoice records for billing validation."""
    
    __tablename__ = "invoices"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.name"), nullable=False, index=True)
    order_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    invoice_number: Mapped[str] = mapped_column(String(64), nullable=True)
    
    # Billing details
    billable_ops: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    
    # Status and dates
    status: Mapped[str] = mapped_column(String(16), default="DRAFT", nullable=False)
    invoice_date: Mapped[dt.datetime] = mapped_column(DateTime, nullable=True)
    due_date: Mapped[dt.datetime] = mapped_column(DateTime, nullable=True)
    
    # Audit fields
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime,
        default=dt.datetime.utcnow,
        nullable=False
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime,
        default=dt.datetime.utcnow,
        onupdate=dt.datetime.utcnow,
        nullable=False
    )
    
    # Relationships
    adjustments = relationship("InvoiceAdjustment", back_populates="invoice")
    
    # Indexes
    __table_args__ = (
        Index("ix_invoices_tenant_status", "tenant", "status"),
        Index("ix_invoices_tenant_created", "tenant", "created_at"),
    )


class InvoiceAdjustment(Base):
    """Invoice adjustments from nightly validation."""
    
    __tablename__ = "invoice_adjustments"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    invoice_id: Mapped[int] = mapped_column(
        Integer, 
        ForeignKey("invoices.id"),
        nullable=False
    )
    tenant: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.name"), nullable=False, index=True)
    
    # Adjustment details
    reason: Mapped[str] = mapped_column(String(64), nullable=False)
    delta_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    
    # AI analysis (if available)
    ai_generated: Mapped[bool] = mapped_column(default=False, nullable=False)
    ai_confidence: Mapped[float] = mapped_column(Float, nullable=True)
    
    # Audit fields
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime,
        default=dt.datetime.utcnow,
        nullable=False
    )
    created_by: Mapped[str] = mapped_column(String(64), default="system", nullable=False)
    
    # Relationships
    invoice = relationship("Invoice", back_populates="adjustments")
    
    # Indexes
    __table_args__ = (
        Index("ix_adjustments_tenant_reason", "tenant", "reason"),
        Index("ix_adjustments_tenant_created", "tenant", "created_at"),
    )


class DLQ(Base):
    """Dead Letter Queue for failed processing."""
    
    __tablename__ = "dlq"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.name"), nullable=False, index=True)
    
    # Error details
    payload: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    error_class: Mapped[str] = mapped_column(String(64), nullable=False)
    error_message: Mapped[str] = mapped_column(Text, nullable=False)
    stack_trace: Mapped[str] = mapped_column(Text, nullable=True)
    
    # Retry tracking
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    next_retry_at: Mapped[dt.datetime] = mapped_column(DateTime, nullable=True)
    
    # Status
    status: Mapped[str] = mapped_column(String(16), default="PENDING", nullable=False)
    
    # Audit fields
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime,
        default=dt.datetime.utcnow,
        nullable=False
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime,
        default=dt.datetime.utcnow,
        onupdate=dt.datetime.utcnow,
        nullable=False
    )
    processed_at: Mapped[dt.datetime] = mapped_column(DateTime, nullable=True)
    
    # Context
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=True, index=True)
    source_operation: Mapped[str] = mapped_column(String(64), nullable=True)
    
    # Indexes
    __table_args__ = (
        Index("ix_dlq_tenant_status", "tenant", "status"),
        Index("ix_dlq_tenant_created", "tenant", "created_at"),
        Index("ix_dlq_next_retry", "next_retry_at"),
    )


# ==== END OF MODELS ==== #
