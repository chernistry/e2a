# ==== ORDER ANALYZER SERVICE ==== #

"""
Order analyzer for detecting problems in order data.

This module analyzes incoming order data to detect potential issues
that should trigger exceptions, such as invalid addresses, payment problems,
inventory shortages, and delivery delays.
"""

from datetime import datetime
from typing import Dict, Any, Optional, List

from app.observability.tracing import get_tracer


tracer = get_tracer(__name__)


class OrderAnalyzer:
    """
    Analyzer for detecting problems in order data.
    
    Examines order content, customer information, and delivery details
    to identify issues that should trigger exception creation.
    """
    
    def __init__(self):
        """Initialize the order analyzer."""
        pass
    
    def analyze_order(self, order_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Analyze order data for potential problems.
        
        Args:
            order_data (Dict[str, Any]): Order data from webhook
            
        Returns:
            List[Dict[str, Any]]: List of detected problems
        """
        problems = []
        
        # Extract order details
        order = order_data.get("data", {}).get("order", {})
        if not order:
            return problems
        
        # Check for delivery delays
        delivery_problem = self._check_delivery_delay(order)
        if delivery_problem:
            problems.append(delivery_problem)
        
        # Check for payment issues
        payment_problem = self._check_payment_issues(order)
        if payment_problem:
            problems.append(payment_problem)
        
        # Check for address problems
        address_problem = self._check_address_issues(order)
        if address_problem:
            problems.append(address_problem)
        
        # Check for inventory issues
        inventory_problem = self._check_inventory_issues(order)
        if inventory_problem:
            problems.append(inventory_problem)
        
        # Check for package damage
        damage_problem = self._check_package_damage(order)
        if damage_problem:
            problems.append(damage_problem)
        
        # Check for customer availability issues
        customer_problem = self._check_customer_availability(order)
        if customer_problem:
            problems.append(customer_problem)
        
        return problems
    
    def _check_delivery_delay(self, order: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Check for delivery delay indicators."""
        # Check fulfillment status
        fulfillment_status = order.get("fulfillment_status")
        if fulfillment_status == "delayed":
            return {
                "reason_code": "DELIVERY_DELAY",
                "severity": "HIGH",
                "description": "Order marked as delayed in fulfillment system",
                "context": {
                    "fulfillment_status": fulfillment_status
                }
            }
        
        # Check estimated delivery date
        estimated_delivery = order.get("estimated_delivery_date")
        if estimated_delivery:
            try:
                delivery_date = datetime.fromisoformat(estimated_delivery.replace('Z', '+00:00'))
                now = datetime.now(delivery_date.tzinfo)
                
                # If delivery date is in the past, it's overdue
                if delivery_date < now:
                    days_overdue = (now - delivery_date).days
                    severity = "CRITICAL" if days_overdue > 3 else "HIGH" if days_overdue > 1 else "MEDIUM"
                    
                    return {
                        "reason_code": "DELIVERY_DELAY",
                        "severity": severity,
                        "description": f"Order is {days_overdue} days overdue for delivery",
                        "context": {
                            "estimated_delivery": estimated_delivery,
                            "days_overdue": days_overdue
                        }
                    }
            except (ValueError, TypeError):
                pass
        
        return None
    
    def _check_payment_issues(self, order: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Check for payment-related problems."""
        financial_status = order.get("financial_status")
        
        if financial_status == "pending":
            return {
                "reason_code": "PAYMENT_FAILED",
                "severity": "HIGH",
                "description": "Payment is still pending after order creation",
                "context": {
                    "financial_status": financial_status
                }
            }
        
        # Check for payment issues flag
        if order.get("payment_issues"):
            return {
                "reason_code": "PAYMENT_FAILED",
                "severity": "HIGH",
                "description": "Payment processing issues detected",
                "context": {
                    "payment_issues": True
                }
            }
        
        return None
    
    def _check_address_issues(self, order: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Check for address-related problems."""
        shipping_address = order.get("shipping_address", {})
        
        # Check for invalid zip codes
        zip_code = shipping_address.get("zip", "")
        if zip_code in ["00000", "99999", "INVALID"] or not zip_code:
            return {
                "reason_code": "ADDRESS_INVALID",
                "severity": "MEDIUM",
                "description": "Invalid or missing postal code in shipping address",
                "context": {
                    "zip_code": zip_code,
                    "shipping_address": shipping_address
                }
            }
        
        # Check for problematic addresses
        address1 = shipping_address.get("address1", "")
        city = shipping_address.get("city", "")
        
        if "Nonexistent" in address1 or city == "Nowhere":
            return {
                "reason_code": "ADDRESS_INVALID",
                "severity": "HIGH",
                "description": "Shipping address appears to be invalid or non-existent",
                "context": {
                    "address1": address1,
                    "city": city
                }
            }
        
        return None
    
    def _check_inventory_issues(self, order: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Check for inventory-related problems."""
        line_items = order.get("line_items", [])
        
        for item in line_items:
            # Check for inventory shortage flag
            if item.get("inventory_shortage"):
                available_qty = item.get("available_quantity", 0)
                requested_qty = item.get("quantity", 1)
                
                severity = "CRITICAL" if available_qty == 0 else "HIGH"
                
                return {
                    "reason_code": "INVENTORY_SHORTAGE",
                    "severity": severity,
                    "description": f"Insufficient inventory for {item.get('title', 'item')}",
                    "context": {
                        "item_title": item.get("title"),
                        "sku": item.get("sku"),
                        "requested_quantity": requested_qty,
                        "available_quantity": available_qty
                    }
                }
        
        return None
    
    def _check_package_damage(self, order: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Check for package damage indicators."""
        package_condition = order.get("package_condition")
        
        if package_condition == "damaged":
            return {
                "reason_code": "DAMAGED_PACKAGE",
                "severity": "HIGH",
                "description": "Package reported as damaged during transit",
                "context": {
                    "package_condition": package_condition,
                    "damage_report": order.get("damage_report")
                }
            }
        
        return None
    
    def _check_customer_availability(self, order: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Check for customer availability issues."""
        delivery_attempts = order.get("delivery_attempts", 0)
        delivery_status = order.get("delivery_status")
        
        if delivery_attempts >= 2 or delivery_status == "failed_delivery":
            severity = "HIGH" if delivery_attempts >= 3 else "MEDIUM"
            
            return {
                "reason_code": "CUSTOMER_UNAVAILABLE",
                "severity": severity,
                "description": f"Customer unavailable for delivery after {delivery_attempts} attempts",
                "context": {
                    "delivery_attempts": delivery_attempts,
                    "delivery_status": delivery_status
                }
            }
        
        return None


# Global instance
_order_analyzer: Optional[OrderAnalyzer] = None


def get_order_analyzer() -> OrderAnalyzer:
    """
    Get global order analyzer instance.
    
    Returns:
        OrderAnalyzer: Global order analyzer instance
    """
    global _order_analyzer
    if _order_analyzer is None:
        _order_analyzer = OrderAnalyzer()
    return _order_analyzer
