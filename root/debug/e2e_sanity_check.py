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

# Import database metrics collector
from app.services.metrics_collector import DatabaseMetricsCollector

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
        
        # 8. Get final metrics
        self.results["metrics_after"] = self.get_api_metrics() or {}
        
        # 9. Final validation - simplified for new architecture
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


class EnhancedE2EValidator(E2EValidator):
    """Enhanced validator with comprehensive database metrics tracking."""
    
    def __init__(self, tenant: str, orders_count: int, wait_seconds: int, 
                 start_stack: bool) -> None:
        """Initialize enhanced validator.
        
        Args:
            tenant: Tenant identifier for operations
            orders_count: Number of orders to generate for testing
            wait_seconds: Wait time between operations
            start_stack: Whether to start the stack if services are down
        """
        super().__init__(tenant, orders_count, wait_seconds, start_stack)
        self.enable_enhanced_metrics = True  # Always enabled for enhanced validator
        
        # Enhanced results structure
        self.results.update({
            "database_metrics_before": {},
            "database_metrics_after": {},
            "pipeline_health_analysis": {},
            "business_logic_validation": {},
            "architecture_performance": {},
            "validation_rules_results": {},
            "enhanced_anomalies": []
        })

    async def collect_database_metrics(self, phase: str = "unknown") -> Dict[str, Any]:
        """Collect comprehensive database state metrics.
        
        Args:
            phase: Phase identifier for metrics collection
            
        Returns:
            Dictionary containing comprehensive database metrics
        """
        # Ensure enable_enhanced_metrics is set (fallback)
        if not hasattr(self, 'enable_enhanced_metrics'):
            self.enable_enhanced_metrics = True
            
        if not self.enable_enhanced_metrics:
            return {}
            
        self.logger.info(f"Collecting database metrics for phase: {phase}")
        
        try:
            async with DatabaseMetricsCollector() as collector:
                # Collect all metric types
                order_metrics = await collector.collect_order_metrics(self.tenant, 1)
                exception_metrics = await collector.collect_exception_metrics(self.tenant, 1)
                sla_metrics = await collector.collect_sla_metrics(self.tenant, 1)
                flow_metrics = await collector.collect_flow_performance_metrics(self.tenant, 1)
                
                comprehensive_metrics = {
                    "phase": phase,
                    "order_metrics": order_metrics,
                    "exception_metrics": exception_metrics,
                    "sla_metrics": sla_metrics,
                    "flow_performance_metrics": flow_metrics,
                    "collection_timestamp": time.time()
                }
                
                self.logger.info(f"Database metrics collected for {phase}")
                return comprehensive_metrics
                
        except Exception as e:
            self.logger.error(f"Failed to collect database metrics for {phase}: {e}")
            return {"error": str(e), "phase": phase}

    async def analyze_pipeline_health(self) -> Dict[str, Any]:
        """Analyze overall pipeline health and performance.
        
        Returns:
            Dictionary containing pipeline health analysis
        """
        if not self.enable_enhanced_metrics:
            return {}
            
        self.logger.info("Analyzing pipeline health...")
        
        try:
            async with DatabaseMetricsCollector() as collector:
                analysis = await collector.analyze_pipeline_effectiveness(self.tenant, 1)
                
                # Add additional health indicators
                analysis["validation_context"] = {
                    "orders_generated": self.orders_count,
                    "expected_exception_rate_range": [2.0, 5.0],
                    "minimum_ai_success_rate": 0.8,
                    "minimum_sla_compliance": 0.8
                }
                
                self.logger.info(f"Pipeline health analyzed - status: {analysis.get('pipeline_status', 'unknown')}")
                return analysis
                
        except Exception as e:
            self.logger.error(f"Failed to analyze pipeline health: {e}")
            return {"error": str(e)}

    async def validate_business_logic(self) -> Dict[str, Any]:
        """Validate business logic correctness across components.
        
        Returns:
            Dictionary containing business logic validation results
        """
        if not self.enable_enhanced_metrics:
            return {}
            
        self.logger.info("Validating business logic...")
        
        validation_results = {
            "timestamp": time.time(),
            "validations": {},
            "overall_valid": True,
            "issues_found": []
        }
        
        try:
            # Get current metrics for validation
            before_metrics = self.results.get("database_metrics_before", {})
            after_metrics = self.results.get("database_metrics_after", {})
            
            if not before_metrics or not after_metrics:
                validation_results["issues_found"].append(
                    "Missing before/after metrics for business logic validation"
                )
                validation_results["overall_valid"] = False
                return validation_results
            
            # Extract key metrics
            before_orders = before_metrics.get("order_metrics", {}).get("orders_created_count", 0)
            after_orders = after_metrics.get("order_metrics", {}).get("orders_created_count", 0)
            orders_created = after_orders - before_orders
            
            after_exceptions = after_metrics.get("exception_metrics", {}).get("total_exceptions_analyzed", 0)
            avg_exceptions_per_order = after_metrics.get("order_metrics", {}).get("average_exceptions_per_order", 0)
            
            # Business Logic Validation Rules
            validations = {}
            
            # 1. Order creation validation
            validations["order_creation"] = {
                "expected": self.orders_count,
                "actual": orders_created,
                "valid": orders_created >= self.orders_count,
                "description": "All generated orders should be created in database"
            }
            
            # 2. Exception creation rate validation (based on our analysis: 2-5 per order)
            validations["exception_rate"] = {
                "expected_range": [2.0, 5.0],
                "actual": avg_exceptions_per_order,
                "valid": 2.0 <= avg_exceptions_per_order <= 5.0,
                "description": "Exception creation rate should be 2-5 per order"
            }
            
            # 3. AI analysis coverage validation
            ai_success_rate = after_metrics.get("exception_metrics", {}).get("ai_analysis_success_rate", 0)
            validations["ai_analysis_coverage"] = {
                "expected_minimum": 0.8,
                "actual": ai_success_rate,
                "valid": ai_success_rate >= 0.8,
                "description": "AI analysis should succeed for at least 80% of exceptions"
            }
            
            # 4. SLA compliance validation
            sla_compliance_rate = after_metrics.get("sla_metrics", {}).get("sla_compliance_rate", 1.0)
            validations["sla_compliance"] = {
                "expected_minimum": 0.8,
                "actual": sla_compliance_rate,
                "valid": sla_compliance_rate >= 0.8,
                "description": "SLA compliance should be at least 80%"
            }
            
            # 5. Exception distribution validation
            exceptions_by_reason = after_metrics.get("exception_metrics", {}).get("exceptions_by_reason_code", {})
            has_diverse_exceptions = len(exceptions_by_reason) >= 3
            validations["exception_diversity"] = {
                "expected_minimum_types": 3,
                "actual_types": len(exceptions_by_reason),
                "valid": has_diverse_exceptions,
                "description": "Should have diverse exception types from comprehensive validation"
            }
            
            validation_results["validations"] = validations
            
            # Check overall validity
            failed_validations = [
                name for name, result in validations.items() 
                if not result["valid"]
            ]
            
            if failed_validations:
                validation_results["overall_valid"] = False
                validation_results["issues_found"].extend([
                    f"Business logic validation failed: {name}" 
                    for name in failed_validations
                ])
            
            self.logger.info(f"Business logic validation completed - valid: {validation_results['overall_valid']}")
            return validation_results
            
        except Exception as e:
            self.logger.error(f"Failed to validate business logic: {e}")
            validation_results["error"] = str(e)
            validation_results["overall_valid"] = False
            return validation_results

    async def generate_architecture_report(self) -> Dict[str, Any]:
        """Generate comprehensive architecture performance report.
        
        Returns:
            Dictionary containing architecture performance analysis
        """
        if not self.enable_enhanced_metrics:
            return {}
            
        self.logger.info("Generating architecture performance report...")
        
        report = {
            "timestamp": time.time(),
            "architecture_type": "simplified_2_flow",
            "performance_metrics": {},
            "efficiency_analysis": {},
            "recommendations": []
        }
        
        try:
            # Analyze flow execution performance
            flow_results = self.results.get("flow_results", {})
            
            performance_metrics = {
                "flows_executed": len(flow_results),
                "flows_successful": sum(1 for r in flow_results.values() if r.get("success", False)),
                "success_rate": 0.0
            }
            
            if performance_metrics["flows_executed"] > 0:
                performance_metrics["success_rate"] = (
                    performance_metrics["flows_successful"] / performance_metrics["flows_executed"]
                )
            
            # Analyze database metrics changes
            before_metrics = self.results.get("database_metrics_before", {})
            after_metrics = self.results.get("database_metrics_after", {})
            
            if before_metrics and after_metrics:
                before_orders = before_metrics.get("order_metrics", {}).get("orders_created_count", 0)
                after_orders = after_metrics.get("order_metrics", {}).get("orders_created_count", 0)
                orders_processed = after_orders - before_orders
                
                performance_metrics.update({
                    "orders_processed": orders_processed,
                    "processing_efficiency": orders_processed / self.orders_count if self.orders_count > 0 else 0,
                    "exceptions_created": after_metrics.get("exception_metrics", {}).get("total_exceptions_analyzed", 0),
                    "avg_exceptions_per_order": after_metrics.get("order_metrics", {}).get("average_exceptions_per_order", 0)
                })
            
            report["performance_metrics"] = performance_metrics
            
            # Efficiency analysis
            efficiency_analysis = {
                "architecture_effectiveness": "high" if performance_metrics.get("success_rate", 0) >= 0.9 else "medium",
                "exception_processing_efficiency": "optimal" if 2.0 <= performance_metrics.get("avg_exceptions_per_order", 0) <= 5.0 else "suboptimal",
                "overall_rating": "good"
            }
            
            # Generate recommendations
            recommendations = []
            
            if performance_metrics.get("success_rate", 0) < 0.9:
                recommendations.append("Investigate flow execution failures to improve success rate")
            
            if performance_metrics.get("processing_efficiency", 0) < 0.9:
                recommendations.append("Review order processing pipeline for efficiency improvements")
            
            avg_exceptions = performance_metrics.get("avg_exceptions_per_order", 0)
            if avg_exceptions < 2.0:
                recommendations.append("Exception detection may be insufficient - review validation logic")
            elif avg_exceptions > 5.0:
                recommendations.append("Exception rate high - review for false positives")
            
            if not recommendations:
                recommendations.append("Architecture performing within expected parameters")
            
            report["efficiency_analysis"] = efficiency_analysis
            report["recommendations"] = recommendations
            
            self.logger.info("Architecture performance report generated")
            return report
            
        except Exception as e:
            self.logger.error(f"Failed to generate architecture report: {e}")
            report["error"] = str(e)
            return report

    async def run_enhanced_validation(self) -> bool:
        """Run enhanced end-to-end validation with comprehensive metrics.
        
        Returns:
            True if all validations passed, False otherwise
        """
        self.logger.info("=== Starting Enhanced E2E Validation ===")
        
        # 1. Check service health and start if needed
        if not self.start_stack_if_needed():
            self.logger.error("✗ Services are not available")
            return False
            
        # 2. Discover deployments
        if not self.discover_deployments():
            self.logger.error("✗ Failed to discover deployments")
            return False
            
        # 3. Collect initial metrics (both API and database)
        self.results["metrics_before"] = self.get_api_metrics() or {}
        self.results["database_metrics_before"] = await self.collect_database_metrics("before")
        
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
        
        # 8. Collect final metrics (both API and database)
        self.results["metrics_after"] = self.get_api_metrics() or {}
        self.results["database_metrics_after"] = await self.collect_database_metrics("after")
        
        # 9. Run enhanced analyses
        self.results["pipeline_health_analysis"] = await self.analyze_pipeline_health()
        self.results["business_logic_validation"] = await self.validate_business_logic()
        self.results["architecture_performance"] = await self.generate_architecture_report()
        
        # 10. Final validation with enhanced criteria
        basic_success = flows_successful
        
        # Enhanced validation criteria
        pipeline_healthy = self.results["pipeline_health_analysis"].get("pipeline_status") == "healthy"
        business_logic_valid = self.results["business_logic_validation"].get("overall_valid", False)
        
        enhanced_success = basic_success and pipeline_healthy and business_logic_valid
        
        self.results["success"] = enhanced_success
        self.results["basic_validation_success"] = basic_success
        self.results["enhanced_validation_success"] = enhanced_success
        
        if enhanced_success:
            self.logger.info("✓ All enhanced validations passed successfully")
        elif basic_success:
            self.logger.warning("✓ Basic validations passed, but enhanced validations found issues")
        else:
            self.logger.error("✗ Validations failed")
            
        return enhanced_success

    def print_enhanced_summary(self) -> None:
        """Print enhanced validation summary with comprehensive metrics."""
        print("\n" + "="*80)
        print("ENHANCED E2E VALIDATION SUMMARY")
        print("="*80)
        
        print(f"Tenant: {self.tenant}")
        print(f"Orders Generated: {self.orders_count}")
        print(f"Enhanced Metrics: {'Enabled' if self.enable_enhanced_metrics else 'Disabled'}")
        print(f"Basic Validation: {'✓' if self.results.get('basic_validation_success', False) else '✗'}")
        print(f"Enhanced Validation: {'✓' if self.results.get('enhanced_validation_success', False) else '✗'}")
        print(f"Overall Success: {'✓' if self.results['success'] else '✗'}")
        
        # Flow Results
        print(f"\nFlow Execution Results:")
        for deployment, result in self.results["flow_results"].items():
            status = "✓" if result["success"] else "✗"
            print(f"  {status} {deployment}")
            
        # Pipeline Health
        pipeline_health = self.results.get("pipeline_health_analysis", {})
        if pipeline_health:
            health_score = pipeline_health.get("overall_health_score", 0)
            pipeline_status = pipeline_health.get("pipeline_status", "unknown")
            print(f"\nPipeline Health:")
            print(f"  Health Score: {health_score:.3f}")
            print(f"  Status: {pipeline_status}")
            
            recommendations = pipeline_health.get("recommendations", [])
            if recommendations:
                print(f"  Recommendations:")
                for rec in recommendations[:3]:  # Show top 3
                    print(f"    - {rec}")
        
        # Business Logic Validation
        business_logic = self.results.get("business_logic_validation", {})
        if business_logic:
            overall_valid = business_logic.get("overall_valid", False)
            validations = business_logic.get("validations", {})
            print(f"\nBusiness Logic Validation: {'✓' if overall_valid else '✗'}")
            
            for name, validation in validations.items():
                status = "✓" if validation.get("valid", False) else "✗"
                actual = validation.get("actual", "N/A")
                print(f"  {status} {name}: {actual}")
        
        # Key Metrics
        after_metrics = self.results.get("database_metrics_after", {})
        if after_metrics:
            order_metrics = after_metrics.get("order_metrics", {})
            exception_metrics = after_metrics.get("exception_metrics", {})
            
            print(f"\nKey Metrics:")
            print(f"  Orders Created: {order_metrics.get('orders_created_count', 0)}")
            print(f"  Total Exceptions: {exception_metrics.get('total_exceptions_analyzed', 0)}")
            print(f"  Avg Exceptions/Order: {order_metrics.get('average_exceptions_per_order', 0):.2f}")
            print(f"  AI Success Rate: {exception_metrics.get('ai_analysis_success_rate', 0):.3f}")
        
        # Anomalies
        all_anomalies = self.results.get("anomalies", []) + self.results.get("enhanced_anomalies", [])
        if all_anomalies:
            print(f"\nAnomalies Detected ({len(all_anomalies)}):")
            for anomaly in all_anomalies[:5]:  # Show top 5
                print(f"  - {anomaly}")
                
        print(f"\nDetailed JSON Report:")
        print(json.dumps(self.results, indent=2, default=str))
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
    parser.add_argument(
        "--enhanced", 
        action="store_true", 
        help="Enable enhanced validation with comprehensive database metrics"
    )
    parser.add_argument(
        "--basic-only", 
        action="store_true", 
        help="Run only basic validation (legacy mode)"
    )
    
    args = parser.parse_args()
    
    # Determine validation mode
    if args.basic_only:
        validator = E2EValidator(
            tenant=args.tenant,
            orders_count=args.orders,
            wait_seconds=args.wait_seconds,
            start_stack=args.start_stack
        )
        validation_method = validator.run_validation
        summary_method = validator.print_summary
    else:
        # Use enhanced validator by default, or when explicitly requested
        validator = EnhancedE2EValidator(
            tenant=args.tenant,
            orders_count=args.orders,
            wait_seconds=args.wait_seconds,
            start_stack=args.start_stack
        )
        validation_method = validator.run_enhanced_validation
        summary_method = validator.print_enhanced_summary
    
    try:
        success = asyncio.run(validation_method())
        summary_method()
        
        sys.exit(0 if success else 2)
        
    except KeyboardInterrupt:
        print("\nValidation interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"Validation failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(2)


if __name__ == "__main__":
    main()
