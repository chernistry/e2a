# ==== ORDER ANALYZER SERVICE ==== #

"""
Order analyzer for detecting problems in order data.

This module analyzes incoming order data to detect potential issues
that should trigger exceptions. Now powered by AI for intelligent
problem detection, with rule-based fallback for reliability.
"""

from datetime import datetime
from typing import Dict, Any, Optional, List

from app.observability.tracing import get_tracer
from app.observability.logging import ContextualLogger
from app.services.ai_order_analyzer import get_ai_order_analyzer


tracer = get_tracer(__name__)
logger = ContextualLogger(__name__)


class OrderAnalyzer:
    """
    Analyzer for detecting problems in order data.
    
    Uses AI-powered analysis to examine order content, customer information,
    and delivery details to identify issues that should trigger exception creation.
    Falls back to rule-based analysis when AI is unavailable.
    """
    
    def __init__(self):
        """Initialize the order analyzer."""
        self.ai_analyzer = get_ai_order_analyzer()
    
    async def analyze_order(self, order_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Analyze order data for potential problems using AI.
        
        Args:
            order_data (Dict[str, Any]): Order data from webhook
            
        Returns:
            List[Dict[str, Any]]: List of detected problems
        """
        problems = []
        
        # Extract order details (handle both webhook and direct order formats)
        order = order_data.get("data", {}).get("order", order_data)
        if not order:
            return problems
        
        try:
            # AI-powered analysis (primary method)
            ai_result = await self.ai_analyzer.analyze_order_problems(order_data)
            
            # Check if AI analysis succeeded
            if (ai_result.get("has_problems") is not None and 
                ai_result.get("confidence") is not None and 
                ai_result.get("confidence") >= 0.7):
                
                # Convert AI problems to exception format
                if ai_result.get("has_problems"):
                    for problem in ai_result.get("problems", []):
                        exception_problem = self._convert_ai_problem_to_exception(problem, order, ai_result)
                        problems.append(exception_problem)
                
                logger.info(
                    f"AI order analysis completed successfully",
                    extra={
                        "order_id": order.get("id"),
                        "has_problems": ai_result.get("has_problems"),
                        "confidence": ai_result.get("confidence"),
                        "problems_count": len(problems)
                    }
                )
                
                return problems
            
            # AI analysis failed or low confidence - use fallback
            logger.warning(
                f"AI analysis failed or low confidence, using fallback",
                extra={
                    "order_id": order.get("id"),
                    "ai_confidence": ai_result.get("confidence"),
                    "ai_error": ai_result.get("error")
                }
            )
            
        except Exception as e:
            logger.error(f"AI order analysis error: {e}, using fallback")
        
        # Fallback to rule-based analysis
        return await self._legacy_analyze_order(order_data)
    
    def _convert_ai_problem_to_exception(
        self, 
        ai_problem: Dict[str, Any], 
        order: Dict[str, Any],
        ai_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Convert AI problem to exception record format.
        
        Args:
            ai_problem (Dict[str, Any]): AI-detected problem
            order (Dict[str, Any]): Order data
            ai_result (Dict[str, Any]): Complete AI analysis result
            
        Returns:
            Dict[str, Any]: Exception record format
        """
        return {
            "reason_code": ai_problem["type"],
            "severity": ai_problem["severity"],
            "description": ai_problem["reason"],
            "context": {
                "ai_analysis": True,
                "ai_confidence": ai_result.get("confidence"),
                "field": ai_problem["field"],
                "impact": ai_problem.get("impact"),
                "recommendations": ai_result.get("recommendations", []),
                "risk_assessment": ai_result.get("risk_assessment", {}),
                "analysis_method": "ai_powered"
            }
        }
    
    async def _legacy_analyze_order(self, order_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Legacy rule-based analysis (fallback only).
        
        Maintains existing hardcoded checks as fallback when AI is unavailable.
        This is the embarrassing code we're replacing with AI.
        
        Args:
            order_data (Dict[str, Any]): Order data from webhook
            
        Returns:
            List[Dict[str, Any]]: List of detected problems
        """
        problems = []
        
        # Extract order details
        order = order_data.get("data", {}).get("order", order_data)
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
        
        # Check for address problems (embarrassing hardcoded checks)
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
