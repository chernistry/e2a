"""CLI commands for processing stage management."""

import click
from typing import Optional
from tabulate import tabulate

from app.storage.db import get_session
from app.services.processing_stage_service import ProcessingStageService, DataCompletenessService
import logging

logger = logging.getLogger(__name__)

logger = get_logger(__name__)


@click.group()
def processing_stages():
    """Processing stage management commands."""
    pass


@processing_stages.command()
@click.option('--tenant', required=True, help='Tenant name')
@click.option('--order-id', required=True, help='Order ID')
@click.option('--stages', help='Comma-separated list of stages (optional)')
def init_stages(tenant: str, order_id: str, stages: Optional[str]):
    """Initialize processing stages for an order."""
    import asyncio
    
    async def run():
        async with get_session() as db:
            service = ProcessingStageService(db)
            
            stage_list = None
            if stages:
                stage_list = [s.strip() for s in stages.split(',')]
            
            created_stages = service.initialize_order_stages(tenant, order_id, stage_list)
            
            click.echo(f"✅ Initialized {len(created_stages)} stages for order {order_id}")
            
            # Display created stages
            table_data = []
            for stage in created_stages:
                table_data.append([
                    stage.stage_name,
                    stage.stage_status,
                    "✅" if stage.dependencies_met else "❌",
                    stage.retry_count,
                    stage.max_retries
                ])
            
            headers = ["Stage", "Status", "Dependencies Met", "Retries", "Max Retries"]
            click.echo("\n" + tabulate(table_data, headers=headers, tablefmt="grid"))
    
    asyncio.run(run())


@processing_stages.command()
@click.option('--tenant', required=True, help='Tenant name')
@click.option('--order-id', required=True, help='Order ID')
@click.option('--stage', required=True, help='Stage name')
def start_stage(tenant: str, order_id: str, stage: str):
    """Start a processing stage."""
    with get_db_session() as db:
        service = ProcessingStageService(db)
        
        result = service.start_stage(tenant, order_id, stage)
        if result:
            click.echo(f"✅ Started stage '{stage}' for order {order_id}")
        else:
            click.echo(f"❌ Failed to start stage '{stage}' for order {order_id}")


@processing_stages.command()
@click.option('--tenant', required=True, help='Tenant name')
@click.option('--order-id', required=True, help='Order ID')
@click.option('--stage', required=True, help='Stage name')
@click.option('--data', help='Stage data as JSON string')
def complete_stage(tenant: str, order_id: str, stage: str, data: Optional[str]):
    """Complete a processing stage."""
    import json
    
    with get_db_session() as db:
        service = ProcessingStageService(db)
        
        stage_data = None
        if data:
            try:
                stage_data = json.loads(data)
            except json.JSONDecodeError:
                click.echo("❌ Invalid JSON data provided")
                return
        
        result = service.complete_stage(tenant, order_id, stage, stage_data)
        if result:
            click.echo(f"✅ Completed stage '{stage}' for order {order_id}")
        else:
            click.echo(f"❌ Failed to complete stage '{stage}' for order {order_id}")


@processing_stages.command()
@click.option('--tenant', required=True, help='Tenant name')
@click.option('--order-id', required=True, help='Order ID')
@click.option('--stage', required=True, help='Stage name')
@click.option('--error', required=True, help='Error message')
def fail_stage(tenant: str, order_id: str, stage: str, error: str):
    """Mark a processing stage as failed."""
    with get_db_session() as db:
        service = ProcessingStageService(db)
        
        result = service.fail_stage(tenant, order_id, stage, error)
        if result:
            if result.stage_status == "PENDING":
                click.echo(f"⚠️  Stage '{stage}' failed but will retry ({result.retry_count}/{result.max_retries})")
            else:
                click.echo(f"❌ Stage '{stage}' permanently failed after {result.retry_count} attempts")
        else:
            click.echo(f"❌ Failed to update stage '{stage}' for order {order_id}")


@processing_stages.command()
@click.option('--tenant', required=True, help='Tenant name')
@click.option('--order-id', required=True, help='Order ID')
def list_stages(tenant: str, order_id: str):
    """List all processing stages for an order."""
    with get_db_session() as db:
        service = ProcessingStageService(db)
        
        stages = service.get_order_stages(tenant, order_id)
        
        if not stages:
            click.echo(f"No stages found for order {order_id}")
            return
        
        table_data = []
        for stage in stages:
            duration = ""
            if stage.duration_seconds:
                duration = f"{stage.duration_seconds}s"
            
            table_data.append([
                stage.stage_name,
                stage.stage_status,
                "✅" if stage.dependencies_met else "❌",
                f"{stage.retry_count}/{stage.max_retries}",
                stage.started_at.strftime("%H:%M:%S") if stage.started_at else "-",
                stage.completed_at.strftime("%H:%M:%S") if stage.completed_at else "-",
                duration,
                stage.error_message[:50] + "..." if stage.error_message and len(stage.error_message) > 50 else stage.error_message or "-"
            ])
        
        headers = ["Stage", "Status", "Deps Met", "Retries", "Started", "Completed", "Duration", "Error"]
        click.echo(f"\nProcessing stages for order {order_id}:")
        click.echo(tabulate(table_data, headers=headers, tablefmt="grid"))


@processing_stages.command()
@click.option('--tenant', required=True, help='Tenant name')
@click.option('--limit', type=int, default=20, help='Limit number of results')
def list_eligible(tenant: str, limit: int):
    """List stages eligible to run."""
    with get_db_session() as db:
        service = ProcessingStageService(db)
        
        stages = service.get_eligible_stages(tenant, limit)
        
        if not stages:
            click.echo("No eligible stages found")
            return
        
        table_data = []
        for stage in stages:
            table_data.append([
                stage.order_id,
                stage.stage_name,
                stage.stage_status,
                f"{stage.retry_count}/{stage.max_retries}",
                stage.created_at.strftime("%Y-%m-%d %H:%M:%S")
            ])
        
        headers = ["Order ID", "Stage", "Status", "Retries", "Created"]
        click.echo(f"\nEligible stages (limit: {limit}):")
        click.echo(tabulate(table_data, headers=headers, tablefmt="grid"))


@processing_stages.command()
@click.option('--tenant', required=True, help='Tenant name')
def metrics(tenant: str):
    """Show processing stage metrics."""
    with get_db_session() as db:
        service = ProcessingStageService(db)
        completeness_service = DataCompletenessService(db)
        
        stage_metrics = service.get_stage_metrics(tenant)
        completeness_metrics = completeness_service.get_completeness_metrics(tenant)
        
        click.echo(f"\n📊 Processing Stage Metrics for {tenant}")
        click.echo("=" * 50)
        
        # Status counts
        click.echo("\n🔄 Stage Status Counts:")
        status_data = [[status, count] for status, count in stage_metrics['status_counts'].items()]
        click.echo(tabulate(status_data, headers=["Status", "Count"], tablefmt="grid"))
        
        # Completion rates
        click.echo("\n📈 Stage Completion Rates:")
        completion_data = []
        for stage, stats in stage_metrics['completion_rates'].items():
            completion_data.append([
                stage,
                stats['total'],
                stats['completed'],
                stats['failed'],
                f"{stats['completion_rate']:.1f}%"
            ])
        
        headers = ["Stage", "Total", "Completed", "Failed", "Success Rate"]
        click.echo(tabulate(completion_data, headers=headers, tablefmt="grid"))
        
        # Average processing times
        if stage_metrics['average_processing_times']:
            click.echo("\n⏱️  Average Processing Times:")
            time_data = []
            for stage, avg_seconds in stage_metrics['average_processing_times'].items():
                if avg_seconds:
                    time_data.append([stage, f"{avg_seconds:.1f}s"])
            
            if time_data:
                click.echo(tabulate(time_data, headers=["Stage", "Avg Time"], tablefmt="grid"))
        
        # Data completeness metrics
        click.echo(f"\n✅ Data Completeness Metrics:")
        click.echo(f"Total Checks: {completeness_metrics['total_checks']}")
        click.echo(f"Passed Checks: {completeness_metrics['passed_checks']}")
        click.echo(f"Overall Completion Rate: {completeness_metrics['overall_completion_rate']:.1f}%")
        
        # Eligible stages count
        click.echo(f"\n🎯 Eligible Stages: {stage_metrics['eligible_stages_count']}")


@processing_stages.group()
def completeness():
    """Data completeness check commands."""
    pass


@completeness.command()
@click.option('--tenant', required=True, help='Tenant name')
@click.option('--order-id', required=True, help='Order ID')
@click.option('--check-type', required=True, help='Check type')
def create_check(tenant: str, order_id: str, check_type: str):
    """Create a data completeness check."""
    with get_db_session() as db:
        service = DataCompletenessService(db)
        
        check = service.create_completeness_check(tenant, order_id, check_type)
        click.echo(f"✅ Created completeness check '{check_type}' for order {order_id}")


@completeness.command()
@click.option('--tenant', required=True, help='Tenant name')
@click.option('--order-id', required=True, help='Order ID')
@click.option('--check-type', required=True, help='Check type')
@click.option('--passed', is_flag=True, help='Mark check as passed')
@click.option('--result', help='Check result as JSON string')
def complete_check(tenant: str, order_id: str, check_type: str, passed: bool, result: Optional[str]):
    """Complete a data completeness check."""
    import json
    
    with get_db_session() as db:
        service = DataCompletenessService(db)
        
        check_result = {}
        if result:
            try:
                check_result = json.loads(result)
            except json.JSONDecodeError:
                click.echo("❌ Invalid JSON result provided")
                return
        
        check = service.complete_check(tenant, order_id, check_type, check_result, passed)
        if check:
            status = "PASSED" if passed else "FAILED"
            click.echo(f"✅ Completed check '{check_type}' with status {status}")
        else:
            click.echo(f"❌ Failed to complete check '{check_type}' for order {order_id}")


@completeness.command()
@click.option('--tenant', required=True, help='Tenant name')
@click.option('--order-id', required=True, help='Order ID')
def show_completeness(tenant: str, order_id: str):
    """Show data completeness status for an order."""
    with get_db_session() as db:
        service = DataCompletenessService(db)
        
        completeness = service.get_order_completeness(tenant, order_id)
        
        click.echo(f"\n📋 Data Completeness for Order {order_id}")
        click.echo("=" * 50)
        click.echo(f"Total Checks: {completeness['total_checks']}")
        click.echo(f"Passed Checks: {completeness['passed_checks']}")
        click.echo(f"Completion: {completeness['completion_percentage']:.1f}%")
        
        if completeness['checks']:
            table_data = []
            for check in completeness['checks']:
                table_data.append([
                    check['check_type'],
                    check['status'],
                    check['checked_at'].strftime("%Y-%m-%d %H:%M:%S") if check['checked_at'] else "-"
                ])
            
            headers = ["Check Type", "Status", "Checked At"]
            click.echo("\n" + tabulate(table_data, headers=headers, tablefmt="grid"))


# Add subcommands to main group
processing_stages.add_command(completeness)


if __name__ == '__main__':
    processing_stages()
