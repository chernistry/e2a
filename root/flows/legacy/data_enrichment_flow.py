# ==== DATA ENRICHMENT FLOW ==== #

"""
Prefect flow for systematic data enrichment in Octup E²A.

This flow orchestrates comprehensive AI enrichment of all data records,
ensuring systematic reprocessing of failed enrichment, completeness tracking,
and robust failure recovery mechanisms.
"""

from datetime import datetime, timedelta
from typing import Dict, Any, List

from prefect import flow, task, get_run_logger
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.storage.db import get_session
from app.storage.models import ExceptionRecord
from app.services.data_enrichment_pipeline import get_enrichment_pipeline


# ==== ENRICHMENT TASKS ==== #

@task
async def analyze_enrichment_backlog(tenant: str = "demo-3pl") -> Dict[str, Any]:
    """
    Analyze the current enrichment backlog for a tenant.
    
    Identifies records that need enrichment or reprocessing and provides
    statistics on data completeness and enrichment quality.
    
    Args:
        tenant (str): Tenant identifier
        
    Returns:
        Dict[str, Any]: Backlog analysis with statistics and priorities
    """
    logger = get_run_logger()
    logger.info(f"Analyzing enrichment backlog for tenant {tenant}")
    
    async with get_session() as db:
        # Total records
        total_query = select(func.count()).where(ExceptionRecord.tenant == tenant)
        total_result = await db.execute(total_query)
        total_records = total_result.scalar() or 0
        
        # Records missing AI classification
        missing_classification_query = select(func.count()).where(
            and_(
                ExceptionRecord.tenant == tenant,
                ExceptionRecord.ai_confidence.is_(None)
            )
        )
        missing_classification_result = await db.execute(missing_classification_query)
        missing_classification = missing_classification_result.scalar() or 0
        
        # Records with low confidence (need reprocessing)
        low_confidence_query = select(func.count()).where(
            and_(
                ExceptionRecord.tenant == tenant,
                ExceptionRecord.ai_confidence < 0.7,
                ExceptionRecord.ai_confidence.isnot(None)
            )
        )
        low_confidence_result = await db.execute(low_confidence_query)
        low_confidence = low_confidence_result.scalar() or 0
        
        # Records created in last 24 hours (recent)
        recent_cutoff = datetime.utcnow() - timedelta(hours=24)
        recent_query = select(func.count()).where(
            and_(
                ExceptionRecord.tenant == tenant,
                ExceptionRecord.created_at >= recent_cutoff
            )
        )
        recent_result = await db.execute(recent_query)
        recent_records = recent_result.scalar() or 0
        
        # Calculate priorities
        total_needing_enrichment = missing_classification + low_confidence
        enrichment_rate = ((total_records - total_needing_enrichment) / total_records * 100) if total_records > 0 else 100
        
        # Determine priority level
        if total_needing_enrichment > 1000:
            priority = "CRITICAL"
        elif total_needing_enrichment > 500:
            priority = "HIGH"
        elif total_needing_enrichment > 100:
            priority = "MEDIUM"
        else:
            priority = "LOW"
        
        backlog_analysis = {
            "tenant": tenant,
            "analysis_time": datetime.utcnow().isoformat(),
            "total_records": total_records,
            "missing_classification": missing_classification,
            "low_confidence": low_confidence,
            "recent_records": recent_records,
            "total_needing_enrichment": total_needing_enrichment,
            "enrichment_rate": round(enrichment_rate, 2),
            "priority": priority,
            "recommended_batch_size": min(100, max(10, total_needing_enrichment // 10))
        }
        
        logger.info(f"Backlog analysis complete: {total_needing_enrichment} records need enrichment "
                   f"({enrichment_rate:.1f}% completion rate)")
        
        return backlog_analysis


@task
async def execute_enrichment_pipeline(
    backlog_analysis: Dict[str, Any],
    tenant: str = "demo-3pl"
) -> Dict[str, Any]:
    """
    Execute the comprehensive enrichment pipeline.
    
    Processes records through all enrichment stages with automatic
    reprocessing and failure recovery.
    
    Args:
        backlog_analysis (Dict[str, Any]): Output from analyze_enrichment_backlog
        tenant (str): Tenant identifier
        
    Returns:
        Dict[str, Any]: Pipeline execution results
    """
    logger = get_run_logger()
    logger.info(f"Executing enrichment pipeline for tenant {tenant}")
    
    # Get recommended batch size from backlog analysis
    batch_size = backlog_analysis.get("recommended_batch_size", 50)
    
    # Adjust batch size based on priority
    priority = backlog_analysis.get("priority", "MEDIUM")
    if priority == "CRITICAL":
        batch_size = min(200, batch_size * 2)  # Larger batches for critical backlog
    elif priority == "LOW":
        batch_size = max(10, batch_size // 2)  # Smaller batches for low priority
    
    logger.info(f"Using batch size {batch_size} for priority {priority}")
    
    # Execute the enrichment pipeline
    pipeline = get_enrichment_pipeline()
    
    try:
        results = await pipeline.process_enrichment_pipeline(
            tenant=tenant,
            batch_size=batch_size,
            max_retries=3
        )
        
        logger.info(f"Enrichment pipeline completed: {results['records_completed']} completed, "
                   f"{results['records_failed']} failed")
        
        return results
        
    except Exception as e:
        logger.error(f"Enrichment pipeline failed: {e}")
        raise


@task
async def validate_enrichment_quality(
    pipeline_results: Dict[str, Any],
    tenant: str = "demo-3pl"
) -> Dict[str, Any]:
    """
    Validate the quality of enrichment results.
    
    Performs quality checks on enriched data and identifies
    potential issues or areas for improvement.
    
    Args:
        pipeline_results (Dict[str, Any]): Output from execute_enrichment_pipeline
        tenant (str): Tenant identifier
        
    Returns:
        Dict[str, Any]: Quality validation results
    """
    logger = get_run_logger()
    logger.info(f"Validating enrichment quality for tenant {tenant}")
    
    completeness_report = pipeline_results.get("completeness_report", {})
    
    # Quality thresholds
    EXCELLENT_THRESHOLD = 90.0
    GOOD_THRESHOLD = 75.0
    
    classification_rate = completeness_report.get("classification_rate", 0.0)
    high_confidence_rate = completeness_report.get("high_confidence_rate", 0.0)
    
    # Determine overall quality
    if high_confidence_rate >= EXCELLENT_THRESHOLD:
        overall_quality = "EXCELLENT"
        quality_score = 95 + (high_confidence_rate - EXCELLENT_THRESHOLD) / 2
    elif high_confidence_rate >= GOOD_THRESHOLD:
        overall_quality = "GOOD"
        quality_score = 75 + (high_confidence_rate - GOOD_THRESHOLD) * 20 / 15
    else:
        overall_quality = "NEEDS_IMPROVEMENT"
        quality_score = high_confidence_rate
    
    # Identify issues
    issues = []
    recommendations = []
    
    if classification_rate < 95.0:
        issues.append(f"Classification coverage is {classification_rate:.1f}% (target: 95%+)")
        recommendations.append("Investigate AI service availability and error patterns")
    
    if high_confidence_rate < GOOD_THRESHOLD:
        issues.append(f"High confidence rate is {high_confidence_rate:.1f}% (target: {GOOD_THRESHOLD}%+)")
        recommendations.append("Review AI model performance and prompt engineering")
    
    errors = pipeline_results.get("errors", [])
    if len(errors) > 10:
        issues.append(f"High error count: {len(errors)} errors during processing")
        recommendations.append("Investigate common error patterns and improve error handling")
    
    # Success metrics
    records_processed = pipeline_results.get("records_processed", 0)
    records_completed = pipeline_results.get("records_completed", 0)
    success_rate = (records_completed / records_processed * 100) if records_processed > 0 else 0
    
    validation_results = {
        "tenant": tenant,
        "validation_time": datetime.utcnow().isoformat(),
        "overall_quality": overall_quality,
        "quality_score": round(quality_score, 1),
        "classification_rate": classification_rate,
        "high_confidence_rate": high_confidence_rate,
        "success_rate": round(success_rate, 1),
        "records_processed": records_processed,
        "records_completed": records_completed,
        "issues": issues,
        "recommendations": recommendations,
        "completeness_report": completeness_report
    }
    
    logger.info(f"Quality validation complete: {overall_quality} quality "
               f"({quality_score:.1f} score, {success_rate:.1f}% success rate)")
    
    return validation_results


@task
async def generate_enrichment_alerts(
    quality_results: Dict[str, Any],
    tenant: str = "demo-3pl"
) -> Dict[str, Any]:
    """
    Generate alerts for enrichment quality issues.
    
    Creates actionable alerts when enrichment quality falls below
    acceptable thresholds or when critical issues are detected.
    
    Args:
        quality_results (Dict[str, Any]): Output from validate_enrichment_quality
        tenant (str): Tenant identifier
        
    Returns:
        Dict[str, Any]: Generated alerts and notifications
    """
    logger = get_run_logger()
    logger.info(f"Generating enrichment alerts for tenant {tenant}")
    
    alerts = []
    notifications = []
    
    overall_quality = quality_results.get("overall_quality", "UNKNOWN")
    quality_score = quality_results.get("quality_score", 0.0)
    success_rate = quality_results.get("success_rate", 0.0)
    issues = quality_results.get("issues", [])
    
    # Critical alerts
    if overall_quality == "NEEDS_IMPROVEMENT":
        alerts.append({
            "level": "CRITICAL",
            "title": "Data Enrichment Quality Below Threshold",
            "message": f"Enrichment quality is {overall_quality} with {quality_score:.1f}% score",
            "action_required": "Immediate investigation of AI service performance required"
        })
    
    if success_rate < 80.0:
        alerts.append({
            "level": "HIGH",
            "title": "Low Enrichment Success Rate",
            "message": f"Only {success_rate:.1f}% of records processed successfully",
            "action_required": "Review error patterns and improve pipeline reliability"
        })
    
    # Warning alerts
    if len(issues) > 5:
        alerts.append({
            "level": "WARNING",
            "title": "Multiple Enrichment Issues Detected",
            "message": f"{len(issues)} issues found during quality validation",
            "action_required": "Review and address identified issues"
        })
    
    # Success notifications
    if overall_quality == "EXCELLENT" and success_rate > 95.0:
        notifications.append({
            "level": "SUCCESS",
            "title": "Excellent Enrichment Quality",
            "message": f"Achieved {overall_quality} quality with {success_rate:.1f}% success rate"
        })
    
    alert_summary = {
        "tenant": tenant,
        "alert_time": datetime.utcnow().isoformat(),
        "alerts": alerts,
        "notifications": notifications,
        "total_alerts": len(alerts),
        "critical_alerts": len([a for a in alerts if a["level"] == "CRITICAL"]),
        "requires_attention": len(alerts) > 0
    }
    
    if alerts:
        logger.warning(f"Generated {len(alerts)} enrichment alerts for tenant {tenant}")
    else:
        logger.info(f"No enrichment alerts required for tenant {tenant}")
    
    return alert_summary


# ==== MAIN ENRICHMENT FLOW ==== #

@flow(name="data-enrichment-pipeline")
async def data_enrichment_flow(
    tenant: str = "demo-3pl",
    force_reprocessing: bool = False
) -> Dict[str, Any]:
    """
    Comprehensive data enrichment flow.
    
    Orchestrates systematic AI enrichment of all data records with
    automatic reprocessing, quality validation, and alerting.
    
    Args:
        tenant (str): Tenant to process
        force_reprocessing (bool): Force reprocessing of all records
        
    Returns:
        Dict[str, Any]: Complete flow execution results
    """
    logger = get_run_logger()
    logger.info(f"Starting data enrichment flow for tenant {tenant}")
    
    # Step 1: Analyze enrichment backlog
    backlog_analysis = await analyze_enrichment_backlog(tenant)
    
    # Step 2: Execute enrichment pipeline
    pipeline_results = await execute_enrichment_pipeline(backlog_analysis, tenant)
    
    # Step 3: Validate enrichment quality
    quality_results = await validate_enrichment_quality(pipeline_results, tenant)
    
    # Step 4: Generate alerts if needed
    alert_summary = await generate_enrichment_alerts(quality_results, tenant)
    
    # Compile comprehensive results
    flow_results = {
        "tenant": tenant,
        "execution_time": datetime.utcnow().isoformat(),
        "force_reprocessing": force_reprocessing,
        "backlog_analysis": backlog_analysis,
        "pipeline_results": pipeline_results,
        "quality_results": quality_results,
        "alert_summary": alert_summary,
        "flow_status": "SUCCESS" if not alert_summary["requires_attention"] else "WARNING"
    }
    
    logger.info(f"Data enrichment flow completed for tenant {tenant}: "
               f"{flow_results['flow_status']} status")
    
    return flow_results


# ==== SCHEDULED ENRICHMENT FLOW ==== #

@flow(name="scheduled-enrichment-maintenance")
async def scheduled_enrichment_maintenance() -> Dict[str, Any]:
    """
    Scheduled maintenance flow for data enrichment.
    
    Runs periodic enrichment for all tenants to ensure data completeness
    and quality across the entire system.
    
    Returns:
        Dict[str, Any]: Maintenance execution results for all tenants
    """
    logger = get_run_logger()
    logger.info("Starting scheduled enrichment maintenance")
    
    # List of tenants to process (in production, this would be dynamic)
    tenants = ["demo-3pl", "acme-logistics", "global-shipping"]
    
    maintenance_results = {
        "execution_time": datetime.utcnow().isoformat(),
        "tenants_processed": [],
        "total_records_processed": 0,
        "total_records_completed": 0,
        "critical_alerts": 0,
        "overall_status": "SUCCESS"
    }
    
    for tenant in tenants:
        try:
            logger.info(f"Processing enrichment maintenance for tenant {tenant}")
            
            tenant_results = await data_enrichment_flow(tenant)
            
            maintenance_results["tenants_processed"].append({
                "tenant": tenant,
                "status": tenant_results["flow_status"],
                "records_processed": tenant_results["pipeline_results"]["records_processed"],
                "records_completed": tenant_results["pipeline_results"]["records_completed"],
                "quality_score": tenant_results["quality_results"]["quality_score"]
            })
            
            # Aggregate statistics
            maintenance_results["total_records_processed"] += tenant_results["pipeline_results"]["records_processed"]
            maintenance_results["total_records_completed"] += tenant_results["pipeline_results"]["records_completed"]
            maintenance_results["critical_alerts"] += tenant_results["alert_summary"]["critical_alerts"]
            
            # Update overall status
            if tenant_results["flow_status"] == "WARNING":
                maintenance_results["overall_status"] = "WARNING"
            
        except Exception as e:
            logger.error(f"Enrichment maintenance failed for tenant {tenant}: {e}")
            maintenance_results["tenants_processed"].append({
                "tenant": tenant,
                "status": "FAILED",
                "error": str(e)
            })
            maintenance_results["overall_status"] = "FAILED"
    
    logger.info(f"Scheduled enrichment maintenance completed: {maintenance_results['overall_status']} status")
    
    return maintenance_results
