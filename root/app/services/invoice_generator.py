# ==== INVOICE GENERATOR SERVICE ==== #

"""
Invoice generator service for creating invoices from completed order events.

This module provides automatic invoice generation based on order completion
events, calculating billable operations and amounts according to tenant
billing configurations.
"""

import datetime as dt
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.storage.models import OrderEvent, Invoice
from app.services.billing import compute_amount_cents
from app.observability.tracing import get_tracer
from app.observability.logging import ContextualLogger


tracer = get_tracer(__name__)
logger = ContextualLogger(__name__)


class InvoiceGeneratorService:
    """
    Service for generating invoices from completed order events.
    
    Analyzes order event sequences to identify completed orders and
    automatically generates invoices with calculated billable operations
    and amounts based on tenant billing configurations.
    """
    
    def __init__(self):
        """Initialize invoice generator service."""
        pass
    
    async def generate_invoice(
        self,
        tenant: str,
        order_id: str,
        customer_email: str = "",
        total_amount: float = 0.0,
        currency: str = "USD",
        line_items: List = None,
        **kwargs
    ) -> Optional[Invoice]:
        """
        Generate a single invoice for an order.
        
        Args:
            tenant: Tenant identifier
            order_id: Order identifier
            customer_email: Customer email address
            total_amount: Total amount for the invoice
            currency: Currency code
            line_items: List of line items
            **kwargs: Additional parameters
            
        Returns:
            Generated invoice or None if failed
        """
        from app.storage.db import get_session
        
        async with get_session() as db:
            try:
                # Check if invoice already exists
                existing = await self._check_existing_invoice(db, tenant, order_id)
                if existing:
                    logger.info(f"Invoice already exists for order {order_id}")
                    return existing
                
                # Get order events for billable operations calculation
                events_query = select(OrderEvent).where(
                    and_(
                        OrderEvent.tenant == tenant,
                        OrderEvent.order_id == order_id
                    )
                )
                result = await db.execute(events_query)
                events = result.scalars().all()
                
                if not events:
                    logger.warning(f"No events found for order {order_id}")
                    return None
                
                # Calculate billable operations
                billable_ops = self._calculate_billable_operations(events)
                
                # Generate invoice number
                invoice_number = await self._generate_invoice_number(db, tenant)
                
                # Calculate amount from billable operations (ignore passed total_amount)
                amount_cents = compute_amount_cents(billable_ops, tenant)
                logger.info(f"Calculated 3PL service fees: {amount_cents} cents for operations {billable_ops}")
                
                invoice = Invoice(
                    tenant=tenant,
                    order_id=order_id,
                    invoice_number=invoice_number,
                    billable_ops=billable_ops,
                    amount_cents=amount_cents,
                    currency=currency,
                    status="PENDING",
                    invoice_date=dt.datetime.utcnow(),
                    due_date=dt.datetime.utcnow() + dt.timedelta(days=30)
                )
                
                db.add(invoice)
                await db.commit()
                await db.refresh(invoice)
                
                logger.info(f"Generated invoice {invoice_number} for order {order_id}: ${amount_cents/100:.2f}")
                
                # Generate invoice file if enabled
                from app.settings import settings
                logger.info(f"🔍 Checking invoice file generation - GENERATE_INVOICE_FILES: {settings.GENERATE_INVOICE_FILES}")
                if settings.GENERATE_INVOICE_FILES:
                    logger.info(f"🔍 Triggering invoice file generation for invoice {invoice_number}")
                    await self._generate_invoice_file(invoice, customer_email, line_items or [])
                else:
                    logger.info(f"🔍 Invoice file generation disabled in settings")
                
                return invoice
                
            except Exception as e:
                logger.error(f"Failed to generate invoice for order {order_id}: {e}")
                await db.rollback()
                return None
    
    async def _generate_invoice_file(self, invoice: Invoice, customer_email: str, line_items: List) -> None:
        """Generate invoice text file."""
        logger.info(f"🔍 Invoice file generation called for invoice {invoice.invoice_number}")
        
        try:
            from app.settings import settings
            import os
            
            logger.info(f"🔍 Invoice file settings - GENERATE_INVOICE_FILES: {settings.GENERATE_INVOICE_FILES}")
            logger.info(f"🔍 Invoice file settings - INVOICE_FILES_PATH: {settings.INVOICE_FILES_PATH}")
            
            # Ensure directory exists
            logger.info(f"🔍 Creating directory: {settings.INVOICE_FILES_PATH}")
            os.makedirs(settings.INVOICE_FILES_PATH, exist_ok=True)
            logger.info(f"✅ Directory created/verified: {settings.INVOICE_FILES_PATH}")
            
            # Build line items section
            line_items_section = ""
            product_subtotal = 0.0
            if line_items:
                line_items_section = "\nPRODUCT LINE ITEMS:\n"
                for item in line_items:
                    sku = item.get('sku', 'N/A')
                    qty = item.get('quantity', 1)
                    price = float(item.get('price', 0))
                    line_total = qty * price
                    product_subtotal += line_total
                    line_items_section += f"  • {sku} - Qty: {qty} × ${price:.2f} = ${line_total:.2f}\n"
                
                line_items_section += f"\nProduct Subtotal: ${product_subtotal:.2f}\n"
            
            # Add 3PL service charges
            service_charges_section = "\n3PL SERVICE CHARGES:\n"
            billable_ops = invoice.billable_ops or {}
            service_total = 0.0
            
            # Get billing rates (should match compute_amount_cents)
            pick_fee = 0.30  # $0.30 per pick
            pack_fee = 0.20  # $0.20 per pack  
            label_fee = 0.15 # $0.15 per label
            
            if billable_ops.get("pick", 0) > 0:
                pick_charge = billable_ops["pick"] * pick_fee
                service_total += pick_charge
                service_charges_section += f"  • Pick Operations: {billable_ops['pick']} × ${pick_fee:.2f} = ${pick_charge:.2f}\n"
            
            if billable_ops.get("pack", 0) > 0:
                pack_charge = billable_ops["pack"] * pack_fee
                service_total += pack_charge
                service_charges_section += f"  • Pack Operations: {billable_ops['pack']} × ${pack_fee:.2f} = ${pack_charge:.2f}\n"
            
            if billable_ops.get("label", 0) > 0:
                label_charge = billable_ops["label"] * label_fee
                service_total += label_charge
                service_charges_section += f"  • Label Operations: {billable_ops['label']} × ${label_fee:.2f} = ${label_charge:.2f}\n"
            
            service_charges_section += f"\nService Charges Subtotal: ${service_total:.2f}\n"
            
            # Invoice content with both product line items and service charges
            invoice_content = f"""INVOICE {invoice.invoice_number}
            
Order ID: {invoice.order_id}
Customer: {customer_email}
Date: {invoice.invoice_date.strftime('%Y-%m-%d')}
Due Date: {invoice.due_date.strftime('%Y-%m-%d') if invoice.due_date else 'N/A'}
{line_items_section}{service_charges_section}
TOTAL AMOUNT: ${invoice.amount_cents/100:.2f} {invoice.currency}
Status: {invoice.status}
"""
            
            # Save as text file
            filename = f"{invoice.invoice_number}.txt"
            filepath = os.path.join(settings.INVOICE_FILES_PATH, filename)
            
            logger.info(f"🔍 Writing invoice file to: {filepath}")
            
            with open(filepath, 'w') as f:
                f.write(invoice_content)
            
            # Verify file was created
            if os.path.exists(filepath):
                file_size = os.path.getsize(filepath)
                logger.info(f"✅ Invoice file created successfully: {filepath} ({file_size} bytes)")
            else:
                logger.error(f"❌ Invoice file not found after creation: {filepath}")
            
        except Exception as e:
            logger.error(f"❌ Failed to generate invoice file for invoice {invoice.invoice_number}: {e}")
            import traceback
            logger.error(f"❌ Full traceback: {traceback.format_exc()}")
    
    async def generate_invoices_for_completed_orders(
        self, 
        db: AsyncSession,
        tenant: str = None,
        lookback_hours: int = 24
    ) -> List[Invoice]:
        """
        Generate invoices for orders completed in the last N hours.
        
        Identifies orders that have completed their fulfillment cycle
        and generates invoices with calculated billable operations.
        
        Args:
            db (AsyncSession): Database session
            tenant (str): Specific tenant to process (None for all)
            lookback_hours (int): How far back to look for completed orders
            
        Returns:
            List[Invoice]: List of generated invoices
        """
        with tracer.start_as_current_span("generate_invoices_for_completed_orders") as span:
            span.set_attribute("lookback_hours", lookback_hours)
            if tenant:
                span.set_attribute("tenant", tenant)
            
            # Get cutoff time
            cutoff_time = dt.datetime.utcnow() - dt.timedelta(hours=lookback_hours)
            
            # Find completed orders
            completed_orders = await self._find_completed_orders(
                db, tenant, cutoff_time
            )
            
            logger.info(f"Found {len(completed_orders)} completed orders to invoice")
            span.set_attribute("completed_orders_count", len(completed_orders))
            
            generated_invoices = []
            
            for order_info in completed_orders:
                try:
                    # Check if invoice already exists
                    existing_invoice = await self._check_existing_invoice(
                        db, order_info["tenant"], order_info["order_id"]
                    )
                    
                    if existing_invoice:
                        logger.debug(f"Invoice already exists for order {order_info['order_id']}")
                        continue
                    
                    # Generate invoice
                    invoice = await self._generate_invoice_for_order(
                        db, order_info
                    )
                    
                    if invoice:
                        generated_invoices.append(invoice)
                        logger.info(f"Generated invoice for order {order_info['order_id']}")
                    
                except Exception as e:
                    logger.error(f"Failed to generate invoice for order {order_info['order_id']}: {str(e)}")
                    continue
            
            # Commit all invoices
            if generated_invoices:
                await db.commit()
                logger.info(f"Successfully generated {len(generated_invoices)} invoices")
            
            span.set_attribute("invoices_generated", len(generated_invoices))
            return generated_invoices
    
    async def _find_completed_orders(
        self,
        db: AsyncSession,
        tenant: str = None,
        cutoff_time: dt.datetime = None
    ) -> List[Dict[str, Any]]:
        """
        Find orders that have completed their fulfillment cycle.
        
        An order is considered complete if it has:
        - order_paid event
        - pick_completed event
        - pack_completed event
        - ship_label_printed or manifested event (optional)
        
        Args:
            db (AsyncSession): Database session
            tenant (str): Specific tenant filter
            cutoff_time (dt.datetime): Only consider events after this time
            
        Returns:
            List[Dict[str, Any]]: List of completed order information
        """
        # Build query conditions
        conditions = []
        if tenant:
            conditions.append(OrderEvent.tenant == tenant)
        if cutoff_time:
            conditions.append(OrderEvent.occurred_at >= cutoff_time)
        
        # Get all relevant events
        query = select(OrderEvent).where(and_(*conditions)) if conditions else select(OrderEvent)
        result = await db.execute(query)
        events = result.scalars().all()
        
        # Group events by tenant and order_id
        orders_by_key = {}
        for event in events:
            key = (event.tenant, event.order_id)
            if key not in orders_by_key:
                orders_by_key[key] = {
                    "tenant": event.tenant,
                    "order_id": event.order_id,
                    "events": []
                }
            orders_by_key[key]["events"].append(event)
        
        # Filter for completed orders
        completed_orders = []
        for order_info in orders_by_key.values():
            if self._is_order_complete(order_info["events"]):
                completed_orders.append(order_info)
        
        return completed_orders
    
    def _is_order_complete(self, events: List[OrderEvent]) -> bool:
        """
        Check if an order has completed its fulfillment cycle.
        
        Args:
            events (List[OrderEvent]): List of events for the order
            
        Returns:
            bool: True if order is complete
        """
        event_types = {event.event_type for event in events}
        
        # Required events for completion
        required_events = {
            "order_paid",
            "pick_completed", 
            "pack_completed"
        }
        
        # Optional completion events (at least one should be present)
        completion_events = {
            "ship_label_printed",
            "label_created", 
            "manifested",
            "shipped"
        }
        
        # Check if all required events are present
        has_required = required_events.issubset(event_types)
        
        # Check if at least one completion event is present (or skip this check for now)
        has_completion = bool(completion_events.intersection(event_types))
        
        # For now, just require the core fulfillment events
        return has_required
    
    async def _check_existing_invoice(
        self,
        db: AsyncSession,
        tenant: str,
        order_id: str
    ) -> Optional[Invoice]:
        """
        Check if an invoice already exists for the order.
        
        Args:
            db (AsyncSession): Database session
            tenant (str): Tenant identifier
            order_id (str): Order identifier
            
        Returns:
            Optional[Invoice]: Existing invoice if found
        """
        query = select(Invoice).where(
            and_(
                Invoice.tenant == tenant,
                Invoice.order_id == order_id
            )
        )
        result = await db.execute(query)
        return result.scalars().first()
    
    async def _generate_invoice_for_order(
        self,
        db: AsyncSession,
        order_info: Dict[str, Any]
    ) -> Optional[Invoice]:
        """
        Generate an invoice for a completed order.
        
        Args:
            db (AsyncSession): Database session
            order_info (Dict[str, Any]): Order information with events
            
        Returns:
            Optional[Invoice]: Generated invoice
        """
        tenant = order_info["tenant"]
        order_id = order_info["order_id"]
        events = order_info["events"]
        
        with tracer.start_as_current_span("generate_invoice_for_order") as span:
            span.set_attribute("tenant", tenant)
            span.set_attribute("order_id", order_id)
            span.set_attribute("events_count", len(events))
            
            # Calculate billable operations from events
            billable_ops = self._calculate_billable_operations(events)
            
            # Calculate amount
            amount_cents = compute_amount_cents(billable_ops, tenant)
            
            # Generate invoice number
            invoice_number = await self._generate_invoice_number(db, tenant)
            
            # Create invoice
            invoice = Invoice(
                tenant=tenant,
                order_id=order_id,
                invoice_number=invoice_number,
                billable_ops=billable_ops,
                amount_cents=amount_cents,
                currency="USD",
                status="DRAFT",
                invoice_date=dt.datetime.utcnow().date()
            )
            
            db.add(invoice)
            await db.flush()
            
            span.set_attribute("invoice_id", invoice.id)
            span.set_attribute("amount_cents", amount_cents)
            
            logger.info(
                f"Generated invoice {invoice_number} for order {order_id}: "
                f"${amount_cents/100:.2f} ({billable_ops})"
            )
            
            return invoice
    
    def _calculate_billable_operations(self, events: List[OrderEvent]) -> Dict[str, Any]:
        """
        Calculate billable operations from order events.
        
        Args:
            events (List[OrderEvent]): List of order events
            
        Returns:
            Dict[str, Any]: Dictionary of billable operations
        """
        operations = {
            "pick": 0,
            "pack": 0,
            "label": 0,
            "kitting": 0,
            "storage_days": 0,
            "returns": 0
        }
        
        # Count operations based on event types
        for event in events:
            if event.event_type == "pick_completed":
                operations["pick"] += 1
            elif event.event_type == "pack_completed":
                operations["pack"] += 1
            elif event.event_type in ["ship_label_printed", "label_created"]:
                operations["label"] += 1
            elif event.event_type == "kitting_completed":
                operations["kitting"] += 1
            elif event.event_type == "return_processed":
                operations["returns"] += 1
        
        # Calculate storage days (simplified)
        if events:
            # Sort events by time
            sorted_events = sorted(events, key=lambda e: e.occurred_at)
            first_event = sorted_events[0]
            last_event = sorted_events[-1]
            
            # Calculate storage duration
            storage_duration = last_event.occurred_at - first_event.occurred_at
            operations["storage_days"] = max(1, storage_duration.days)
        
        # Check for special handling flags from event payloads
        for event in events:
            payload = event.payload or {}
            
            # Check for rush processing
            if payload.get("priority") == "rush" or payload.get("rush", False):
                operations["rush"] = True
            
            # Check for oversized items
            if payload.get("oversized", False) or payload.get("size_category") == "oversized":
                operations["oversized"] = True
            
            # Check for hazmat
            if payload.get("hazmat", False) or payload.get("hazardous", False):
                operations["hazmat"] = True
            
            # Check for fragile items
            if payload.get("fragile", False) or payload.get("handling") == "fragile":
                operations["fragile"] = True
        
        return operations
    
    async def _generate_invoice_number(
        self,
        db: AsyncSession,
        tenant: str
    ) -> str:
        """
        Generate a unique invoice number for the tenant.
        
        Args:
            db (AsyncSession): Database session
            tenant (str): Tenant identifier
            
        Returns:
            str: Generated invoice number
        """
        # Get current year and month
        now = dt.datetime.utcnow()
        year_month = now.strftime("%Y%m")
        
        # Count existing invoices for this tenant and month
        query = select(Invoice).where(
            and_(
                Invoice.tenant == tenant,
                Invoice.created_at >= dt.datetime(now.year, now.month, 1)
            )
        )
        result = await db.execute(query)
        existing_count = len(result.scalars().all())
        
        # Generate sequential number
        sequence = existing_count + 1
        
        # Format: INV-TENANT-YYYYMM-NNNN
        tenant_code = tenant.upper().replace("-", "")[:4]
        invoice_number = f"INV-{tenant_code}-{year_month}-{sequence:04d}"
        
        return invoice_number


# ==== STANDALONE FUNCTIONS ==== #


async def generate_missing_invoices(
    db: AsyncSession,
    tenant: str = None,
    lookback_hours: int = 168  # 1 week default
) -> List[Invoice]:
    """
    Generate missing invoices for completed orders.
    
    This is a convenience function that can be called from flows
    or management commands to generate invoices for orders that
    completed but don't have invoices yet.
    
    Args:
        db (AsyncSession): Database session
        tenant (str): Specific tenant to process (None for all)
        lookback_hours (int): How far back to look for completed orders
        
    Returns:
        List[Invoice]: List of generated invoices
    """
    generator = InvoiceGeneratorService()
    return await generator.generate_invoices_for_completed_orders(
        db, tenant, lookback_hours
    )


async def backfill_invoices_for_tenant(
    db: AsyncSession,
    tenant: str,
    start_date: dt.datetime = None,
    end_date: dt.datetime = None
) -> List[Invoice]:
    """
    Backfill invoices for a specific tenant and date range.
    
    Args:
        db (AsyncSession): Database session
        tenant (str): Tenant identifier
        start_date (dt.datetime): Start date for backfill
        end_date (dt.datetime): End date for backfill
        
    Returns:
        List[Invoice]: List of generated invoices
    """
    if not start_date:
        start_date = dt.datetime.utcnow() - dt.timedelta(days=30)
    if not end_date:
        end_date = dt.datetime.utcnow()
    
    # Calculate lookback hours from date range
    lookback_hours = int((end_date - start_date).total_seconds() / 3600)
    
    generator = InvoiceGeneratorService()
    return await generator.generate_invoices_for_completed_orders(
        db, tenant, lookback_hours
    )
