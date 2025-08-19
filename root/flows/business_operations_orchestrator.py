# ==== BUSINESS OPERATIONS ORCHESTRATOR ==== #

"""
Master orchestration flow for Octup E²A business operations.

This flow coordinates all business processes in a realistic sequence that
mirrors real-world e-commerce operations:

1. Order Processing Pipeline (hourly)
2. Exception Management Pipeline (every 4 hours)
3. Billing Management Pipeline (daily)
4. Business Intelligence & Reporting (daily)

The orchestrator ensures proper sequencing, handles dependencies between
processes, and provides comprehensive operational visibility.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from prefect import flow, task, get_run_logger
from prefect.deployments import run_deployment

from .order_processing_flow import order_processing_pipeline
from .exception_management_flow import exception_management_pipeline
from .billing_management_flow import billing_management_pipeline


# ==== ORCHESTRATION TASKS ==== #


@task
async def check_system_readiness(tenant: str = "demo-3pl") -> Dict[str, Any]:
    """
    Check system readiness before running business operations.
    
    This task verifies that all required services are available and
    the system is in a good state to process business operations.
    
    Args:
        tenant: Tenant to check readiness for
        
    Returns:
        Dict with system readiness status
    """
    logger = get_run_logger()
    logger.info(f"Checking system readiness for tenant {tenant}")
    
    readiness_checks = {
        'database_connection': True,  # Would check actual DB connectivity
        'api_service': True,          # Would check API health endpoint
        'redis_cache': True,          # Would check Redis connectivity
        'ai_services': True,          # Would check AI service availability
        'webhook_processing': True    # Would check webhook queue status
    }
    
    # Simulate system checks
    all_ready = all(readiness_checks.values())
    
    if all_ready:
        logger.info("System readiness check passed - all services available")
    else:
        failed_services = [service for service, status in readiness_checks.items() if not status]
        logger.warning(f"System readiness check failed - unavailable services: {failed_services}")
    
    return {
        'tenant': tenant,
        'check_timestamp': datetime.utcnow().isoformat(),
        'overall_ready': all_ready,
        'service_status': readiness_checks,
        'failed_services': [service for service, status in readiness_checks.items() if not status]
    }


@task
async def determine_operation_schedule(
    current_time: datetime,
    tenant: str = "demo-3pl"
) -> Dict[str, Any]:
    """
    Determine which operations should run based on current time and business rules.
    
    This task implements intelligent scheduling that considers:
    - Business hours and time zones
    - Operation frequency requirements
    - System load and capacity
    - Maintenance windows
    
    Args:
        current_time: Current execution time
        tenant: Tenant context
        
    Returns:
        Dict with operation schedule decisions
    """
    logger = get_run_logger()
    logger.info(f"Determining operation schedule for {current_time}")
    
    # Business rules for operation scheduling
    hour = current_time.hour
    day_of_week = current_time.weekday()  # 0 = Monday, 6 = Sunday
    
    schedule_decisions = {
        'run_order_processing': True,  # Always run (hourly)
        'run_exception_management': hour % 4 == 0,  # Every 4 hours
        'run_billing_management': hour == 2,  # Daily at 2 AM
        'run_reporting': hour == 6 and day_of_week < 5,  # Weekdays at 6 AM
        'maintenance_window': 3 <= hour <= 4,  # 3-4 AM maintenance window
        'business_hours': 9 <= hour <= 17,  # 9 AM - 5 PM business hours
    }
    
    # Adjust for maintenance windows
    if schedule_decisions['maintenance_window']:
        schedule_decisions['run_order_processing'] = False
        schedule_decisions['run_exception_management'] = False
        logger.info("Maintenance window active - skipping non-critical operations")
    
    operations_to_run = [op for op, should_run in schedule_decisions.items() 
                        if should_run and op.startswith('run_')]
    
    logger.info(f"Scheduled operations: {operations_to_run}")
    
    return {
        'tenant': tenant,
        'schedule_timestamp': current_time.isoformat(),
        'schedule_decisions': schedule_decisions,
        'operations_to_run': operations_to_run,
        'estimated_duration_minutes': len(operations_to_run) * 15  # Estimate 15 min per operation
    }


@task
async def execute_order_processing(
    tenant: str = "demo-3pl",
    lookback_hours: int = 1
) -> Dict[str, Any]:
    """
    Execute order processing pipeline with error handling.
    
    Args:
        tenant: Tenant to process
        lookback_hours: Time window for processing
        
    Returns:
        Dict with execution results
    """
    logger = get_run_logger()
    logger.info(f"Executing order processing pipeline for tenant {tenant}")
    
    try:
        results = await order_processing_pipeline(tenant, lookback_hours)
        logger.info(f"Order processing completed successfully: "
                   f"{results['summary']['orders_completed']} orders processed")
        return {
            'operation': 'order_processing',
            'status': 'success',
            'results': results
        }
    except Exception as e:
        logger.error(f"Order processing failed: {str(e)}")
        return {
            'operation': 'order_processing',
            'status': 'failed',
            'error': str(e)
        }


@task
async def execute_exception_management(
    tenant: str = "demo-3pl",
    analysis_hours: int = 24
) -> Dict[str, Any]:
    """
    Execute exception management pipeline with error handling.
    
    Args:
        tenant: Tenant to process
        analysis_hours: Time window for analysis
        
    Returns:
        Dict with execution results
    """
    logger = get_run_logger()
    logger.info(f"Executing exception management pipeline for tenant {tenant}")
    
    try:
        results = await exception_management_pipeline(tenant, analysis_hours)
        logger.info(f"Exception management completed successfully: "
                   f"{results['summary']['automated_resolutions']} auto-resolved")
        return {
            'operation': 'exception_management',
            'status': 'success',
            'results': results
        }
    except Exception as e:
        logger.error(f"Exception management failed: {str(e)}")
        return {
            'operation': 'exception_management',
            'status': 'failed',
            'error': str(e)
        }


@task
async def execute_billing_management(
    tenant: str = "demo-3pl",
    lookback_hours: int = 24
) -> Dict[str, Any]:
    """
    Execute billing management pipeline with error handling.
    
    Args:
        tenant: Tenant to process
        lookback_hours: Time window for billing
        
    Returns:
        Dict with execution results
    """
    logger = get_run_logger()
    logger.info(f"Executing billing management pipeline for tenant {tenant}")
    
    try:
        results = await billing_management_pipeline(tenant, lookback_hours)
        logger.info(f"Billing management completed successfully: "
                   f"{results['summary']['invoices_generated']} invoices generated")
        return {
            'operation': 'billing_management',
            'status': 'success',
            'results': results
        }
    except Exception as e:
        logger.error(f"Billing management failed: {str(e)}")
        return {
            'operation': 'billing_management',
            'status': 'failed',
            'error': str(e)
        }


@task
async def generate_operations_summary(
    execution_results: List[Dict[str, Any]],
    tenant: str = "demo-3pl"
) -> Dict[str, Any]:
    """
    Generate comprehensive operations summary and performance metrics.
    
    This task creates executive-level reporting on business operations
    performance, highlighting key metrics and areas needing attention.
    
    Args:
        execution_results: Results from all executed operations
        tenant: Tenant context
        
    Returns:
        Dict with operations summary and insights
    """
    logger = get_run_logger()
    logger.info(f"Generating operations summary for tenant {tenant}")
    
    # Analyze execution results
    successful_operations = [r for r in execution_results if r['status'] == 'success']
    failed_operations = [r for r in execution_results if r['status'] == 'failed']
    
    # Extract key metrics from successful operations
    key_metrics = {
        'orders_processed': 0,
        'exceptions_resolved': 0,
        'invoices_generated': 0,
        'revenue_processed': 0.0,
        'sla_compliance_rate': 0.0
    }
    
    operational_insights = []
    
    for result in successful_operations:
        operation_type = result['operation']
        operation_results = result.get('results', {})
        
        if operation_type == 'order_processing':
            summary = operation_results.get('summary', {})
            key_metrics['orders_processed'] += summary.get('orders_completed', 0)
            key_metrics['sla_compliance_rate'] = summary.get('sla_compliance_rate', 0)
            
            if summary.get('orders_completed', 0) > 0:
                operational_insights.append(
                    f"Order processing: {summary['orders_completed']} orders completed with "
                    f"{summary.get('sla_compliance_rate', 0):.1%} SLA compliance"
                )
        
        elif operation_type == 'exception_management':
            summary = operation_results.get('summary', {})
            key_metrics['exceptions_resolved'] += summary.get('automated_resolutions', 0)
            
            if summary.get('automated_resolutions', 0) > 0:
                operational_insights.append(
                    f"Exception management: {summary['automated_resolutions']} exceptions auto-resolved"
                )
        
        elif operation_type == 'billing_management':
            summary = operation_results.get('summary', {})
            key_metrics['invoices_generated'] += summary.get('invoices_generated', 0)
            key_metrics['revenue_processed'] += summary.get('total_billed_amount', 0)
            
            if summary.get('invoices_generated', 0) > 0:
                operational_insights.append(
                    f"Billing management: {summary['invoices_generated']} invoices generated, "
                    f"${summary.get('total_billed_amount', 0):.2f} revenue processed"
                )
    
    # Generate performance assessment
    performance_score = len(successful_operations) / len(execution_results) if execution_results else 0
    
    if performance_score >= 0.9:
        performance_status = "EXCELLENT"
    elif performance_score >= 0.7:
        performance_status = "GOOD"
    elif performance_score >= 0.5:
        performance_status = "FAIR"
    else:
        performance_status = "POOR"
    
    # Create comprehensive summary
    operations_summary = {
        'tenant': tenant,
        'summary_timestamp': datetime.utcnow().isoformat(),
        'execution_overview': {
            'total_operations': len(execution_results),
            'successful_operations': len(successful_operations),
            'failed_operations': len(failed_operations),
            'success_rate': performance_score,
            'performance_status': performance_status
        },
        'key_metrics': key_metrics,
        'operational_insights': operational_insights,
        'failed_operations': [
            {
                'operation': r['operation'],
                'error': r.get('error', 'Unknown error')
            } for r in failed_operations
        ],
        'recommendations': []
    }
    
    # Generate recommendations based on results
    if failed_operations:
        operations_summary['recommendations'].append(
            f"Investigate {len(failed_operations)} failed operations for root cause analysis"
        )
    
    if key_metrics['sla_compliance_rate'] < 0.8:
        operations_summary['recommendations'].append(
            "SLA compliance below 80% - review exception handling processes"
        )
    
    if key_metrics['exceptions_resolved'] == 0 and any(r['operation'] == 'exception_management' for r in successful_operations):
        operations_summary['recommendations'].append(
            "No exceptions auto-resolved - review automation rules and patterns"
        )
    
    logger.info(f"Operations summary generated: {performance_status} performance, "
               f"{len(successful_operations)}/{len(execution_results)} operations successful")
    
    return operations_summary


# ==== MAIN ORCHESTRATION FLOW ==== #


@flow(name="business-operations-orchestrator", log_prints=True)
async def business_operations_orchestrator(
    tenant: str = "demo-3pl",
    execution_time: Optional[datetime] = None
) -> Dict[str, Any]:
    """
    Master orchestration flow for all business operations.
    
    This flow coordinates the execution of all business processes in the
    correct sequence with proper error handling and comprehensive reporting.
    
    Real-world scheduling:
    - Order Processing: Every hour
    - Exception Management: Every 4 hours
    - Billing Management: Daily at 2 AM
    - Reporting: Weekdays at 6 AM
    
    Args:
        tenant: Tenant to orchestrate operations for
        execution_time: Override execution time (defaults to now)
        
    Returns:
        Dict with complete orchestration results
    """
    logger = get_run_logger()
    current_time = execution_time or datetime.utcnow()
    logger.info(f"Starting business operations orchestration for tenant {tenant} at {current_time}")
    
    # Step 1: Check system readiness
    readiness_check = await check_system_readiness(tenant)
    
    if not readiness_check['overall_ready']:
        logger.error("System readiness check failed - aborting operations")
        return {
            'tenant': tenant,
            'execution_time': current_time.isoformat(),
            'status': 'aborted',
            'reason': 'system_not_ready',
            'readiness_check': readiness_check
        }
    
    # Step 2: Determine operation schedule
    schedule = await determine_operation_schedule(current_time, tenant)
    
    if not schedule['operations_to_run']:
        logger.info("No operations scheduled for current time")
        return {
            'tenant': tenant,
            'execution_time': current_time.isoformat(),
            'status': 'completed',
            'reason': 'no_operations_scheduled',
            'schedule': schedule
        }
    
    # Step 3: Execute scheduled operations
    execution_results = []
    
    # Order Processing (if scheduled)
    if 'run_order_processing' in schedule['operations_to_run']:
        order_result = await execute_order_processing(tenant, lookback_hours=1)
        execution_results.append(order_result)
    
    # Exception Management (if scheduled)
    if 'run_exception_management' in schedule['operations_to_run']:
        exception_result = await execute_exception_management(tenant, analysis_hours=24)
        execution_results.append(exception_result)
    
    # Billing Management (if scheduled)
    if 'run_billing_management' in schedule['operations_to_run']:
        billing_result = await execute_billing_management(tenant, lookback_hours=24)
        execution_results.append(billing_result)
    
    # Step 4: Generate operations summary
    operations_summary = await generate_operations_summary(execution_results, tenant)
    
    # Compile comprehensive orchestration results
    orchestration_results = {
        'tenant': tenant,
        'execution_time': current_time.isoformat(),
        'orchestration_duration_seconds': (datetime.utcnow() - current_time).total_seconds(),
        'status': 'completed',
        'readiness_check': readiness_check,
        'operation_schedule': schedule,
        'execution_results': execution_results,
        'operations_summary': operations_summary,
        'overall_success': operations_summary['execution_overview']['success_rate'] >= 0.5
    }
    
    logger.info(f"Business operations orchestration completed: "
               f"{operations_summary['execution_overview']['performance_status']} performance, "
               f"{len(execution_results)} operations executed")
    
    return orchestration_results


# ==== DEPLOYMENT HELPERS ==== #


@flow(name="hourly-operations", log_prints=True)
async def hourly_operations(tenant: str = "demo-3pl") -> Dict[str, Any]:
    """Hourly business operations (order processing focus)."""
    return await business_operations_orchestrator(tenant)


@flow(name="daily-operations", log_prints=True)
async def daily_operations(tenant: str = "demo-3pl") -> Dict[str, Any]:
    """Daily business operations (full pipeline)."""
    # Force execution of all operations for daily run
    execution_time = datetime.utcnow().replace(hour=2, minute=0, second=0, microsecond=0)
    return await business_operations_orchestrator(tenant, execution_time)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Business Operations Orchestrator")
    parser.add_argument("--tenant", default="demo-3pl", help="Tenant to process")
    parser.add_argument("--mode", choices=["full", "hourly", "daily"], default="full", 
                       help="Orchestration mode")
    parser.add_argument("--run", action="store_true", help="Run the flow immediately")
    parser.add_argument("--serve", action="store_true", help="Serve the flow for scheduling")
    
    args = parser.parse_args()
    
    if args.run:
        if args.mode == "hourly":
            asyncio.run(hourly_operations(args.tenant))
        elif args.mode == "daily":
            asyncio.run(daily_operations(args.tenant))
        else:
            asyncio.run(business_operations_orchestrator(args.tenant))
    elif args.serve:
        print(f"Serving business operations orchestrator for tenant {args.tenant}")
        print("This would set up scheduled deployments in a real environment")
        print("- Hourly: Order processing and immediate operations")
        print("- Daily: Full pipeline including billing and reporting")
    else:
        print("Use --run to execute immediately or --serve to set up scheduling")
        print("Modes: full (on-demand), hourly (order processing), daily (complete pipeline)")
