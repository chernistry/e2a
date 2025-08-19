"""
BI-Quality Metrics Service for Octup E²A Dashboard

Provides comprehensive KPI calculations, trend analysis, and business intelligence
metrics for executive and operational decision-making.
"""

from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from sqlalchemy import select, func, and_, desc, text, case
from sqlalchemy.ext.asyncio import AsyncSession
from prometheus_client import REGISTRY
import numpy as np
from scipy import stats

from app.storage.models import ExceptionRecord, OrderEvent, Invoice, InvoiceAdjustment, DLQ
from app.observability.logging import ContextualLogger

logger = ContextualLogger(__name__)


@dataclass
class KPIResult:
    """Structured KPI result with metadata."""
    value: float
    unit: str
    trend: List[Dict[str, Any]]
    status: str  # 'good', 'warning', 'critical'
    metadata: Dict[str, Any]


@dataclass
class ChartData:
    """Structured chart data with configuration."""
    data: List[Dict[str, Any]]
    chart_type: str
    config: Dict[str, Any]
    annotations: List[Dict[str, Any]]


class BIMetricsService:
    """Comprehensive BI metrics calculation service."""
    
    def __init__(self, db: AsyncSession, tenant: str):
        self.db = db
        self.tenant = tenant
        self.logger = logger.bind(tenant=tenant)
    
    # ==== SLA PERFORMANCE METRICS ====
    
    async def get_sla_breach_rate(self, window_hours: int = 24) -> KPIResult:
        """Calculate SLA breach rate with trend analysis."""
        cutoff = datetime.utcnow() - timedelta(hours=window_hours)
        
        # Total orders in window
        total_orders_query = select(func.count(func.distinct(OrderEvent.order_id))).where(
            and_(
                OrderEvent.tenant == self.tenant,
                OrderEvent.created_at >= cutoff
            )
        )
        total_orders = (await self.db.execute(total_orders_query)).scalar() or 0
        
        # Total breaches in window
        breaches_query = select(func.count()).where(
            and_(
                ExceptionRecord.tenant == self.tenant,
                ExceptionRecord.created_at >= cutoff
            )
        )
        breaches = (await self.db.execute(breaches_query)).scalar() or 0
        
        # Calculate rate
        rate = (breaches / total_orders * 100) if total_orders > 0 else 0
        
        # Get hourly trend
        trend_query = text("""
            SELECT 
                DATE_TRUNC('hour', created_at) as hour,
                COUNT(*) as breach_count,
                (SELECT COUNT(DISTINCT order_id) 
                 FROM order_events oe 
                 WHERE oe.tenant = :tenant 
                   AND DATE_TRUNC('hour', oe.created_at) = DATE_TRUNC('hour', e.created_at)
                ) as total_orders
            FROM exceptions e
            WHERE tenant = :tenant 
              AND created_at >= :cutoff
            GROUP BY DATE_TRUNC('hour', created_at)
            ORDER BY hour
        """)
        
        trend_result = await self.db.execute(trend_query, {
            "tenant": self.tenant,
            "cutoff": cutoff
        })
        
        trend = [
            {
                "time": row.hour.isoformat(),
                "value": (row.breach_count / row.total_orders * 100) if row.total_orders > 0 else 0
            }
            for row in trend_result
        ]
        
        # Determine status
        status = "good" if rate < 5 else "warning" if rate < 15 else "critical"
        
        return KPIResult(
            value=rate,
            unit="%",
            trend=trend,
            status=status,
            metadata={
                "total_orders": total_orders,
                "total_breaches": breaches,
                "window_hours": window_hours
            }
        )
    
    async def get_mttr_metrics(self, window_days: int = 7) -> Dict[str, KPIResult]:
        """Calculate MTTD, MTTR, and TTR percentiles."""
        cutoff = datetime.utcnow() - timedelta(days=window_days)
        
        # MTTR calculation
        mttr_query = text("""
            SELECT 
                EXTRACT(EPOCH FROM (resolved_at - created_at)) / 3600 as resolution_hours,
                EXTRACT(EPOCH FROM (created_at - occurred_at)) / 60 as detection_minutes,
                reason_code,
                severity
            FROM exceptions 
            WHERE tenant = :tenant 
              AND resolved_at IS NOT NULL 
              AND created_at >= :cutoff
              AND occurred_at IS NOT NULL
        """)
        
        result = await self.db.execute(mttr_query, {
            "tenant": self.tenant,
            "cutoff": cutoff
        })
        
        rows = result.fetchall()
        
        if not rows:
            return {
                "mttr": KPIResult(0, "hours", [], "warning", {"no_data": True}),
                "mttd": KPIResult(0, "minutes", [], "warning", {"no_data": True}),
                "ttr_p90": KPIResult(0, "hours", [], "warning", {"no_data": True})
            }
        
        resolution_times = [row.resolution_hours for row in rows if row.resolution_hours]
        detection_times = [row.detection_minutes for row in rows if row.detection_minutes]
        
        mttr = np.mean(resolution_times) if resolution_times else 0
        mttd = np.mean(detection_times) if detection_times else 0
        ttr_p90 = np.percentile(resolution_times, 90) if resolution_times else 0
        
        # Daily trend for MTTR
        daily_trend_query = text("""
            SELECT 
                DATE(created_at) as day,
                AVG(EXTRACT(EPOCH FROM (resolved_at - created_at)) / 3600) as avg_mttr
            FROM exceptions 
            WHERE tenant = :tenant 
              AND resolved_at IS NOT NULL 
              AND created_at >= :cutoff
            GROUP BY DATE(created_at)
            ORDER BY day
        """)
        
        trend_result = await self.db.execute(daily_trend_query, {
            "tenant": self.tenant,
            "cutoff": cutoff
        })
        
        trend = [
            {"time": row.day.isoformat(), "value": float(row.avg_mttr)}
            for row in trend_result
        ]
        
        return {
            "mttr": KPIResult(
                value=mttr,
                unit="hours",
                trend=trend,
                status="good" if mttr < 24 else "warning" if mttr < 72 else "critical",
                metadata={"sample_size": len(resolution_times)}
            ),
            "mttd": KPIResult(
                value=mttd,
                unit="minutes",
                trend=[],
                status="good" if mttd < 30 else "warning" if mttd < 120 else "critical",
                metadata={"sample_size": len(detection_times)}
            ),
            "ttr_p90": KPIResult(
                value=ttr_p90,
                unit="hours",
                trend=[],
                status="good" if ttr_p90 < 48 else "warning" if ttr_p90 < 120 else "critical",
                metadata={"percentile": 90}
            )
        }
    
    # ==== FINANCIAL IMPACT METRICS ====
    
    async def get_revenue_at_risk(self) -> KPIResult:
        """Calculate current revenue at risk from active exceptions."""
        query = text("""
            SELECT 
                id,
                severity,
                reason_code,
                context_data,
                created_at
            FROM exceptions 
            WHERE tenant = :tenant 
              AND status IN ('OPEN', 'IN_PROGRESS')
        """)
        
        result = await self.db.execute(query, {"tenant": self.tenant})
        exceptions = result.fetchall()
        
        total_risk = 0
        risk_by_reason = {}
        
        # Risk multipliers based on severity
        risk_multipliers = {
            "CRITICAL": 0.8,
            "HIGH": 0.5,
            "MEDIUM": 0.2,
            "LOW": 0.05
        }
        
        for exc in exceptions:
            if exc.context_data and "order_value" in exc.context_data:
                order_value = float(exc.context_data["order_value"])
                multiplier = risk_multipliers.get(exc.severity, 0.1)
                risk = order_value * multiplier
                total_risk += risk
                
                if exc.reason_code not in risk_by_reason:
                    risk_by_reason[exc.reason_code] = 0
                risk_by_reason[exc.reason_code] += risk
        
        # Weekly trend
        weekly_trend_query = text("""
            SELECT 
                DATE_TRUNC('day', created_at) as day,
                COUNT(*) as active_count,
                AVG(CASE 
                    WHEN context_data->>'order_value' IS NOT NULL 
                    THEN (context_data->>'order_value')::numeric * 
                         CASE severity 
                            WHEN 'CRITICAL' THEN 0.8 
                            WHEN 'HIGH' THEN 0.5 
                            WHEN 'MEDIUM' THEN 0.2 
                            ELSE 0.05 END
                    ELSE 0 END) as avg_risk
            FROM exceptions 
            WHERE tenant = :tenant 
              AND created_at >= NOW() - INTERVAL '7 days'
            GROUP BY DATE_TRUNC('day', created_at)
            ORDER BY day
        """)
        
        trend_result = await self.db.execute(weekly_trend_query, {"tenant": self.tenant})
        trend = [
            {"time": row.day.isoformat(), "value": float(row.avg_risk or 0)}
            for row in trend_result
        ]
        
        status = "good" if total_risk < 10000 else "warning" if total_risk < 50000 else "critical"
        
        return KPIResult(
            value=total_risk,
            unit="$",
            trend=trend,
            status=status,
            metadata={
                "active_exceptions": len(exceptions),
                "risk_by_reason": risk_by_reason,
                "disclaimer": "Mathematical analysis based on active exceptions and estimated impact"
            }
        )
    
    async def get_invoice_adjustments(self, window_days: int = 30) -> Dict[str, KPIResult]:
        """Calculate invoice adjustment metrics."""
        cutoff = datetime.utcnow() - timedelta(days=window_days)
        
        # Total adjustments
        adjustments_query = select(
            func.count().label("total_adjustments"),
            func.sum(func.abs(InvoiceAdjustment.delta_cents)).label("total_amount"),
            func.avg(func.abs(InvoiceAdjustment.delta_cents)).label("avg_amount")
        ).where(
            and_(
                InvoiceAdjustment.tenant == self.tenant,
                InvoiceAdjustment.created_at >= cutoff
            )
        )
        
        result = await self.db.execute(adjustments_query)
        row = result.first()
        
        total_adjustments = row.total_adjustments or 0
        total_amount = (row.total_amount or 0) / 100  # Convert to dollars
        avg_amount = (row.avg_amount or 0) / 100
        
        # Adjustment rate (need total invoices)
        invoices_query = select(func.count()).where(
            and_(
                Invoice.tenant == self.tenant,
                Invoice.created_at >= cutoff
            )
        )
        total_invoices = (await self.db.execute(invoices_query)).scalar() or 0
        
        adjustment_rate = (total_adjustments / total_invoices * 100) if total_invoices > 0 else 0
        
        return {
            "realized_adjustments": KPIResult(
                value=total_amount,
                unit="$",
                trend=[],
                status="good" if total_amount < 5000 else "warning" if total_amount < 20000 else "critical",
                metadata={"total_adjustments": total_adjustments}
            ),
            "adjustment_rate": KPIResult(
                value=adjustment_rate,
                unit="%",
                trend=[],
                status="good" if adjustment_rate < 5 else "warning" if adjustment_rate < 15 else "critical",
                metadata={"total_invoices": total_invoices}
            ),
            "avg_adjustment": KPIResult(
                value=avg_amount,
                unit="$",
                trend=[],
                status="good" if avg_amount < 100 else "warning" if avg_amount < 500 else "critical",
                metadata={"sample_size": total_adjustments}
            )
        }
    
    # ==== AI EFFECTIVENESS METRICS ====
    
    async def get_ai_metrics(self, window_days: int = 7) -> Dict[str, KPIResult]:
        """Calculate comprehensive AI effectiveness metrics."""
        cutoff = datetime.utcnow() - timedelta(days=window_days)
        
        # AI coverage and performance
        ai_query = text("""
            SELECT 
                COUNT(*) as total_exceptions,
                COUNT(CASE WHEN ai_confidence IS NOT NULL THEN 1 END) as ai_analyzed,
                COUNT(CASE WHEN ai_confidence >= 0.8 THEN 1 END) as high_confidence,
                COUNT(CASE WHEN ai_confidence >= 0.7 THEN 1 END) as acceptable_confidence,
                AVG(ai_confidence) as avg_confidence,
                COUNT(CASE WHEN status = 'RESOLVED' AND ai_confidence >= 0.8 THEN 1 END) as auto_resolved
            FROM exceptions 
            WHERE tenant = :tenant 
              AND created_at >= :cutoff
        """)
        
        result = await self.db.execute(ai_query, {
            "tenant": self.tenant,
            "cutoff": cutoff
        })
        row = result.first()
        
        total_exceptions = row.total_exceptions or 0
        ai_analyzed = row.ai_analyzed or 0
        high_confidence = row.high_confidence or 0
        acceptable_confidence = row.acceptable_confidence or 0
        avg_confidence = row.avg_confidence or 0
        auto_resolved = row.auto_resolved or 0
        
        # Calculate rates
        coverage_rate = (ai_analyzed / total_exceptions * 100) if total_exceptions > 0 else 0
        acceptance_rate = (acceptable_confidence / ai_analyzed * 100) if ai_analyzed > 0 else 0
        deflection_rate = (auto_resolved / total_exceptions * 100) if total_exceptions > 0 else 0
        
        # Confidence distribution
        confidence_dist_query = text("""
            SELECT 
                CASE 
                    WHEN ai_confidence >= 0.9 THEN '90-100%'
                    WHEN ai_confidence >= 0.8 THEN '80-90%'
                    WHEN ai_confidence >= 0.7 THEN '70-80%'
                    WHEN ai_confidence >= 0.6 THEN '60-70%'
                    ELSE '<60%'
                END as confidence_bucket,
                COUNT(*) as count
            FROM exceptions 
            WHERE tenant = :tenant 
              AND ai_confidence IS NOT NULL
              AND created_at >= :cutoff
            GROUP BY 1
            ORDER BY 1
        """)
        
        dist_result = await self.db.execute(confidence_dist_query, {
            "tenant": self.tenant,
            "cutoff": cutoff
        })
        
        confidence_distribution = [
            {"bucket": row.confidence_bucket, "count": row.count}
            for row in dist_result
        ]
        
        return {
            "ai_coverage": KPIResult(
                value=coverage_rate,
                unit="%",
                trend=[],
                status="good" if coverage_rate > 80 else "warning" if coverage_rate > 60 else "critical",
                metadata={"total_analyzed": ai_analyzed, "total_exceptions": total_exceptions}
            ),
            "ai_acceptance": KPIResult(
                value=acceptance_rate,
                unit="%",
                trend=[],
                status="good" if acceptance_rate > 85 else "warning" if acceptance_rate > 70 else "critical",
                metadata={"acceptable_count": acceptable_confidence}
            ),
            "ai_deflection": KPIResult(
                value=deflection_rate,
                unit="%",
                trend=[],
                status="good" if deflection_rate > 30 else "warning" if deflection_rate > 15 else "critical",
                metadata={"auto_resolved": auto_resolved}
            ),
            "avg_confidence": KPIResult(
                value=avg_confidence * 100,
                unit="%",
                trend=[],
                status="good" if avg_confidence > 0.8 else "warning" if avg_confidence > 0.7 else "critical",
                metadata={"confidence_distribution": confidence_distribution}
            )
        }
    
    # ==== OPERATIONAL HEALTH METRICS ====
    
    async def get_dlq_metrics(self) -> Dict[str, KPIResult]:
        """Calculate DLQ health metrics."""
        # Current DLQ depth
        depth_query = select(func.count()).where(
            and_(
                DLQ.tenant == self.tenant,
                DLQ.status == "PENDING"
            )
        )
        current_depth = (await self.db.execute(depth_query)).scalar() or 0
        
        # DLQ aging
        aging_query = text("""
            SELECT 
                EXTRACT(EPOCH FROM (NOW() - created_at)) / 3600 as age_hours
            FROM dlq 
            WHERE tenant = :tenant 
              AND status = 'PENDING'
            ORDER BY age_hours DESC
        """)
        
        aging_result = await self.db.execute(aging_query, {"tenant": self.tenant})
        ages = [row.age_hours for row in aging_result]
        
        p90_age = np.percentile(ages, 90) if ages else 0
        
        # Replay success rate (last 7 days)
        replay_query = text("""
            SELECT 
                COUNT(*) as total_replays,
                COUNT(CASE WHEN status = 'PROCESSED' THEN 1 END) as successful_replays
            FROM dlq 
            WHERE tenant = :tenant 
              AND updated_at >= NOW() - INTERVAL '7 days'
              AND attempts > 0
        """)
        
        replay_result = await self.db.execute(replay_query, {"tenant": self.tenant})
        replay_row = replay_result.first()
        
        total_replays = replay_row.total_replays or 0
        successful_replays = replay_row.successful_replays or 0
        replay_success_rate = (successful_replays / total_replays * 100) if total_replays > 0 else 100
        
        return {
            "dlq_depth": KPIResult(
                value=current_depth,
                unit="items",
                trend=[],
                status="good" if current_depth < 10 else "warning" if current_depth < 50 else "critical",
                metadata={"oldest_age_hours": max(ages) if ages else 0}
            ),
            "dlq_aging_p90": KPIResult(
                value=p90_age,
                unit="hours",
                trend=[],
                status="good" if p90_age < 4 else "warning" if p90_age < 24 else "critical",
                metadata={"sample_size": len(ages)}
            ),
            "replay_success_rate": KPIResult(
                value=replay_success_rate,
                unit="%",
                trend=[],
                status="good" if replay_success_rate > 90 else "warning" if replay_success_rate > 75 else "critical",
                metadata={"total_replays": total_replays, "successful_replays": successful_replays}
            )
        }
    
    # ==== CHART DATA GENERATION ====
    
    async def get_sla_risk_heatmap(self, days: int = 7) -> ChartData:
        """Generate SLA risk heatmap data."""
        cutoff = datetime.utcnow() - timedelta(days=days)
        
        query = text("""
            SELECT 
                EXTRACT(hour FROM created_at) as hour,
                reason_code,
                COUNT(*) as breach_count,
                SUM(CASE WHEN context_data->>'order_value' IS NOT NULL 
                    THEN (context_data->>'order_value')::numeric * 
                         CASE severity 
                            WHEN 'CRITICAL' THEN 0.8 
                            WHEN 'HIGH' THEN 0.5 
                            WHEN 'MEDIUM' THEN 0.2 
                            ELSE 0.05 END
                    ELSE 0 END) as revenue_risk
            FROM exceptions 
            WHERE tenant = :tenant 
              AND created_at >= :cutoff
            GROUP BY 1, 2
            ORDER BY 1, 2
        """)
        
        result = await self.db.execute(query, {
            "tenant": self.tenant,
            "cutoff": cutoff
        })
        
        data = [
            {
                "hour": int(row.hour),
                "reason_code": row.reason_code,
                "breach_count": row.breach_count,
                "revenue_risk": float(row.revenue_risk)
            }
            for row in result
        ]
        
        return ChartData(
            data=data,
            chart_type="heatmap",
            config={
                "x_axis": "hour",
                "y_axis": "reason_code",
                "value": "revenue_risk",
                "color_scale": "reds"
            },
            annotations=[
                {"type": "line", "value": 9, "label": "Business Hours Start"},
                {"type": "line", "value": 17, "label": "Business Hours End"}
            ]
        )
    
    async def get_revenue_risk_pareto(self) -> ChartData:
        """Generate revenue risk Pareto chart data."""
        query = text("""
            WITH risk_by_reason AS (
                SELECT 
                    reason_code,
                    COUNT(*) as exception_count,
                    SUM(CASE WHEN context_data->>'order_value' IS NOT NULL 
                        THEN (context_data->>'order_value')::numeric * 
                             CASE severity 
                                WHEN 'CRITICAL' THEN 0.8 
                                WHEN 'HIGH' THEN 0.5 
                                WHEN 'MEDIUM' THEN 0.2 
                                ELSE 0.05 END
                        ELSE 0 END) as total_risk
                FROM exceptions 
                WHERE tenant = :tenant 
                  AND status IN ('OPEN', 'IN_PROGRESS')
                GROUP BY reason_code
            ),
            cumulative AS (
                SELECT *,
                    SUM(total_risk) OVER (ORDER BY total_risk DESC) as cumulative_risk,
                    SUM(total_risk) OVER () as grand_total
                FROM risk_by_reason
            )
            SELECT 
                reason_code,
                total_risk,
                exception_count,
                (cumulative_risk / NULLIF(grand_total, 0) * 100) as cumulative_percent
            FROM cumulative
            ORDER BY total_risk DESC
        """)
        
        result = await self.db.execute(query, {"tenant": self.tenant})
        
        data = [
            {
                "reason_code": row.reason_code,
                "total_risk": float(row.total_risk),
                "exception_count": row.exception_count,
                "cumulative_percent": float(row.cumulative_percent or 0)
            }
            for row in result
        ]
        
        return ChartData(
            data=data,
            chart_type="pareto",
            config={
                "x_axis": "reason_code",
                "bar_value": "total_risk",
                "line_value": "cumulative_percent"
            },
            annotations=[
                {"type": "line", "value": 80, "label": "80% Rule", "axis": "right"}
            ]
        )
    
    async def get_ai_confidence_scatter(self, days: int = 7) -> ChartData:
        """Generate AI confidence vs resolution time scatter plot."""
        cutoff = datetime.utcnow() - timedelta(days=days)
        
        query = text("""
            SELECT 
                ai_confidence * 100 as confidence_percent,
                EXTRACT(EPOCH FROM (resolved_at - created_at)) / 3600 as resolution_hours,
                reason_code,
                severity,
                CASE severity 
                    WHEN 'CRITICAL' THEN 20
                    WHEN 'HIGH' THEN 15
                    WHEN 'MEDIUM' THEN 10
                    ELSE 5
                END as bubble_size
            FROM exceptions 
            WHERE tenant = :tenant 
              AND ai_confidence IS NOT NULL 
              AND resolved_at IS NOT NULL
              AND created_at >= :cutoff
              AND EXTRACT(EPOCH FROM (resolved_at - created_at)) / 3600 < 168  -- Less than 1 week
        """)
        
        result = await self.db.execute(query, {
            "tenant": self.tenant,
            "cutoff": cutoff
        })
        
        data = [
            {
                "confidence_percent": float(row.confidence_percent),
                "resolution_hours": float(row.resolution_hours),
                "reason_code": row.reason_code,
                "severity": row.severity,
                "bubble_size": row.bubble_size
            }
            for row in result
        ]
        
        # Calculate correlation coefficient
        if len(data) > 1:
            x_vals = [d["confidence_percent"] for d in data]
            y_vals = [d["resolution_hours"] for d in data]
            correlation, _ = stats.pearsonr(x_vals, y_vals)
            r_squared = correlation ** 2
        else:
            r_squared = 0
        
        return ChartData(
            data=data,
            chart_type="scatter",
            config={
                "x_axis": "confidence_percent",
                "y_axis": "resolution_hours",
                "color": "reason_code",
                "size": "bubble_size",
                "trend_line": True
            },
            annotations=[
                {"type": "text", "value": f"R² = {r_squared:.3f}", "position": "top-right"},
                {"type": "quadrant", "x": 80, "y": 24, "labels": ["High Conf/Fast", "High Conf/Slow", "Low Conf/Fast", "Low Conf/Slow"]}
            ]
        )
