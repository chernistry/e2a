"""Database seeder for demo data."""

import asyncio
import datetime as dt
from typing import List

from sqlalchemy import select

from app.storage.db import get_session
from app.storage.models import Tenant, OrderEvent, Invoice, ExceptionRecord
from app.observability.logging import ContextualLogger


logger = ContextualLogger(__name__)


async def seed_demo_data() -> None:
    """Seed database with demo data for testing and development."""
    logger.info("Starting database seeding")
    
    async with get_session() as db:
        # Check if data already exists
        existing_tenants = await db.execute(select(Tenant))
        if existing_tenants.scalars().first():
            logger.info("Demo data already exists, skipping seeding")
            return
        
        # Create demo tenant
        await _create_demo_tenant(db)
        
        # Create demo order events
        await _create_demo_order_events(db)
        
        # Create demo invoices
        await _create_demo_invoices(db)
        
        # Commit all changes
        await db.commit()
        
        logger.info("Database seeding completed successfully")


async def _create_demo_tenant(db) -> None:
    """Create demo tenant with SLA and billing configuration."""
    logger.info("Creating demo tenant")
    
    tenant = Tenant(
        name="demo-3pl",
        display_name="Demo 3PL Warehouse",
        sla_config={
            "pick_minutes": 120,
            "pack_minutes": 180,
            "ship_minutes": 1440,
            "weekend_multiplier": 1.5,
            "holiday_multiplier": 2.0
        },
        billing_config={
            "pick_fee_cents": 30,
            "pack_fee_cents": 20,
            "label_fee_cents": 15,
            "min_order_fee_cents": 50
        }
    )
    
    db.add(tenant)
    await db.flush()


async def _create_demo_order_events(db) -> None:
    """Create demo order events with various scenarios."""
    logger.info("Creating demo order events")
    
    base_time = dt.datetime.utcnow() - dt.timedelta(hours=6)
    
    # Scenario 1: Normal order flow (no SLA breach)
    events_normal = [
        OrderEvent(
            tenant="demo-3pl",
            source="shopify",
            event_type="order_paid",
            event_id="evt-normal-001",
            order_id="order-normal-001",
            occurred_at=base_time,
            payload={
                "source": "shopify",
                "event_type": "order_paid",
                "order_id": "order-normal-001",
                "total_amount_cents": 2999,
                "line_count": 2
            },
            correlation_id="corr-normal-001"
        ),
        OrderEvent(
            tenant="demo-3pl",
            source="wms",
            event_type="pick_completed",
            event_id="evt-normal-002",
            order_id="order-normal-001",
            occurred_at=base_time + dt.timedelta(minutes=90),  # Within 120min SLA
            payload={
                "source": "wms",
                "event_type": "pick_completed",
                "station": "PICK-01",
                "worker_id": "W123",
                "items_count": 2
            },
            correlation_id="corr-normal-001"
        ),
        OrderEvent(
            tenant="demo-3pl",
            source="wms",
            event_type="pack_completed",
            event_id="evt-normal-003",
            order_id="order-normal-001",
            occurred_at=base_time + dt.timedelta(minutes=150),  # Within 180min SLA
            payload={
                "source": "wms",
                "event_type": "pack_completed",
                "station": "PACK-01",
                "worker_id": "W456"
            },
            correlation_id="corr-normal-001"
        )
    ]
    
    # Scenario 2: Pick delay (SLA breach)
    events_pick_delay = [
        OrderEvent(
            tenant="demo-3pl",
            source="shopify",
            event_type="order_paid",
            event_id="evt-delay-001",
            order_id="order-delay-001",
            occurred_at=base_time - dt.timedelta(hours=4),
            payload={
                "source": "shopify",
                "event_type": "order_paid",
                "order_id": "order-delay-001",
                "total_amount_cents": 4999,
                "line_count": 3
            },
            correlation_id="corr-delay-001"
        ),
        OrderEvent(
            tenant="demo-3pl",
            source="wms",
            event_type="pick_completed",
            event_id="evt-delay-002",
            order_id="order-delay-001",
            occurred_at=base_time - dt.timedelta(hours=1),  # 180min delay (exceeds 120min SLA)
            payload={
                "source": "wms",
                "event_type": "pick_completed",
                "station": "PICK-02",
                "worker_id": "W789",
                "items_count": 3,
                "delay_reason": "high_volume"
            },
            correlation_id="corr-delay-001"
        )
    ]
    
    # Scenario 3: Carrier issue
    events_carrier_issue = [
        OrderEvent(
            tenant="demo-3pl",
            source="shopify",
            event_type="order_paid",
            event_id="evt-carrier-001",
            order_id="order-carrier-001",
            occurred_at=base_time - dt.timedelta(days=2),
            payload={
                "source": "shopify",
                "event_type": "order_paid",
                "order_id": "order-carrier-001",
                "total_amount_cents": 1999
            },
            correlation_id="corr-carrier-001"
        ),
        OrderEvent(
            tenant="demo-3pl",
            source="wms",
            event_type="pick_completed",
            event_id="evt-carrier-002",
            order_id="order-carrier-001",
            occurred_at=base_time - dt.timedelta(days=2, minutes=-60),
            payload={
                "source": "wms",
                "event_type": "pick_completed",
                "station": "PICK-01"
            },
            correlation_id="corr-carrier-001"
        ),
        OrderEvent(
            tenant="demo-3pl",
            source="wms",
            event_type="pack_completed",
            event_id="evt-carrier-003",
            order_id="order-carrier-001",
            occurred_at=base_time - dt.timedelta(days=2, minutes=-30),
            payload={
                "source": "wms",
                "event_type": "pack_completed",
                "station": "PACK-01"
            },
            correlation_id="corr-carrier-001"
        )
        # Note: No manifested event - will trigger carrier issue after 24h
    ]
    
    # Add all events to database
    all_events = events_normal + events_pick_delay + events_carrier_issue
    
    for event in all_events:
        db.add(event)
    
    await db.flush()
    logger.info(f"Created {len(all_events)} demo order events")


async def _create_demo_invoices(db) -> None:
    """Create demo invoices for billing validation."""
    logger.info("Creating demo invoices")
    
    invoices = [
        Invoice(
            tenant="demo-3pl",
            order_id="order-normal-001",
            invoice_number="INV-2025-001",
            billable_ops={
                "pick": 1,
                "pack": 1,
                "label": 1
            },
            amount_cents=65,  # Correct amount: 30+20+15 = 65
            currency="USD",
            status="DRAFT",
            invoice_date=dt.datetime.utcnow().date()
        ),
        Invoice(
            tenant="demo-3pl",
            order_id="order-delay-001",
            invoice_number="INV-2025-002",
            billable_ops={
                "pick": 1,
                "pack": 1,
                "label": 1,
                "rush": True  # Rush order due to delay
            },
            amount_cents=65,  # Incorrect: should be 130 (65 * 2.0 rush multiplier)
            currency="USD",
            status="DRAFT",
            invoice_date=dt.datetime.utcnow().date()
        ),
        Invoice(
            tenant="demo-3pl",
            order_id="order-carrier-001",
            invoice_number="INV-2025-003",
            billable_ops={
                "pick": 1,
                "pack": 1,
                "label": 1,
                "storage_days": 2  # 2 days storage
            },
            amount_cents=75,  # Should be 75: 65 + (2*5) = 75
            currency="USD",
            status="DRAFT",
            invoice_date=dt.datetime.utcnow().date()
        )
    ]
    
    for invoice in invoices:
        db.add(invoice)
    
    await db.flush()
    logger.info(f"Created {len(invoices)} demo invoices")


async def create_sample_exception() -> None:
    """Create a sample exception for testing AI analysis."""
    logger.info("Creating sample exception")
    
    async with get_session() as db:
        # Check if exception already exists
        existing = await db.execute(
            select(ExceptionRecord).where(ExceptionRecord.order_id == "order-delay-001")
        )
        if existing.scalars().first():
            logger.info("Sample exception already exists")
            return
        
        exception = ExceptionRecord(
            tenant="demo-3pl",
            order_id="order-delay-001",
            reason_code="PICK_DELAY",
            status="OPEN",
            severity="MEDIUM",
            correlation_id="corr-delay-001",
            context_data={
                "actual_minutes": 180,
                "sla_minutes": 120,
                "delay_minutes": 60,
                "station": "PICK-02",
                "reason": "high_volume"
            }
        )
        
        db.add(exception)
        await db.commit()
        
        logger.info("Sample exception created successfully")


async def cleanup_demo_data() -> None:
    """Clean up all demo data from database."""
    logger.info("Cleaning up demo data")
    
    async with get_session() as db:
        # Delete in reverse dependency order
        from sqlalchemy import text
        await db.execute(text("DELETE FROM invoice_adjustments WHERE tenant = 'demo-3pl'"))
        await db.execute(text("DELETE FROM invoices WHERE tenant = 'demo-3pl'"))
        await db.execute(text("DELETE FROM exceptions WHERE tenant = 'demo-3pl'"))
        await db.execute(text("DELETE FROM order_events WHERE tenant = 'demo-3pl'"))
        await db.execute(text("DELETE FROM dlq WHERE tenant = 'demo-3pl'"))
        await db.execute(text("DELETE FROM tenants WHERE name = 'demo-3pl'"))
        
        await db.commit()
        
        logger.info("Demo data cleanup completed")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "cleanup":
        asyncio.run(cleanup_demo_data())
    elif len(sys.argv) > 1 and sys.argv[1] == "exception":
        asyncio.run(create_sample_exception())
    else:
        asyncio.run(seed_demo_data())
