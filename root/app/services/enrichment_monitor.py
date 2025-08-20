# ==== ENRICHMENT MONITORING SERVICE ==== #

"""
Comprehensive monitoring and alerting for data enrichment pipeline.

This module provides real-time monitoring of enrichment completeness,
quality metrics, failure detection, and automated alerting for
data pipeline health and performance.
"""

from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from enum import Enum
from dataclasses import dataclass

from sqlalchemy import select, and_, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.storage.db import get_session
from app.storage.models import ExceptionRecord, OrderEvent
from app.observability.tracing import get_tracer
from app.observability.logging import ContextualLogger
from app.observability.metrics import (
    Gauge, Counter, Histogram,
    ai_requests_total, ai_failures_total
)


# ==== MODULE INITIALIZATION ==== #

tracer = get_tracer(__name__)
logger = ContextualLogger(__name__)

# Custom metrics for enrichment monitoring
enrichment_completeness_rate = Gauge(
    "octup_enrichment_completeness_rate",
    "Percentage of records with complete AI enrichment",
    ["tenant", "enrichment_type"]
)

enrichment_quality_score = Gauge(
    "octup_enrichment_quality_score", 
    "Quality score of AI enrichment (0-100)",
    ["tenant", "enrichment_type"]
)

enrichment_backlog_size = Gauge(
    "octup_enrichment_backlog_size",
    "Number of records awaiting enrichment",
    ["tenant", "priority"]
)

enrichment_processing_duration = Histogram(
    "octup_enrichment_processing_duration_seconds",
    "Time taken to process enrichment batches",
    ["tenant", "batch_size"]
)

enrichment_failures_total = Counter(
    "octup_enrichment_failures_total",
    "Total enrichment failures by type",
    ["tenant", "failure_type", "stage"]
)


# ==== MONITORING DEFINITIONS ==== #

class AlertLevel(Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


@dataclass
class EnrichmentAlert:
    """Enrichment alert definition."""
    level: AlertLevel
    title: str
    message: str
    tenant: str
    metric_name: str
    current_value: float
    threshold_value: float
    timestamp: datetime
    action_required: str
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert alert to dictionary format."""
        return {
            "level": self.level.value,
            "title": self.title,
            "message": self.message,
            "tenant": self.tenant,
            "metric_name": self.metric_name,
            "current_value": self.current_value,
            "threshold_value": self.threshold_value,
            "timestamp": self.timestamp.isoformat(),
            "action_required": self.action_required
        }


@dataclass
class EnrichmentMetrics:
    """Complete enrichment metrics for a tenant."""
    tenant: str
    timestamp: datetime
    
    # Completeness metrics
    total_records: int
    classified_records: int
    high_confidence_records: int
    automated_resolution_records: int
    
    # Quality metrics
    classification_rate: float
    high_confidence_rate: float
    automation_rate: float
    average_confidence: float
    
    # Performance metrics
    records_processed_last_hour: int
    records_failed_last_hour: int
    average_processing_time: float
    
    # Backlog metrics
    pending_classification: int
    pending_automation: int
    failed_enrichment: int
    
    @property
    def overall_completeness(self) -> float:
        """Calculate overall enrichment completeness percentage."""
        if self.total_records == 0:
            return 100.0
        
        # Weight different enrichment stages
        classification_weight = 0.4
        confidence_weight = 0.4
        automation_weight = 0.2
        
        completeness = (
            (self.classification_rate * classification_weight) +
            (self.high_confidence_rate * confidence_weight) +
            (self.automation_rate * automation_weight)
        )
        
        return min(100.0, completeness)
    
    @property
    def quality_score(self) -> float:
        """Calculate overall quality score (0-100)."""
        if self.total_records == 0:
            return 100.0
        
        # Quality factors
        confidence_factor = self.average_confidence * 100
        coverage_factor = self.classification_rate
        reliability_factor = 100 - (self.records_failed_last_hour / max(1, self.records_processed_last_hour) * 100)
        
        # Weighted quality score
        quality = (
            confidence_factor * 0.5 +
            coverage_factor * 0.3 +
            reliability_factor * 0.2
        )
        
        return min(100.0, max(0.0, quality))


# ==== ENRICHMENT MONITOR CLASS ==== #

class EnrichmentMonitor:
    """
    Comprehensive enrichment monitoring service.
    
    Provides real-time monitoring of data enrichment pipeline health,
    quality metrics, and automated alerting for operational issues.
    """
    
    def __init__(self):
        """Initialize the enrichment monitor."""
        # Alert thresholds
        self.thresholds = {
            "completeness_critical": 70.0,    # Below 70% completeness is critical
            "completeness_warning": 85.0,     # Below 85% completeness is warning
            "quality_critical": 60.0,         # Below 60% quality is critical
            "quality_warning": 80.0,          # Below 80% quality is warning
            "backlog_critical": 1000,         # More than 1000 pending is critical
            "backlog_warning": 500,           # More than 500 pending is warning
            "failure_rate_critical": 20.0,    # More than 20% failure rate is critical
            "failure_rate_warning": 10.0      # More than 10% failure rate is warning
        }
    
    async def collect_enrichment_metrics(self, tenant: str) -> EnrichmentMetrics:
        """
        Collect comprehensive enrichment metrics for a tenant.
        
        Args:
            tenant (str): Tenant identifier
            
        Returns:
            EnrichmentMetrics: Complete metrics for the tenant
        """
        with tracer.start_as_current_span("collect_enrichment_metrics") as span:
            span.set_attribute("tenant", tenant)
            
            async with get_session() as db:
                # Base query for tenant records
                base_query = select(ExceptionRecord).where(ExceptionRecord.tenant == tenant)
                
                # Total records
                total_result = await db.execute(select(func.count()).where(ExceptionRecord.tenant == tenant))
                total_records = total_result.scalar() or 0
                
                # Classified records (have AI analysis)
                classified_result = await db.execute(
                    select(func.count()).where(
                        and_(
                            ExceptionRecord.tenant == tenant,
                            ExceptionRecord.ai_confidence.isnot(None),
                            ExceptionRecord.ai_label.isnot(None)
                        )
                    )
                )
                classified_records = classified_result.scalar() or 0
                
                # High confidence records
                high_confidence_result = await db.execute(
                    select(func.count()).where(
                        and_(
                            ExceptionRecord.tenant == tenant,
                            ExceptionRecord.ai_confidence >= 0.7
                        )
                    )
                )
                high_confidence_records = high_confidence_result.scalar() or 0
                
                # Automated resolution records
                automation_result = await db.execute(
                    select(func.count()).where(
                        and_(
                            ExceptionRecord.tenant == tenant,
                            ExceptionRecord.ops_note.like("%AI-resolved%")
                        )
                    )
                )
                automated_resolution_records = automation_result.scalar() or 0
                
                # Average confidence
                avg_confidence_result = await db.execute(
                    select(func.avg(ExceptionRecord.ai_confidence)).where(
                        and_(
                            ExceptionRecord.tenant == tenant,
                            ExceptionRecord.ai_confidence.isnot(None)
                        )
                    )
                )
                average_confidence = avg_confidence_result.scalar() or 0.0
                
                # Recent activity (last hour)
                one_hour_ago = datetime.utcnow() - timedelta(hours=1)
                
                recent_processed_result = await db.execute(
                    select(func.count()).where(
                        and_(
                            ExceptionRecord.tenant == tenant,
                            ExceptionRecord.updated_at >= one_hour_ago,
                            ExceptionRecord.ai_confidence.isnot(None)
                        )
                    )
                )
                records_processed_last_hour = recent_processed_result.scalar() or 0
                
                # Failed enrichment (NULL confidence after recent update)
                recent_failed_result = await db.execute(
                    select(func.count()).where(
                        and_(
                            ExceptionRecord.tenant == tenant,
                            ExceptionRecord.updated_at >= one_hour_ago,
                            ExceptionRecord.ai_confidence.is_(None)
                        )
                    )
                )
                records_failed_last_hour = recent_failed_result.scalar() or 0
                
                # Pending enrichment
                pending_classification = total_records - classified_records
                pending_automation = high_confidence_records - automated_resolution_records
                failed_enrichment = records_failed_last_hour
                
                # Calculate rates
                classification_rate = (classified_records / total_records * 100) if total_records > 0 else 100.0
                high_confidence_rate = (high_confidence_records / total_records * 100) if total_records > 0 else 100.0
                automation_rate = (automated_resolution_records / total_records * 100) if total_records > 0 else 100.0
                
                # Create metrics object
                metrics = EnrichmentMetrics(
                    tenant=tenant,
                    timestamp=datetime.utcnow(),
                    total_records=total_records,
                    classified_records=classified_records,
                    high_confidence_records=high_confidence_records,
                    automated_resolution_records=automated_resolution_records,
                    classification_rate=classification_rate,
                    high_confidence_rate=high_confidence_rate,
                    automation_rate=automation_rate,
                    average_confidence=average_confidence,
                    records_processed_last_hour=records_processed_last_hour,
                    records_failed_last_hour=records_failed_last_hour,
                    average_processing_time=2.5,  # Placeholder - would be calculated from metrics
                    pending_classification=pending_classification,
                    pending_automation=pending_automation,
                    failed_enrichment=failed_enrichment
                )
                
                # Update Prometheus metrics
                self._update_prometheus_metrics(metrics)
                
                logger.info(f"Collected enrichment metrics for tenant {tenant}: "
                           f"{metrics.overall_completeness:.1f}% complete, "
                           f"{metrics.quality_score:.1f} quality score")
                
                return metrics
    
    def _update_prometheus_metrics(self, metrics: EnrichmentMetrics) -> None:
        """
        Update Prometheus metrics with enrichment data.
        
        Args:
            metrics (EnrichmentMetrics): Enrichment metrics to publish
        """
        tenant = metrics.tenant
        
        # Completeness metrics
        enrichment_completeness_rate.labels(
            tenant=tenant, 
            enrichment_type="classification"
        ).set(metrics.classification_rate)
        
        enrichment_completeness_rate.labels(
            tenant=tenant,
            enrichment_type="high_confidence"
        ).set(metrics.high_confidence_rate)
        
        enrichment_completeness_rate.labels(
            tenant=tenant,
            enrichment_type="automation"
        ).set(metrics.automation_rate)
        
        # Quality metrics
        enrichment_quality_score.labels(
            tenant=tenant,
            enrichment_type="overall"
        ).set(metrics.quality_score)
        
        enrichment_quality_score.labels(
            tenant=tenant,
            enrichment_type="confidence"
        ).set(metrics.average_confidence * 100)
        
        # Backlog metrics
        enrichment_backlog_size.labels(
            tenant=tenant,
            priority="classification"
        ).set(metrics.pending_classification)
        
        enrichment_backlog_size.labels(
            tenant=tenant,
            priority="automation"
        ).set(metrics.pending_automation)
        
        enrichment_backlog_size.labels(
            tenant=tenant,
            priority="failed"
        ).set(metrics.failed_enrichment)
    
    async def check_enrichment_health(self, tenant: str) -> List[EnrichmentAlert]:
        """
        Check enrichment health and generate alerts.
        
        Args:
            tenant (str): Tenant to check
            
        Returns:
            List[EnrichmentAlert]: List of generated alerts
        """
        metrics = await self.collect_enrichment_metrics(tenant)
        alerts = []
        
        # Check completeness thresholds
        completeness = metrics.overall_completeness
        if completeness < self.thresholds["completeness_critical"]:
            alerts.append(EnrichmentAlert(
                level=AlertLevel.CRITICAL,
                title="Critical Enrichment Completeness",
                message=f"Enrichment completeness is {completeness:.1f}% (threshold: {self.thresholds['completeness_critical']}%)",
                tenant=tenant,
                metric_name="completeness",
                current_value=completeness,
                threshold_value=self.thresholds["completeness_critical"],
                timestamp=datetime.utcnow(),
                action_required="Immediate investigation of enrichment pipeline required"
            ))
        elif completeness < self.thresholds["completeness_warning"]:
            alerts.append(EnrichmentAlert(
                level=AlertLevel.WARNING,
                title="Low Enrichment Completeness",
                message=f"Enrichment completeness is {completeness:.1f}% (threshold: {self.thresholds['completeness_warning']}%)",
                tenant=tenant,
                metric_name="completeness",
                current_value=completeness,
                threshold_value=self.thresholds["completeness_warning"],
                timestamp=datetime.utcnow(),
                action_required="Review enrichment pipeline performance"
            ))
        
        # Check quality thresholds
        quality = metrics.quality_score
        if quality < self.thresholds["quality_critical"]:
            alerts.append(EnrichmentAlert(
                level=AlertLevel.CRITICAL,
                title="Critical Enrichment Quality",
                message=f"Enrichment quality is {quality:.1f} (threshold: {self.thresholds['quality_critical']})",
                tenant=tenant,
                metric_name="quality",
                current_value=quality,
                threshold_value=self.thresholds["quality_critical"],
                timestamp=datetime.utcnow(),
                action_required="Immediate AI model performance investigation required"
            ))
        elif quality < self.thresholds["quality_warning"]:
            alerts.append(EnrichmentAlert(
                level=AlertLevel.WARNING,
                title="Low Enrichment Quality",
                message=f"Enrichment quality is {quality:.1f} (threshold: {self.thresholds['quality_warning']})",
                tenant=tenant,
                metric_name="quality",
                current_value=quality,
                threshold_value=self.thresholds["quality_warning"],
                timestamp=datetime.utcnow(),
                action_required="Review AI model performance and prompt engineering"
            ))
        
        # Check backlog thresholds
        total_backlog = metrics.pending_classification + metrics.pending_automation
        if total_backlog > self.thresholds["backlog_critical"]:
            alerts.append(EnrichmentAlert(
                level=AlertLevel.CRITICAL,
                title="Critical Enrichment Backlog",
                message=f"Enrichment backlog is {total_backlog} records (threshold: {self.thresholds['backlog_critical']})",
                tenant=tenant,
                metric_name="backlog",
                current_value=total_backlog,
                threshold_value=self.thresholds["backlog_critical"],
                timestamp=datetime.utcnow(),
                action_required="Scale up enrichment processing immediately"
            ))
        elif total_backlog > self.thresholds["backlog_warning"]:
            alerts.append(EnrichmentAlert(
                level=AlertLevel.WARNING,
                title="High Enrichment Backlog",
                message=f"Enrichment backlog is {total_backlog} records (threshold: {self.thresholds['backlog_warning']})",
                tenant=tenant,
                metric_name="backlog",
                current_value=total_backlog,
                threshold_value=self.thresholds["backlog_warning"],
                timestamp=datetime.utcnow(),
                action_required="Consider increasing enrichment processing capacity"
            ))
        
        # Check failure rate
        if metrics.records_processed_last_hour > 0:
            failure_rate = (metrics.records_failed_last_hour / metrics.records_processed_last_hour) * 100
            
            if failure_rate > self.thresholds["failure_rate_critical"]:
                alerts.append(EnrichmentAlert(
                    level=AlertLevel.CRITICAL,
                    title="Critical Enrichment Failure Rate",
                    message=f"Enrichment failure rate is {failure_rate:.1f}% (threshold: {self.thresholds['failure_rate_critical']}%)",
                    tenant=tenant,
                    metric_name="failure_rate",
                    current_value=failure_rate,
                    threshold_value=self.thresholds["failure_rate_critical"],
                    timestamp=datetime.utcnow(),
                    action_required="Immediate investigation of enrichment failures required"
                ))
            elif failure_rate > self.thresholds["failure_rate_warning"]:
                alerts.append(EnrichmentAlert(
                    level=AlertLevel.WARNING,
                    title="High Enrichment Failure Rate",
                    message=f"Enrichment failure rate is {failure_rate:.1f}% (threshold: {self.thresholds['failure_rate_warning']}%)",
                    tenant=tenant,
                    metric_name="failure_rate",
                    current_value=failure_rate,
                    threshold_value=self.thresholds["failure_rate_warning"],
                    timestamp=datetime.utcnow(),
                    action_required="Review error patterns and improve error handling"
                ))
        
        if alerts:
            logger.warning(f"Generated {len(alerts)} enrichment alerts for tenant {tenant}")
        
        return alerts
    
    async def generate_enrichment_report(self, tenant: str) -> Dict[str, Any]:
        """
        Generate comprehensive enrichment report.
        
        Args:
            tenant (str): Tenant identifier
            
        Returns:
            Dict[str, Any]: Comprehensive enrichment report
        """
        metrics = await self.collect_enrichment_metrics(tenant)
        alerts = await self.check_enrichment_health(tenant)
        
        # Categorize alerts by level
        critical_alerts = [a for a in alerts if a.level == AlertLevel.CRITICAL]
        warning_alerts = [a for a in alerts if a.level == AlertLevel.WARNING]
        
        # Determine overall health status
        if critical_alerts:
            health_status = "CRITICAL"
        elif warning_alerts:
            health_status = "WARNING"
        else:
            health_status = "HEALTHY"
        
        report = {
            "tenant": tenant,
            "report_time": datetime.utcnow().isoformat(),
            "health_status": health_status,
            "metrics": {
                "completeness": {
                    "overall": metrics.overall_completeness,
                    "classification_rate": metrics.classification_rate,
                    "high_confidence_rate": metrics.high_confidence_rate,
                    "automation_rate": metrics.automation_rate
                },
                "quality": {
                    "overall_score": metrics.quality_score,
                    "average_confidence": metrics.average_confidence,
                    "records_processed_last_hour": metrics.records_processed_last_hour,
                    "records_failed_last_hour": metrics.records_failed_last_hour
                },
                "backlog": {
                    "pending_classification": metrics.pending_classification,
                    "pending_automation": metrics.pending_automation,
                    "failed_enrichment": metrics.failed_enrichment,
                    "total_backlog": metrics.pending_classification + metrics.pending_automation
                },
                "volume": {
                    "total_records": metrics.total_records,
                    "classified_records": metrics.classified_records,
                    "high_confidence_records": metrics.high_confidence_records,
                    "automated_resolution_records": metrics.automated_resolution_records
                }
            },
            "alerts": {
                "total": len(alerts),
                "critical": len(critical_alerts),
                "warning": len(warning_alerts),
                "details": [alert.to_dict() for alert in alerts]
            },
            "recommendations": self._generate_recommendations(metrics, alerts)
        }
        
        logger.info(f"Generated enrichment report for tenant {tenant}: {health_status} status")
        
        return report
    
    def _generate_recommendations(
        self, 
        metrics: EnrichmentMetrics, 
        alerts: List[EnrichmentAlert]
    ) -> List[str]:
        """
        Generate actionable recommendations based on metrics and alerts.
        
        Args:
            metrics (EnrichmentMetrics): Current metrics
            alerts (List[EnrichmentAlert]): Active alerts
            
        Returns:
            List[str]: List of recommendations
        """
        recommendations = []
        
        # Completeness recommendations
        if metrics.overall_completeness < 90:
            recommendations.append("Increase enrichment pipeline frequency to improve completeness")
        
        if metrics.pending_classification > 100:
            recommendations.append("Scale up AI classification processing to reduce backlog")
        
        # Quality recommendations
        if metrics.average_confidence < 0.8:
            recommendations.append("Review AI model performance and consider prompt engineering improvements")
        
        if metrics.quality_score < 80:
            recommendations.append("Investigate AI service reliability and error patterns")
        
        # Performance recommendations
        if metrics.records_failed_last_hour > 10:
            recommendations.append("Implement better error handling and retry mechanisms")
        
        # Alert-specific recommendations
        critical_alerts = [a for a in alerts if a.level == AlertLevel.CRITICAL]
        if critical_alerts:
            recommendations.append("Address critical alerts immediately to prevent service degradation")
        
        return recommendations


# ==== GLOBAL SERVICE INSTANCE ==== #

_enrichment_monitor: Optional[EnrichmentMonitor] = None


def get_enrichment_monitor() -> EnrichmentMonitor:
    """
    Get global enrichment monitor instance.
    
    Returns:
        EnrichmentMonitor: Global enrichment monitor instance
    """
    global _enrichment_monitor
    if _enrichment_monitor is None:
        _enrichment_monitor = EnrichmentMonitor()
    return _enrichment_monitor
