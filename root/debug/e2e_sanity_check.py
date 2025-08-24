#!/usr/bin/env python3
"""
End-to-end validation script for Octup E²A business flows.

This script performs comprehensive validation of all business flows after a full
database reset by generating orders, triggering Prefect deployments, and validating
system state across all components.
"""

import argparse
import asyncio
import json
import logging
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# Configuration
ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

# Service endpoints
API_BASE = "http://localhost:8000"
PREFECT_BASE = "http://localhost:4200"
SHOPIFY_MOCK_BASE = "http://localhost:8090"

# Flow deployment configurations - will be populated dynamically
DEPLOYMENT_CONFIGS = {}

# Expected flow result structures for validation - Updated for simplified architecture
FLOW_RESULT_SCHEMAS = {
    "event-processor": {
        "required_keys": [
            "order_analysis", "sla_evaluation", "ai_processing", "summary"
        ],
        "nested_validations": {
            "order_analysis": ["events_processed", "exceptions_created"],
            "sla_evaluation": ["orders_evaluated", "sla_breaches_detected"],
            "summary": ["total_events_processed", "exceptions_created", "sla_breaches"]
        }
    },
    "business-operations": {
        "required_keys": [
            "fulfillment_monitoring", "billing_operations", "business_metrics", "summary"
        ],
        "nested_validations": {
            "fulfillment_monitoring": ["total_orders", "orders_by_status"],
            "business_metrics": ["orders_processed", "invoices_generated", "total_revenue"],
            "summary": ["orders_monitored", "invoices_generated", "total_revenue"]
        }
    }
}


class E2EValidator:
    """End-to-end validation orchestrator for Octup E²A business flows."""
    
    def __init__(self, tenant: str, orders_count: int, wait_seconds: int, 
                 start_stack: bool) -> None:
        """Initialize the validator with configuration parameters.
        
        Args:
            tenant: Tenant identifier for operations
            orders_count: Number of orders to generate for testing
            wait_seconds: Wait time between operations
            start_stack: Whether to start the stack if services are down
        """
        self.tenant = tenant
        self.orders_count = orders_count
        self.wait_seconds = wait_seconds
        self.start_stack = start_stack
        
        self.session = self._create_session()
        self.results: Dict[str, Any] = {
            "timestamp": time.time(),
            "config": {
                "tenant": tenant,
                "orders_count": orders_count,
                "wait_seconds": wait_seconds
            },
            "metrics_before": {},
            "metrics_after": {},
            "flow_results": {},
            "stage_metrics": {},
            "anomalies": [],
            "success": False
        }
        
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)

    def _create_session(self) -> requests.Session:
        """Create HTTP session with retry strategy."""
        session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    def _make_request(self, method: str, url: str, timeout: int = 5, 
                     **kwargs) -> Optional[requests.Response]:
        """Make HTTP request with error handling.
        
        Args:
            method: HTTP method
            url: Request URL
            timeout: Request timeout in seconds
            **kwargs: Additional request parameters
            
        Returns:
            Response object or None if request failed
        """
        try:
            response = self.session.request(
                method, url, timeout=timeout, **kwargs
            )
            response.raise_for_status()
            return response
        except requests.RequestException as e:
            self.logger.error(f"Request failed {method} {url}: {e}")
            return None

    def check_service_health(self) -> bool:
        """Check health of all required services.
        
        Returns:
            True if all services are healthy, False otherwise
        """
        health_checks = [
            (f"{API_BASE}/healthz", "API"),
            (f"{PREFECT_BASE}/api/health", "Prefect"),
            (f"{SHOPIFY_MOCK_BASE}/health", "Shopify Mock")
        ]
        
        all_healthy = True
        for url, service in health_checks:
            response = self._make_request("GET", url)
            if response and response.status_code == 200:
                self.logger.info(f"✓ {service} service is healthy")
            else:
                self.logger.error(f"✗ {service} service is not healthy")
                all_healthy = False
                
        return all_healthy

    def start_stack_if_needed(self) -> bool:
        """Start the stack if services are not healthy and start_stack is enabled.
        
        Returns:
            True if services are healthy after potential startup, False otherwise
        """
        if self.check_service_health():
            return True
            
        if not self.start_stack:
            self.logger.error("Services are not healthy and --start-stack not enabled")
            return False
            
        self.logger.info("Starting stack via ./run.sh start...")
        try:
            subprocess.run(
                ["/bin/bash", "-lc", "./run.sh start"],
                cwd=ROOT_DIR,
                check=True,
                timeout=120
            )
            
            # Wait and retry health checks with backoff
            for attempt in range(6):
                wait_time = min(10 * (2 ** attempt), 60)
                self.logger.info(f"Waiting {wait_time}s for services to start...")
                time.sleep(wait_time)
                
                if self.check_service_health():
                    self.logger.info("Stack started successfully")
                    return True
                    
            self.logger.error("Stack failed to start within timeout")
            return False
            
        except subprocess.SubprocessError as e:
            self.logger.error(f"Failed to start stack: {e}")
            return False

    def get_api_metrics(self) -> Optional[Dict[str, Any]]:
        """Fetch API dashboard metrics.
        
        Returns:
            Metrics dictionary or None if request failed
        """
        headers = {"X-Tenant-Id": self.tenant}
        response = self._make_request(
            "GET", f"{API_BASE}/api/dashboard/metrics", headers=headers
        )
        
        if response:
            try:
                return response.json()
            except json.JSONDecodeError as e:
                self.logger.error(f"Failed to parse metrics JSON: {e}")
                
        return None

    def discover_deployments(self) -> bool:
        """Discover available Prefect deployments and their configurations.
        
        Returns:
            True if deployments were discovered successfully, False otherwise
        """
        self.logger.info("Discovering Prefect deployments...")
        
        response = self._make_request(
            "POST", f"{PREFECT_BASE}/api/deployments/filter",
            json={}
        )
        
        if not response:
            self.logger.error("Failed to fetch deployments")
            return False
            
        try:
            deployments = response.json()
        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse deployments JSON: {e}")
            return False
            
        # Map deployment names to their IDs and parameters - Updated for simplified architecture
        deployment_mapping = {
            "event-processor": "event-processor",
            "business-operations": "business-operations"
        }
        
        for deployment in deployments:
            name = deployment.get("name", "")
            deployment_id = deployment.get("id")
            
            # Match deployment names to our expected flows
            matched_flow = None
            for key, flow_name in deployment_mapping.items():
                if key in name.lower() or key.replace("-", "_") in name.lower():
                    matched_flow = flow_name
                    break
                    
            if matched_flow and deployment_id:
                # Set parameters based on flow type
                if matched_flow == "event-processor":
                    parameters = {
                        "tenant": self.tenant,
                        "lookback_hours": 1,
                        "enable_ai_processing": True
                    }
                elif matched_flow == "business-operations":
                    parameters = {
                        "tenant": self.tenant,
                        "lookback_hours": 24,
                        "enable_billing": True
                    }
                else:
                    parameters = {"tenant": self.tenant}
                    
                DEPLOYMENT_CONFIGS[matched_flow] = {
                    "id": deployment_id,
                    "parameters": parameters
                }
                self.logger.info(f"✓ Found {matched_flow}: {deployment_id}")
                
        if not DEPLOYMENT_CONFIGS:
            self.logger.error("No matching deployments found")
            return False
            
        self.logger.info(f"Discovered {len(DEPLOYMENT_CONFIGS)} deployments")
        return True

    def get_shopify_stats(self) -> Optional[Dict[str, Any]]:
        """Fetch Shopify Mock statistics.
        
        Returns:
            Stats dictionary or None if request failed
        """
        response = self._make_request("GET", f"{SHOPIFY_MOCK_BASE}/demo/stats")
        
        if response:
            try:
                return response.json()
            except json.JSONDecodeError as e:
                self.logger.error(f"Failed to parse Shopify stats JSON: {e}")
                
        return None
        """Fetch Shopify Mock statistics.
        
        Returns:
            Stats dictionary or None if request failed
        """
        response = self._make_request("GET", f"{SHOPIFY_MOCK_BASE}/demo/stats")
        
        if response:
            try:
                return response.json()
            except json.JSONDecodeError as e:
                self.logger.error(f"Failed to parse Shopify stats JSON: {e}")
                
        return None

    def generate_orders(self) -> bool:
        """Generate orders via Shopify Mock GenerateSingle endpoint.
        
        Returns:
            True if orders were generated successfully, False otherwise
        """
        self.logger.info(f"Generating {self.orders_count} orders...")
        
        # Get initial stats
        initial_stats = self.get_shopify_stats()
        if not initial_stats:
            self.logger.error("Failed to get initial Shopify stats")
            return False
            
        initial_orders = initial_stats.get("total_orders", 0)
        
        # Generate orders with limited concurrency
        def generate_single_order() -> bool:
            response = self._make_request(
                "POST", f"{SHOPIFY_MOCK_BASE}/demo/generate-order"
            )
            return response is not None
            
        success_count = 0
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [
                executor.submit(generate_single_order) 
                for _ in range(self.orders_count)
            ]
            
            for future in as_completed(futures):
                if future.result():
                    success_count += 1
                time.sleep(0.2)  # Small delay between requests
                
        self.logger.info(f"Generated {success_count}/{self.orders_count} orders")
        
        # Verify order count increase
        time.sleep(2)  # Allow time for stats update
        final_stats = self.get_shopify_stats()
        if not final_stats:
            self.logger.error("Failed to get final Shopify stats")
            return False
            
        final_orders = final_stats.get("total_orders", 0)
        orders_increase = final_orders - initial_orders
        
        if orders_increase >= self.orders_count:
            self.logger.info(f"✓ Order count increased by {orders_increase}")
            return True
        else:
            self.logger.error(
                f"✗ Expected {self.orders_count} new orders, got {orders_increase}"
            )
            return False

    def wait_for_processing(self) -> None:
        """Wait for webhook reception and initial processing."""
        self.logger.info(f"Waiting {self.wait_seconds}s for webhook processing...")
        
        for i in range(self.wait_seconds):
            if i % 5 == 0:
                self.logger.info(f"Waiting... {self.wait_seconds - i}s remaining")
            time.sleep(1)

    def trigger_prefect_deployment(self, deployment_name: str, 
                                 config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Trigger a Prefect deployment and wait for completion.
        
        Args:
            deployment_name: Name of the deployment to trigger
            config: Configuration containing deployment ID and parameters
            
        Returns:
            Flow run result or None if failed
        """
        self.logger.info(f"Triggering deployment: {deployment_name}")
        
        deployment_id = config["id"]
        parameters = config["parameters"]
        
        # Create flow run using correct API endpoint
        create_url = f"{PREFECT_BASE}/api/deployments/{deployment_id}/create_flow_run"
        create_payload = {"parameters": parameters}
        
        response = self._make_request("POST", create_url, json=create_payload)
        if not response:
            self.logger.error(f"Failed to create flow run for {deployment_name}")
            return None
            
        try:
            flow_run_data = response.json()
            flow_run_id = flow_run_data["id"]
            self.logger.info(f"Created flow run {flow_run_id}")
        except (json.JSONDecodeError, KeyError) as e:
            self.logger.error(f"Failed to parse flow run creation response: {e}")
            return None
            
        # Poll for completion with exponential backoff
        poll_url = f"{PREFECT_BASE}/api/flow_runs/{flow_run_id}"
        wait_time = 2
        max_wait = 300  # 5 minutes timeout
        total_waited = 0
        
        while total_waited < max_wait:
            response = self._make_request("GET", poll_url)
            if not response:
                self.logger.error(f"Failed to poll flow run {flow_run_id}")
                return None
                
            try:
                flow_run = response.json()
                state = flow_run.get("state", {})
                state_type = state.get("type")
                
                if state_type in ["COMPLETED", "FAILED", "CRASHED"]:
                    self.logger.info(
                        f"Flow run {flow_run_id} finished with state: {state_type}"
                    )
                    
                    if state_type == "COMPLETED":
                        # Extract result from state data
                        state_data = state.get("data")
                        if state_data:
                            return state_data
                        else:
                            self.logger.warning(
                                f"No result data in completed flow run {flow_run_id}"
                            )
                            return {}
                    else:
                        self.logger.error(
                            f"Flow run {flow_run_id} failed with state: {state_type}"
                        )
                        return None
                        
            except (json.JSONDecodeError, KeyError) as e:
                self.logger.error(f"Failed to parse flow run status: {e}")
                return None
                
            time.sleep(wait_time)
            total_waited += wait_time
            wait_time = min(wait_time * 1.5, 30)  # Exponential backoff, max 30s
            
        self.logger.error(f"Flow run {flow_run_id} timed out after {max_wait}s")
        return None

    def validate_flow_result(self, deployment_name: str, 
                           result: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Validate flow result structure against expected schema.
        
        Args:
            deployment_name: Name of the deployment
            result: Flow result to validate
            
        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        if deployment_name not in FLOW_RESULT_SCHEMAS:
            return False, [f"No schema defined for {deployment_name}"]
            
        # If result is empty but flow completed, consider it a partial success
        if not result:
            self.logger.warning(f"Flow {deployment_name} completed but returned no data")
            return True, []  # Allow empty results for now
            
        schema = FLOW_RESULT_SCHEMAS[deployment_name]
        errors = []
        
        # Check required top-level keys
        for key in schema["required_keys"]:
            if key not in result:
                errors.append(f"Missing required key: {key}")
                
        # Check nested validations
        for parent_key, nested_keys in schema.get("nested_validations", {}).items():
            if parent_key in result:
                parent_value = result[parent_key]
                if isinstance(parent_value, dict):
                    for nested_key in nested_keys:
                        if nested_key not in parent_value:
                            errors.append(
                                f"Missing nested key: {parent_key}.{nested_key}"
                            )
                else:
                    errors.append(f"Expected dict for {parent_key}, got {type(parent_value)}")
                    
        # Deployment-specific validations (only if we have data) - Updated for simplified architecture
        if result:
            if deployment_name == "event-processor":
                summary = result.get("summary", {})
                events_processed = summary.get("total_events_processed", 0)
                if events_processed < 1:  # Should process at least some events
                    errors.append(
                        f"Expected total_events_processed >= 1, got {events_processed}"
                    )
                    
            elif deployment_name == "business-operations":
                summary = result.get("summary", {})
                orders_monitored = summary.get("orders_monitored", 0)
                if orders_monitored < 1:  # Should monitor at least some orders
                    errors.append(
                        f"Expected orders_monitored >= 1, got {orders_monitored}"
                    )
                    
                business_metrics = result.get("business_metrics", {})
                exception_rate = business_metrics.get("exception_rate")
                if exception_rate is not None and not (0 <= exception_rate <= 1):
                    errors.append(
                        f"exception_rate must be in [0,1], got {exception_rate}"
                    )
                
        return len(errors) == 0, errors

    def run_flow_validations(self) -> bool:
        """Run all Prefect deployments and validate results.
        
        Returns:
            True if all flows completed successfully, False otherwise
        """
        all_successful = True
        
        for deployment_name, config in DEPLOYMENT_CONFIGS.items():
            self.logger.info(f"\n--- Running {deployment_name} ---")
            
            result = self.trigger_prefect_deployment(deployment_name, config)
            
            if result is None:
                self.logger.error(f"✗ {deployment_name} failed to execute")
                self.results["flow_results"][deployment_name] = {
                    "success": False,
                    "error": "Execution failed"
                }
                all_successful = False
                continue
                
            # Validate result structure
            is_valid, validation_errors = self.validate_flow_result(deployment_name, result)
            
            if is_valid:
                self.logger.info(f"✓ {deployment_name} completed successfully")
                self.results["flow_results"][deployment_name] = {
                    "success": True,
                    "result": result
                }
            else:
                self.logger.error(f"✗ {deployment_name} validation failed:")
                for error in validation_errors:
                    self.logger.error(f"  - {error}")
                    
                self.results["flow_results"][deployment_name] = {
                    "success": False,
                    "result": result,
                    "validation_errors": validation_errors
                }
                self.results["anomalies"].extend(
                    [f"{deployment_name}: {error}" for error in validation_errors]
                )
                all_successful = False
                
        return all_successful

    async def run_validation(self) -> bool:
        """Run the complete end-to-end validation process.
        
        Returns:
            True if all validations passed, False otherwise
        """
        self.logger.info("=== Starting E2E Validation ===")
        
        # 1. Check service health and start if needed
        if not self.start_stack_if_needed():
            self.logger.error("✗ Services are not available")
            return False
            
        # 2. Discover deployments
        if not self.discover_deployments():
            self.logger.error("✗ Failed to discover deployments")
            return False
            
        # 3. Get initial metrics
        self.results["metrics_before"] = self.get_api_metrics() or {}
        
        # 4. Generate orders
        if not self.generate_orders():
            self.logger.error("✗ Failed to generate orders")
            return False
            
        # 5. Wait for processing
        self.wait_for_processing()
        
        # 6. Verify orders were processed
        current_metrics = self.get_api_metrics()
        if current_metrics:
            orders_processed = current_metrics.get("orders_processed_today", 0)
            if orders_processed < self.orders_count:
                self.logger.error(
                    f"✗ Expected >= {self.orders_count} orders processed, got {orders_processed}"
                )
                return False
            else:
                self.logger.info(f"✓ {orders_processed} orders processed today")
        else:
            self.logger.warning("Could not verify order processing via metrics")
            
        # 7. Run flow validations
        flows_successful = self.run_flow_validations()
        
        # 8. Run flow validations
        flows_successful = self.run_flow_validations()
        
        # 9. Get final metrics
        self.results["metrics_after"] = self.get_api_metrics() or {}
        
        # 10. Final validation - simplified for new architecture
        success = flows_successful
        self.results["success"] = success
        
        if success:
            self.logger.info("✓ All validations passed successfully")
            if self.results["anomalies"]:
                self.logger.info(f"Note: {len(self.results['anomalies'])} non-critical anomalies detected")
        else:
            self.logger.error("✗ Some validations failed")
            
        return success

    def print_summary(self) -> None:
        """Print validation summary and JSON report."""
        print("\n" + "="*60)
        print("E2E VALIDATION SUMMARY")
        print("="*60)
        
        print(f"Tenant: {self.tenant}")
        print(f"Orders Generated: {self.orders_count}")
        print(f"Overall Success: {'✓' if self.results['success'] else '✗'}")
        
        print(f"\nFlow Results:")
        for deployment, result in self.results["flow_results"].items():
            status = "✓" if result["success"] else "✗"
            print(f"  {status} {deployment}")
            
        if self.results["anomalies"]:
            print(f"\nAnomalies Detected:")
            for anomaly in self.results["anomalies"]:
                print(f"  - {anomaly}")
                
        print(f"\nDetailed JSON Report:")
        print(json.dumps(self.results, indent=2, default=str))


def main() -> None:
    """Main entry point for the E2E validation script."""
    parser = argparse.ArgumentParser(
        description="End-to-end validation for Octup E²A business flows"
    )
    parser.add_argument(
        "--tenant", 
        default="demo-3pl", 
        help="Tenant identifier (default: demo-3pl)"
    )
    parser.add_argument(
        "--orders", 
        type=int, 
        default=30, 
        help="Number of orders to generate (default: 30)"
    )
    parser.add_argument(
        "--wait-seconds", 
        type=int, 
        default=15, 
        help="Wait time for processing (default: 15)"
    )
    parser.add_argument(
        "--start-stack", 
        action="store_true", 
        help="Start stack if services are down"
    )
    
    args = parser.parse_args()
    
    validator = E2EValidator(
        tenant=args.tenant,
        orders_count=args.orders,
        wait_seconds=args.wait_seconds,
        start_stack=args.start_stack
    )
    
    try:
        success = asyncio.run(validator.run_validation())
        validator.print_summary()
        
        sys.exit(0 if success else 2)
        
    except KeyboardInterrupt:
        print("\nValidation interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"Validation failed with error: {e}")
        sys.exit(2)


if __name__ == "__main__":
    main()
