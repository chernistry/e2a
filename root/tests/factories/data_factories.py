"""Data factories for generating test data."""

import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

from app.storage.models import OrderEvent, ExceptionRecord, Invoice, InvoiceAdjustment


@dataclass
class EventFactory:
    """Factory for creating order events."""
    
    tenant: str = "test-tenant"
    base_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def create_shopify_event(
        self,
        event_type: str = "order_paid",
        order_id: Optional[str] = None,
        occurred_at: Optional[datetime] = None,
        payload: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create a Shopify event."""
        if order_id is None:
            order_id = f"order-{uuid.uuid4().hex[:8]}"
        
        if occurred_at is None:
            occurred_at = self.base_time
        
        if payload is None:
            payload = self._get_default_shopify_payload(event_type)
        
        return {
            "source": "shopify",
            "event_type": event_type,
            "event_id": f"evt-shopify-{uuid.uuid4().hex[:8]}",
            "order_id": order_id,
            "occurred_at": occurred_at.isoformat(),
            "payload": payload
        }
    
    def create_wms_event(
        self,
        event_type: str = "pick_completed",
        order_id: Optional[str] = None,
        occurred_at: Optional[datetime] = None,
        payload: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create a WMS event."""
        if order_id is None:
            order_id = f"order-{uuid.uuid4().hex[:8]}"
        
        if occurred_at is None:
            occurred_at = self.base_time
        
        if payload is None:
            payload = self._get_default_wms_payload(event_type)
        
        return {
            "source": "wms",
            "event_type": event_type,
            "event_id": f"evt-wms-{uuid.uuid4().hex[:8]}",
            "order_id": order_id,
            "occurred_at": occurred_at.isoformat(),
            "payload": payload
        }
    
    def create_carrier_event(
        self,
        event_type: str = "shipment_dispatched",
        order_id: Optional[str] = None,
        occurred_at: Optional[datetime] = None,
        payload: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create a carrier event."""
        if order_id is None:
            order_id = f"order-{uuid.uuid4().hex[:8]}"
        
        if occurred_at is None:
            occurred_at = self.base_time
        
        if payload is None:
            payload = self._get_default_carrier_payload(event_type)
        
        return {
            "source": "carrier",
            "event_type": event_type,
            "event_id": f"evt-carrier-{uuid.uuid4().hex[:8]}",
            "order_id": order_id,
            "occurred_at": occurred_at.isoformat(),
            "payload": payload
        }
    
    def create_order_lifecycle(
        self,
        order_id: Optional[str] = None,
        with_delays: bool = False,
        delay_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Create a complete order lifecycle."""
        if order_id is None:
            order_id = f"order-lifecycle-{uuid.uuid4().hex[:8]}"
        
        events = []
        current_time = self.base_time
        
        # Order paid
        events.append(self.create_shopify_event(
            event_type="order_paid",
            order_id=order_id,
            occurred_at=current_time,
            payload={"total_amount_cents": 2999, "line_count": 2}
        ))
        
        # Pick started
        current_time += timedelta(minutes=30)
        events.append(self.create_wms_event(
            event_type="pick_started",
            order_id=order_id,
            occurred_at=current_time,
            payload={"station": "PICK-01", "operator": "john.doe"}
        ))
        
        # Pick completed
        if with_delays and delay_type == "pick":
            current_time += timedelta(hours=3)  # Exceeds 2h SLA
        else:
            current_time += timedelta(minutes=60)  # Within SLA
        
        events.append(self.create_wms_event(
            event_type="pick_completed",
            order_id=order_id,
            occurred_at=current_time,
            payload={"station": "PICK-01", "operator": "john.doe", "items_picked": 2}
        ))
        
        # Pack completed
        if with_delays and delay_type == "pack":
            current_time += timedelta(hours=4)  # Exceeds 3h SLA from pick
        else:
            current_time += timedelta(minutes=60)  # Within SLA
        
        events.append(self.create_wms_event(
            event_type="pack_completed",
            order_id=order_id,
            occurred_at=current_time,
            payload={"station": "PACK-01", "operator": "jane.smith", "weight_grams": 500}
        ))
        
        # Label created
        current_time += timedelta(minutes=10)
        events.append(self.create_wms_event(
            event_type="label_created",
            order_id=order_id,
            occurred_at=current_time,
            payload={"carrier": "UPS", "service_level": "GROUND", "tracking_number": f"1Z999AA{uuid.uuid4().hex[:10].upper()}"}
        ))
        
        # Shipment dispatched
        if with_delays and delay_type == "ship":
            current_time += timedelta(hours=26)  # Exceeds 24h SLA from pack
        else:
            current_time += timedelta(hours=4)  # Within SLA
        
        events.append(self.create_carrier_event(
            event_type="shipment_dispatched",
            order_id=order_id,
            occurred_at=current_time,
            payload={"tracking_number": f"1Z999AA{uuid.uuid4().hex[:10].upper()}", "carrier": "UPS"}
        ))
        
        return events
    
    def _get_default_shopify_payload(self, event_type: str) -> Dict[str, Any]:
        """Get default payload for Shopify event type."""
        payloads = {
            "order_paid": {
                "total_amount_cents": 2999,
                "line_count": 2,
                "customer_id": f"cust-{uuid.uuid4().hex[:8]}"
            },
            "order_cancelled": {
                "reason": "customer_request",
                "refund_amount_cents": 2999
            }
        }
        return payloads.get(event_type, {})
    
    def _get_default_wms_payload(self, event_type: str) -> Dict[str, Any]:
        """Get default payload for WMS event type."""
        payloads = {
            "pick_started": {
                "station": "PICK-01",
                "operator": "john.doe"
            },
            "pick_completed": {
                "station": "PICK-01",
                "operator": "john.doe",
                "items_picked": 2,
                "pick_duration_minutes": 45
            },
            "pack_completed": {
                "station": "PACK-01",
                "operator": "jane.smith",
                "weight_grams": 500,
                "dimensions": {"length": 20, "width": 15, "height": 10}
            },
            "label_created": {
                "carrier": "UPS",
                "service_level": "GROUND",
                "tracking_number": f"1Z999AA{uuid.uuid4().hex[:10].upper()}"
            }
        }
        return payloads.get(event_type, {})
    
    def _get_default_carrier_payload(self, event_type: str) -> Dict[str, Any]:
        """Get default payload for carrier event type."""
        payloads = {
            "shipment_dispatched": {
                "tracking_number": f"1Z999AA{uuid.uuid4().hex[:10].upper()}",
                "carrier": "UPS",
                "service_level": "GROUND",
                "estimated_delivery": (self.base_time + timedelta(days=3)).isoformat()
            },
            "shipment_delivered": {
                "tracking_number": f"1Z999AA{uuid.uuid4().hex[:10].upper()}",
                "delivered_at": (self.base_time + timedelta(days=2)).isoformat(),
                "signature": "J.DOE"
            }
        }
        return payloads.get(event_type, {})


@dataclass
class ExceptionFactory:
    """Factory for creating exception records."""
    
    tenant: str = "test-tenant"
    
    def create_exception(
        self,
        reason_code: str = "PICK_DELAY",
        order_id: Optional[str] = None,
        severity: str = "MEDIUM",
        status: str = "OPEN",
        delay_minutes: int = 30,
        with_ai_analysis: bool = True
    ) -> ExceptionRecord:
        """Create an exception record."""
        if order_id is None:
            order_id = f"order-{uuid.uuid4().hex[:8]}"
        
        exception = ExceptionRecord(
            tenant=self.tenant,
            order_id=order_id,
            reason_code=reason_code,
            status=status,
            severity=severity,
            detected_at=datetime.now(timezone.utc),
            sla_threshold_minutes=self._get_sla_threshold(reason_code),
            actual_duration_minutes=self._get_sla_threshold(reason_code) + delay_minutes,
            delay_minutes=delay_minutes,
            correlation_id=f"corr-{uuid.uuid4().hex[:8]}"
        )
        
        if with_ai_analysis:
            exception.ai_label = reason_code
            exception.ai_confidence = 0.85
            exception.ai_reasoning = f"AI detected {reason_code.lower().replace('_', ' ')} pattern"
            exception.ops_note = self._generate_ops_note(reason_code, delay_minutes)
            exception.client_note = self._generate_client_note(reason_code)
        
        return exception
    
    def create_multiple_exceptions(
        self,
        count: int = 5,
        reason_codes: Optional[List[str]] = None,
        severities: Optional[List[str]] = None
    ) -> List[ExceptionRecord]:
        """Create multiple exception records."""
        if reason_codes is None:
            reason_codes = ["PICK_DELAY", "PACK_DELAY", "SHIP_DELAY"]
        
        if severities is None:
            severities = ["LOW", "MEDIUM", "HIGH"]
        
        exceptions = []
        for i in range(count):
            reason_code = reason_codes[i % len(reason_codes)]
            severity = severities[i % len(severities)]
            
            exception = self.create_exception(
                reason_code=reason_code,
                order_id=f"order-multi-{i:03d}",
                severity=severity,
                delay_minutes=30 + (i * 10)  # Varying delays
            )
            exceptions.append(exception)
        
        return exceptions
    
    def _get_sla_threshold(self, reason_code: str) -> int:
        """Get SLA threshold for reason code."""
        thresholds = {
            "PICK_DELAY": 120,    # 2 hours
            "PACK_DELAY": 180,    # 3 hours
            "SHIP_DELAY": 1440    # 24 hours
        }
        return thresholds.get(reason_code, 120)
    
    def _generate_ops_note(self, reason_code: str, delay_minutes: int) -> str:
        """Generate operational note for exception."""
        operation = reason_code.split('_')[0].lower()
        return f"{operation.title()} operation exceeded SLA by {delay_minutes} minutes. Station reported normal operations."
    
    def _generate_client_note(self, reason_code: str) -> str:
        """Generate client-facing note for exception."""
        operation = reason_code.split('_')[0].lower()
        return f"Your order is taking longer than expected to {operation}. We're working to get it out soon."


@dataclass
class InvoiceFactory:
    """Factory for creating invoices and adjustments."""
    
    tenant: str = "test-tenant"
    
    def create_invoice(
        self,
        order_id: Optional[str] = None,
        amount_cents: int = 65,  # Default: pick(30) + pack(20) + label(15)
        status: str = "DRAFT",
        with_operations: bool = True
    ) -> Invoice:
        """Create an invoice."""
        if order_id is None:
            order_id = f"order-{uuid.uuid4().hex[:8]}"
        
        billable_ops = []
        if with_operations:
            billable_ops = [
                {
                    "operation": "pick",
                    "quantity": 1,
                    "rate_cents": 30,
                    "occurred_at": datetime.now(timezone.utc).isoformat(),
                    "metadata": {"station": "PICK-01"}
                },
                {
                    "operation": "pack",
                    "quantity": 1,
                    "rate_cents": 20,
                    "occurred_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
                    "metadata": {"station": "PACK-01"}
                },
                {
                    "operation": "label",
                    "quantity": 1,
                    "rate_cents": 15,
                    "occurred_at": (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(),
                    "metadata": {"carrier": "UPS"}
                }
            ]
        
        return Invoice(
            tenant=self.tenant,
            order_id=order_id,
            amount_cents=amount_cents,
            currency="USD",
            status=status,
            billable_ops=billable_ops,
            created_at=datetime.now(timezone.utc)
        )
    
    def create_invoice_with_discrepancy(
        self,
        order_id: Optional[str] = None,
        original_amount: int = 100,
        correct_amount: int = 65
    ) -> Invoice:
        """Create an invoice with amount discrepancy."""
        invoice = self.create_invoice(
            order_id=order_id,
            amount_cents=original_amount
        )
        
        # Store the correct amount for validation
        invoice._correct_amount = correct_amount
        
        return invoice
    
    def create_adjustment(
        self,
        invoice_id: int,
        delta_cents: int = -35,  # Decrease by $0.35
        reason: str = "RECALCULATION"
    ) -> InvoiceAdjustment:
        """Create an invoice adjustment."""
        return InvoiceAdjustment(
            invoice_id=invoice_id,
            delta_cents=delta_cents,
            reason=reason,
            rationale=f"Recalculated amount based on actual operations. {reason} adjustment of ${abs(delta_cents)/100:.2f}.",
            created_at=datetime.now(timezone.utc)
        )
    
    def create_multiple_invoices(
        self,
        count: int = 10,
        with_discrepancies: bool = False
    ) -> List[Invoice]:
        """Create multiple invoices."""
        invoices = []
        
        for i in range(count):
            if with_discrepancies and i % 3 == 0:  # Every 3rd invoice has discrepancy
                invoice = self.create_invoice_with_discrepancy(
                    order_id=f"order-invoice-{i:03d}",
                    original_amount=100 + (i * 10),
                    correct_amount=65 + (i * 5)
                )
            else:
                invoice = self.create_invoice(
                    order_id=f"order-invoice-{i:03d}",
                    amount_cents=65 + (i * 5)
                )
            
            invoices.append(invoice)
        
        return invoices


@dataclass
class ScenarioFactory:
    """Factory for creating complex test scenarios."""
    
    def __init__(self, tenant: str = "test-tenant"):
        self.tenant = tenant
        self.event_factory = EventFactory(tenant=tenant)
        self.exception_factory = ExceptionFactory(tenant=tenant)
        self.invoice_factory = InvoiceFactory(tenant=tenant)
    
    def create_sla_breach_scenario(
        self,
        breach_type: str = "pick",
        severity: str = "MEDIUM"
    ) -> Dict[str, Any]:
        """Create a complete SLA breach scenario."""
        order_id = f"order-breach-{breach_type}-{uuid.uuid4().hex[:8]}"
        
        # Create events leading to breach
        events = self.event_factory.create_order_lifecycle(
            order_id=order_id,
            with_delays=True,
            delay_type=breach_type
        )
        
        # Create expected exception
        reason_code = f"{breach_type.upper()}_DELAY"
        exception = self.exception_factory.create_exception(
            reason_code=reason_code,
            order_id=order_id,
            severity=severity
        )
        
        return {
            "order_id": order_id,
            "events": events,
            "expected_exception": exception,
            "breach_type": breach_type,
            "severity": severity
        }
    
    def create_multi_tenant_scenario(
        self,
        tenant_count: int = 3,
        orders_per_tenant: int = 5
    ) -> Dict[str, Any]:
        """Create multi-tenant test scenario."""
        tenants_data = {}
        
        for i in range(tenant_count):
            tenant_id = f"tenant-{i+1}"
            tenant_factory = EventFactory(tenant=tenant_id)
            
            tenant_orders = []
            for j in range(orders_per_tenant):
                order_id = f"order-{tenant_id}-{j+1}"
                events = tenant_factory.create_order_lifecycle(order_id=order_id)
                tenant_orders.append({
                    "order_id": order_id,
                    "events": events
                })
            
            tenants_data[tenant_id] = {
                "orders": tenant_orders,
                "expected_event_count": orders_per_tenant * 6  # 6 events per lifecycle
            }
        
        return tenants_data
    
    def create_invoice_validation_scenario(
        self,
        invoice_count: int = 20,
        discrepancy_rate: float = 0.3
    ) -> Dict[str, Any]:
        """Create invoice validation scenario."""
        invoices = []
        expected_adjustments = 0
        
        for i in range(invoice_count):
            has_discrepancy = i < (invoice_count * discrepancy_rate)
            
            if has_discrepancy:
                invoice = self.invoice_factory.create_invoice_with_discrepancy(
                    order_id=f"order-validation-{i:03d}"
                )
                expected_adjustments += 1
            else:
                invoice = self.invoice_factory.create_invoice(
                    order_id=f"order-validation-{i:03d}"
                )
            
            invoices.append(invoice)
        
        return {
            "invoices": invoices,
            "expected_adjustments": expected_adjustments,
            "discrepancy_rate": discrepancy_rate
        }
    
    def create_performance_test_scenario(
        self,
        event_count: int = 1000,
        concurrent_tenants: int = 10
    ) -> Dict[str, Any]:
        """Create performance test scenario."""
        scenarios = {}
        
        for tenant_i in range(concurrent_tenants):
            tenant_id = f"perf-tenant-{tenant_i+1}"
            tenant_factory = EventFactory(tenant=tenant_id)
            
            events = []
            for event_i in range(event_count // concurrent_tenants):
                order_id = f"perf-order-{tenant_i}-{event_i}"
                
                # Create single event for performance testing
                event = tenant_factory.create_shopify_event(
                    order_id=order_id,
                    payload={"total_amount_cents": 2999}
                )
                events.append(event)
            
            scenarios[tenant_id] = {
                "events": events,
                "expected_count": len(events)
            }
        
        return {
            "tenant_scenarios": scenarios,
            "total_events": event_count,
            "concurrent_tenants": concurrent_tenants
        }
