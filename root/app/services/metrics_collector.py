"""Database metrics collection service for comprehensive E2E validation."""

import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.storage.db import get_session
from app.storage.models import ExceptionRecord, OrderEvent
from app.observability.logging import ContextualLogger

logger = ContextualLogger(__name__)


class DatabaseMetricsCollector:
    """Service for collecting comprehensive database metrics for e2e validation."""

    def __init__(self):
        self.session: Optional[AsyncSession] = None

    async def __aenter__(self):
        """Async context manager entry."""
        self.session_context = get_session()
        self.session = await self.session_context.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if hasattr(self, 'session_context'):
            await self.session_context.__aexit__(exc_type, exc_val, exc_tb)

    async def collect_order_metrics(
        self, tenant: str, timeframe_hours: int = 1
    ) -> Dict[str, Any]:
        """Collect comprehensive order processing metrics.
        
        Args:
            tenant: Tenant identifier
            timeframe_hours: Hours to look back for metrics
            
        Returns:
            Dictionary containing order metrics
        """
        if not self.session:
            raise RuntimeError("DatabaseMetricsCollector not initialized as context manager")

        cutoff_time = datetime.utcnow() - timedelta(hours=timeframe_hours)
        
        try:
            # Orders created in timeframe (based on order_created events)
            orders_created_query = select(func.count(func.distinct(OrderEvent.order_id))).where(
                OrderEvent.tenant == tenant,
                OrderEvent.event_type == "order_created",
                OrderEvent.created_at >= cutoff_time
            )
            orders_created = await self.session.scalar(orders_created_query)

            # Orders by event type (as proxy for status)
            orders_by_event_type_query = select(
                OrderEvent.event_type, func.count(func.distinct(OrderEvent.order_id))
            ).where(
                OrderEvent.tenant == tenant,
                OrderEvent.created_at >= cutoff_time
            ).group_by(OrderEvent.event_type)
            
            orders_by_event_type_result = await self.session.execute(orders_by_event_type_query)
            orders_by_status = dict(orders_by_event_type_result.fetchall())

            # Orders with/without exceptions
            orders_with_exceptions_query = select(func.count(func.distinct(ExceptionRecord.order_id))).where(
                ExceptionRecord.tenant == tenant,
                ExceptionRecord.created_at >= cutoff_time
            )
            orders_with_exceptions = await self.session.scalar(orders_with_exceptions_query)

            orders_without_exceptions = orders_created - (orders_with_exceptions or 0)

            # Average exceptions per order
            total_exceptions_query = select(func.count(ExceptionRecord.id)).where(
                ExceptionRecord.tenant == tenant,
                ExceptionRecord.created_at >= cutoff_time
            )
            total_exceptions = await self.session.scalar(total_exceptions_query)
            
            avg_exceptions_per_order = (
                total_exceptions / orders_created if orders_created > 0 else 0
            )

            metrics = {
                "orders_created_count": orders_created or 0,
                "orders_by_status": orders_by_status,
                "orders_with_exceptions_count": orders_with_exceptions or 0,
                "orders_without_exceptions_count": orders_without_exceptions,
                "average_exceptions_per_order": round(avg_exceptions_per_order, 2),
                "total_exceptions_count": total_exceptions or 0,
                "timeframe_hours": timeframe_hours,
                "collected_at": datetime.utcnow().isoformat()
            }

            logger.info("Order metrics collected", extra={
                "tenant": tenant,
                "timeframe_hours": timeframe_hours,
                "orders_created": orders_created,
                "total_exceptions": total_exceptions
            })

            return metrics

        except Exception as e:
            logger.error("Failed to collect order metrics", extra={
                "tenant": tenant,
                "error": str(e)
            })
            raise

    async def collect_exception_metrics(
        self, tenant: str, timeframe_hours: int = 1
    ) -> Dict[str, Any]:
        """Collect comprehensive exception processing metrics.
        
        Args:
            tenant: Tenant identifier
            timeframe_hours: Hours to look back for metrics
            
        Returns:
            Dictionary containing exception metrics
        """
        if not self.session:
            raise RuntimeError("DatabaseMetricsCollector not initialized as context manager")

        cutoff_time = datetime.utcnow() - timedelta(hours=timeframe_hours)
        
        try:
            # Exceptions by reason code
            exceptions_by_reason_query = select(
                ExceptionRecord.reason_code, func.count(ExceptionRecord.id)
            ).where(
                ExceptionRecord.tenant == tenant,
                ExceptionRecord.created_at >= cutoff_time
            ).group_by(ExceptionRecord.reason_code)
            
            exceptions_by_reason_result = await self.session.execute(exceptions_by_reason_query)
            exceptions_by_reason = dict(exceptions_by_reason_result.fetchall())

            # Exceptions by severity
            exceptions_by_severity_query = select(
                ExceptionRecord.severity, func.count(ExceptionRecord.id)
            ).where(
                ExceptionRecord.tenant == tenant,
                ExceptionRecord.created_at >= cutoff_time
            ).group_by(ExceptionRecord.severity)
            
            exceptions_by_severity_result = await self.session.execute(exceptions_by_severity_query)
            exceptions_by_severity = dict(exceptions_by_severity_result.fetchall())

            # Exceptions by status
            exceptions_by_status_query = select(
                ExceptionRecord.status, func.count(ExceptionRecord.id)
            ).where(
                ExceptionRecord.tenant == tenant,
                ExceptionRecord.created_at >= cutoff_time
            ).group_by(ExceptionRecord.status)
            
            exceptions_by_status_result = await self.session.execute(exceptions_by_status_query)
            exceptions_by_status = dict(exceptions_by_status_result.fetchall())

            # AI analysis metrics
            ai_success_query = select(func.count(ExceptionRecord.id)).where(
                ExceptionRecord.tenant == tenant,
                ExceptionRecord.created_at >= cutoff_time,
                ExceptionRecord.ai_label.isnot(None),
                ExceptionRecord.ai_confidence.isnot(None)
            )
            ai_success_count = await self.session.scalar(ai_success_query)

            total_exceptions_query = select(func.count(ExceptionRecord.id)).where(
                ExceptionRecord.tenant == tenant,
                ExceptionRecord.created_at >= cutoff_time
            )
            total_exceptions = await self.session.scalar(total_exceptions_query)

            ai_failure_count = total_exceptions - (ai_success_count or 0)
            ai_success_rate = (
                ai_success_count / total_exceptions if total_exceptions > 0 else 0
            )

            metrics = {
                "exceptions_by_reason_code": exceptions_by_reason,
                "exceptions_by_severity": exceptions_by_severity,
                "exceptions_by_status": exceptions_by_status,
                "ai_analysis_success_rate": round(ai_success_rate, 3),
                "ai_analysis_failure_rate": round(1 - ai_success_rate, 3),
                "exceptions_with_ai_labels_count": ai_success_count or 0,
                "exceptions_without_ai_labels_count": ai_failure_count,
                "total_exceptions_analyzed": total_exceptions or 0,
                "timeframe_hours": timeframe_hours,
                "collected_at": datetime.utcnow().isoformat()
            }

            logger.info("Exception metrics collected", extra={
                "tenant": tenant,
                "timeframe_hours": timeframe_hours,
                "total_exceptions": total_exceptions,
                "ai_success_rate": ai_success_rate
            })

            return metrics

        except Exception as e:
            logger.error("Failed to collect exception metrics", extra={
                "tenant": tenant,
                "error": str(e)
            })
            raise

    async def collect_sla_metrics(
        self, tenant: str, timeframe_hours: int = 1
    ) -> Dict[str, Any]:
        """Collect SLA compliance and breach metrics.
        
        Args:
            tenant: Tenant identifier
            timeframe_hours: Hours to look back for metrics
            
        Returns:
            Dictionary containing SLA metrics
        """
        if not self.session:
            raise RuntimeError("DatabaseMetricsCollector not initialized as context manager")

        cutoff_time = datetime.utcnow() - timedelta(hours=timeframe_hours)
        
        try:
            # SLA breaches by type (from exceptions with SLA-related reason codes)
            sla_breach_types = [
                'PICK_DELAY', 'PACK_DELAY', 'CARRIER_ISSUE', 'MISSING_SCAN'
            ]
            
            sla_breaches_by_type = {}
            for breach_type in sla_breach_types:
                breach_query = select(func.count(ExceptionRecord.id)).where(
                    ExceptionRecord.tenant == tenant,
                    ExceptionRecord.created_at >= cutoff_time,
                    ExceptionRecord.reason_code == breach_type
                )
                breach_count = await self.session.scalar(breach_query)
                sla_breaches_by_type[breach_type] = breach_count or 0

            # Orders meeting vs breaching SLA (based on order_created events)
            total_orders_query = select(func.count(func.distinct(OrderEvent.order_id))).where(
                OrderEvent.tenant == tenant,
                OrderEvent.event_type == "order_created",
                OrderEvent.created_at >= cutoff_time
            )
            total_orders = await self.session.scalar(total_orders_query)

            orders_with_sla_breaches_query = select(
                func.count(func.distinct(ExceptionRecord.order_id))
            ).where(
                ExceptionRecord.tenant == tenant,
                ExceptionRecord.created_at >= cutoff_time,
                ExceptionRecord.reason_code.in_(sla_breach_types)
            )
            orders_breaching_sla = await self.session.scalar(orders_with_sla_breaches_query)

            orders_meeting_sla = total_orders - (orders_breaching_sla or 0)

            # Average processing time by stage (simplified - based on event timestamps)
            # Calculate time between order_created and delivered events
            avg_processing_time_query = select(
                func.avg(
                    func.extract('epoch', OrderEvent.occurred_at) - 
                    func.extract('epoch', OrderEvent.created_at)
                )
            ).where(
                OrderEvent.tenant == tenant,
                OrderEvent.created_at >= cutoff_time,
                OrderEvent.event_type.in_(['delivered', 'package_shipped'])
            )
            avg_processing_time = await self.session.scalar(avg_processing_time_query)

            metrics = {
                "sla_breaches_by_type": sla_breaches_by_type,
                "orders_meeting_sla_count": orders_meeting_sla,
                "orders_breaching_sla_count": orders_breaching_sla or 0,
                "sla_compliance_rate": (
                    orders_meeting_sla / total_orders if total_orders > 0 else 1.0
                ),
                "average_processing_time_seconds": (
                    round(avg_processing_time, 2) if avg_processing_time else None
                ),
                "total_orders_evaluated": total_orders or 0,
                "timeframe_hours": timeframe_hours,
                "collected_at": datetime.utcnow().isoformat()
            }

            logger.info("SLA metrics collected", extra={
                "tenant": tenant,
                "timeframe_hours": timeframe_hours,
                "total_orders": total_orders,
                "sla_compliance_rate": metrics["sla_compliance_rate"]
            })

            return metrics

        except Exception as e:
            logger.error("Failed to collect SLA metrics", extra={
                "tenant": tenant,
                "error": str(e)
            })
            raise

    async def collect_flow_performance_metrics(
        self, tenant: str, timeframe_hours: int = 1
    ) -> Dict[str, Any]:
        """Collect flow execution performance metrics.
        
        Note: This requires integration with Prefect flow run data.
        For now, we'll collect basic event processing metrics.
        
        Args:
            tenant: Tenant identifier
            timeframe_hours: Hours to look back for metrics
            
        Returns:
            Dictionary containing flow performance metrics
        """
        if not self.session:
            raise RuntimeError("DatabaseMetricsCollector not initialized as context manager")

        cutoff_time = datetime.utcnow() - timedelta(hours=timeframe_hours)
        
        try:
            # Event processing metrics
            events_processed_query = select(func.count(OrderEvent.id)).where(
                OrderEvent.tenant == tenant,
                OrderEvent.created_at >= cutoff_time
            )
            events_processed = await self.session.scalar(events_processed_query)

            # Events by type
            events_by_type_query = select(
                OrderEvent.event_type, func.count(OrderEvent.id)
            ).where(
                OrderEvent.tenant == tenant,
                OrderEvent.created_at >= cutoff_time
            ).group_by(OrderEvent.event_type)
            
            events_by_type_result = await self.session.execute(events_by_type_query)
            events_by_type = dict(events_by_type_result.fetchall())

            # Basic performance estimation based on event processing
            # This would be enhanced with actual Prefect flow run data
            estimated_flow_runs = max(1, events_processed // 10)  # Assume batches of 10
            
            metrics = {
                "events_processed_count": events_processed or 0,
                "events_by_type": events_by_type,
                "estimated_flow_runs": estimated_flow_runs,
                "events_per_estimated_run": (
                    events_processed / estimated_flow_runs if estimated_flow_runs > 0 else 0
                ),
                "timeframe_hours": timeframe_hours,
                "collected_at": datetime.utcnow().isoformat(),
                "note": "Flow performance metrics require Prefect integration for detailed data"
            }

            logger.info("Flow performance metrics collected", extra={
                "tenant": tenant,
                "timeframe_hours": timeframe_hours,
                "events_processed": events_processed,
                "estimated_flow_runs": estimated_flow_runs
            })

            return metrics

        except Exception as e:
            logger.error("Failed to collect flow performance metrics", extra={
                "tenant": tenant,
                "error": str(e)
            })
            raise

    async def analyze_pipeline_effectiveness(
        self, tenant: str, timeframe_hours: int = 1
    ) -> Dict[str, Any]:
        """Analyze overall pipeline effectiveness and health.
        
        Args:
            tenant: Tenant identifier
            timeframe_hours: Hours to look back for analysis
            
        Returns:
            Dictionary containing pipeline effectiveness analysis
        """
        try:
            # Collect all metrics
            order_metrics = await self.collect_order_metrics(tenant, timeframe_hours)
            exception_metrics = await self.collect_exception_metrics(tenant, timeframe_hours)
            sla_metrics = await self.collect_sla_metrics(tenant, timeframe_hours)
            flow_metrics = await self.collect_flow_performance_metrics(tenant, timeframe_hours)

            # Analyze effectiveness
            orders_created = order_metrics["orders_created_count"]
            avg_exceptions_per_order = order_metrics["average_exceptions_per_order"]
            ai_success_rate = exception_metrics["ai_analysis_success_rate"]
            sla_compliance_rate = sla_metrics["sla_compliance_rate"]

            # Health scoring (0-1 scale)
            exception_rate_health = min(1.0, max(0.0, 1.0 - abs(avg_exceptions_per_order - 3.2) / 3.2))
            ai_analysis_health = ai_success_rate
            sla_compliance_health = sla_compliance_rate
            
            overall_health = (exception_rate_health + ai_analysis_health + sla_compliance_health) / 3

            # Effectiveness indicators
            effectiveness_indicators = {
                "exception_creation_rate_healthy": 2.0 <= avg_exceptions_per_order <= 5.0,
                "ai_analysis_performing_well": ai_success_rate >= 0.8,
                "sla_compliance_acceptable": sla_compliance_rate >= 0.8,
                "sufficient_order_volume": orders_created >= 1
            }

            analysis = {
                "overall_health_score": round(overall_health, 3),
                "health_breakdown": {
                    "exception_rate_health": round(exception_rate_health, 3),
                    "ai_analysis_health": round(ai_analysis_health, 3),
                    "sla_compliance_health": round(sla_compliance_health, 3)
                },
                "effectiveness_indicators": effectiveness_indicators,
                "pipeline_status": "healthy" if overall_health >= 0.8 else "needs_attention",
                "key_metrics": {
                    "orders_processed": orders_created,
                    "avg_exceptions_per_order": avg_exceptions_per_order,
                    "ai_success_rate": ai_success_rate,
                    "sla_compliance_rate": sla_compliance_rate
                },
                "recommendations": self._generate_recommendations(
                    effectiveness_indicators, overall_health
                ),
                "timeframe_hours": timeframe_hours,
                "analyzed_at": datetime.utcnow().isoformat()
            }

            logger.info("Pipeline effectiveness analyzed", extra={
                "tenant": tenant,
                "overall_health_score": overall_health,
                "pipeline_status": analysis["pipeline_status"]
            })

            return analysis

        except Exception as e:
            logger.error("Failed to analyze pipeline effectiveness", extra={
                "tenant": tenant,
                "error": str(e)
            })
            raise

    def _generate_recommendations(
        self, indicators: Dict[str, bool], health_score: float
    ) -> List[str]:
        """Generate recommendations based on effectiveness indicators."""
        recommendations = []

        if not indicators["exception_creation_rate_healthy"]:
            recommendations.append(
                "Review exception creation logic - rate outside expected 2-5 per order range"
            )

        if not indicators["ai_analysis_performing_well"]:
            recommendations.append(
                "Investigate AI analysis failures - success rate below 80%"
            )

        if not indicators["sla_compliance_acceptable"]:
            recommendations.append(
                "Review SLA breach patterns - compliance rate below 80%"
            )

        if not indicators["sufficient_order_volume"]:
            recommendations.append(
                "Increase test order volume for more reliable metrics"
            )

        if health_score < 0.6:
            recommendations.append(
                "Pipeline health critical - immediate investigation required"
            )
        elif health_score < 0.8:
            recommendations.append(
                "Pipeline health suboptimal - review and optimize components"
            )

        if not recommendations:
            recommendations.append("Pipeline operating within expected parameters")

        return recommendations
