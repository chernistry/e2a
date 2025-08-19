"""
BI-Quality Dashboard API Routes

Provides comprehensive business intelligence endpoints with executive-grade
metrics, trend analysis, and actionable visualizations.
"""

from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.storage.db import get_db_session
from app.services.bi_metrics import BIMetricsService, KPIResult, ChartData
from app.middleware.tenancy import get_tenant_id
from app.observability.tracing import get_tracer
from app.observability.logging import ContextualLogger

logger = ContextualLogger(__name__)
tracer = get_tracer(__name__)
router = APIRouter(prefix="/api/v1/bi", tags=["BI Dashboard"])


@router.get("/kpis/overview")
async def get_kpi_overview(
    tenant: str = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Get comprehensive KPI overview for executive dashboard.
    
    Returns all key performance indicators with trends, status, and metadata
    for both operational and executive decision-making.
    """
    with tracer.start_as_current_span("bi_kpi_overview") as span:
        span.set_attribute("tenant", tenant)
        
        try:
            metrics_service = BIMetricsService(db, tenant)
            
            # Gather all KPIs concurrently
            sla_breach_rate = await metrics_service.get_sla_breach_rate()
            mttr_metrics = await metrics_service.get_mttr_metrics()
            revenue_at_risk = await metrics_service.get_revenue_at_risk()
            invoice_metrics = await metrics_service.get_invoice_adjustments()
            ai_metrics = await metrics_service.get_ai_metrics()
            dlq_metrics = await metrics_service.get_dlq_metrics()
            
            # Structure response for dashboard consumption
            response = {
                "timestamp": datetime.utcnow().isoformat(),
                "tenant": tenant,
                "sla_performance": {
                    "breach_rate": _serialize_kpi(sla_breach_rate),
                    "mttr": _serialize_kpi(mttr_metrics["mttr"]),
                    "mttd": _serialize_kpi(mttr_metrics["mttd"]),
                    "ttr_p90": _serialize_kpi(mttr_metrics["ttr_p90"])
                },
                "financial_impact": {
                    "revenue_at_risk": _serialize_kpi(revenue_at_risk),
                    "realized_adjustments": _serialize_kpi(invoice_metrics["realized_adjustments"]),
                    "adjustment_rate": _serialize_kpi(invoice_metrics["adjustment_rate"]),
                    "avg_adjustment": _serialize_kpi(invoice_metrics["avg_adjustment"])
                },
                "ai_effectiveness": {
                    "coverage": _serialize_kpi(ai_metrics["ai_coverage"]),
                    "acceptance": _serialize_kpi(ai_metrics["ai_acceptance"]),
                    "deflection": _serialize_kpi(ai_metrics["ai_deflection"]),
                    "avg_confidence": _serialize_kpi(ai_metrics["avg_confidence"])
                },
                "operational_health": {
                    "dlq_depth": _serialize_kpi(dlq_metrics["dlq_depth"]),
                    "dlq_aging_p90": _serialize_kpi(dlq_metrics["dlq_aging_p90"]),
                    "replay_success_rate": _serialize_kpi(dlq_metrics["replay_success_rate"])
                }
            }
            
            span.set_attribute("kpis_calculated", len([k for category in response.values() if isinstance(category, dict) for k in category.keys()]))
            logger.info("KPI overview calculated successfully", extra={"kpi_count": span.get_attribute("kpis_calculated")})
            
            return response
            
        except Exception as e:
            span.record_exception(e)
            logger.error("Failed to calculate KPI overview", extra={"error": str(e)})
            raise HTTPException(status_code=500, detail=f"Failed to calculate KPIs: {str(e)}")


@router.get("/charts/sla-risk-heatmap")
async def get_sla_risk_heatmap(
    days: int = Query(7, ge=1, le=30, description="Number of days to analyze"),
    tenant: str = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Get SLA risk heatmap showing breach patterns by hour and reason code.
    
    Identifies high-risk time windows and reason patterns for staffing
    and operational optimization decisions.
    """
    with tracer.start_as_current_span("bi_sla_heatmap") as span:
        span.set_attribute("tenant", tenant)
        span.set_attribute("days", days)
        
        try:
            metrics_service = BIMetricsService(db, tenant)
            chart_data = await metrics_service.get_sla_risk_heatmap(days)
            
            response = {
                "title": f"SLA Risk Heatmap ({days} days)",
                "description": "Revenue risk by hour and reason code - darker = higher risk",
                "chart_type": chart_data.chart_type,
                "data": chart_data.data,
                "config": chart_data.config,
                "annotations": chart_data.annotations,
                "metadata": {
                    "days_analyzed": days,
                    "data_points": len(chart_data.data),
                    "generated_at": datetime.utcnow().isoformat()
                }
            }
            
            logger.info("SLA risk heatmap generated", extra={"data_points": len(chart_data.data)})
            return response
            
        except Exception as e:
            span.record_exception(e)
            logger.error("Failed to generate SLA risk heatmap", extra={"error": str(e)})
            raise HTTPException(status_code=500, detail=f"Failed to generate heatmap: {str(e)}")


@router.get("/charts/revenue-risk-pareto")
async def get_revenue_risk_pareto(
    tenant: str = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Get revenue risk Pareto chart showing 80/20 analysis of exception reasons.
    
    Identifies the 20% of reasons causing 80% of financial risk for
    prioritized remediation efforts.
    """
    with tracer.start_as_current_span("bi_revenue_pareto") as span:
        span.set_attribute("tenant", tenant)
        
        try:
            metrics_service = BIMetricsService(db, tenant)
            chart_data = await metrics_service.get_revenue_risk_pareto()
            
            # Calculate 80% threshold
            total_risk = sum(d["total_risk"] for d in chart_data.data)
            pareto_80_reasons = []
            cumulative = 0
            
            for item in chart_data.data:
                cumulative += item["total_risk"]
                pareto_80_reasons.append(item["reason_code"])
                if cumulative >= total_risk * 0.8:
                    break
            
            response = {
                "title": "Revenue Risk Pareto Analysis",
                "description": "80/20 analysis - focus on top reasons driving financial risk",
                "chart_type": chart_data.chart_type,
                "data": chart_data.data,
                "config": chart_data.config,
                "annotations": chart_data.annotations,
                "insights": {
                    "total_risk": total_risk,
                    "pareto_80_reasons": pareto_80_reasons,
                    "focus_message": f"Focus on {len(pareto_80_reasons)} reason codes driving 80% of risk"
                },
                "metadata": {
                    "active_reasons": len(chart_data.data),
                    "generated_at": datetime.utcnow().isoformat()
                }
            }
            
            logger.info("Revenue risk Pareto generated", extra={"reasons_count": len(chart_data.data)})
            return response
            
        except Exception as e:
            span.record_exception(e)
            logger.error("Failed to generate revenue risk Pareto", extra={"error": str(e)})
            raise HTTPException(status_code=500, detail=f"Failed to generate Pareto: {str(e)}")


@router.get("/charts/ai-confidence-scatter")
async def get_ai_confidence_scatter(
    days: int = Query(7, ge=1, le=30, description="Number of days to analyze"),
    tenant: str = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Get AI confidence vs resolution time scatter plot with correlation analysis.
    
    Validates AI effectiveness by showing correlation between confidence
    scores and actual resolution performance.
    """
    with tracer.start_as_current_span("bi_ai_scatter") as span:
        span.set_attribute("tenant", tenant)
        span.set_attribute("days", days)
        
        try:
            metrics_service = BIMetricsService(db, tenant)
            chart_data = await metrics_service.get_ai_confidence_scatter(days)
            
            # Extract R² from annotations
            r_squared = 0
            for annotation in chart_data.annotations:
                if annotation.get("type") == "text" and "R²" in annotation.get("value", ""):
                    r_squared_str = annotation["value"].split("=")[1].strip()
                    r_squared = float(r_squared_str)
                    break
            
            # Determine correlation strength
            correlation_strength = "strong" if r_squared > 0.5 else "moderate" if r_squared > 0.25 else "weak"
            
            response = {
                "title": f"AI Confidence vs Resolution Time ({days} days)",
                "description": "Correlation analysis - validates AI effectiveness",
                "chart_type": chart_data.chart_type,
                "data": chart_data.data,
                "config": chart_data.config,
                "annotations": chart_data.annotations,
                "insights": {
                    "correlation_coefficient": r_squared,
                    "correlation_strength": correlation_strength,
                    "sample_size": len(chart_data.data),
                    "interpretation": _interpret_ai_correlation(r_squared)
                },
                "metadata": {
                    "days_analyzed": days,
                    "exceptions_analyzed": len(chart_data.data),
                    "generated_at": datetime.utcnow().isoformat()
                }
            }
            
            logger.info("AI confidence scatter generated", extra={
                "sample_size": len(chart_data.data),
                "r_squared": r_squared
            })
            return response
            
        except Exception as e:
            span.record_exception(e)
            logger.error("Failed to generate AI confidence scatter", extra={"error": str(e)})
            raise HTTPException(status_code=500, detail=f"Failed to generate scatter plot: {str(e)}")


@router.get("/charts/exception-aging-cohorts")
async def get_exception_aging_cohorts(
    days: int = Query(14, ge=7, le=30, description="Number of days to analyze"),
    tenant: str = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Get exception aging cohort analysis showing resolution patterns over time.
    
    Tracks exception resolution patterns by creation cohorts to identify
    process improvements and aging trends.
    """
    with tracer.start_as_current_span("bi_aging_cohorts") as span:
        span.set_attribute("tenant", tenant)
        span.set_attribute("days", days)
        
        try:
            metrics_service = BIMetricsService(db, tenant)
            
            # Get cohort data
            cutoff = datetime.utcnow() - timedelta(days=days)
            
            from sqlalchemy import text
            query = text("""
                SELECT 
                    DATE(created_at) as cohort_date,
                    CASE 
                        WHEN resolved_at IS NULL THEN 
                            CASE 
                                WHEN NOW() - created_at < INTERVAL '4 hours' THEN '0-4h'
                                WHEN NOW() - created_at < INTERVAL '24 hours' THEN '4-24h'
                                WHEN NOW() - created_at < INTERVAL '72 hours' THEN '1-3d'
                                ELSE '3d+'
                            END
                        ELSE 
                            CASE 
                                WHEN resolved_at - created_at < INTERVAL '4 hours' THEN '0-4h'
                                WHEN resolved_at - created_at < INTERVAL '24 hours' THEN '4-24h'
                                WHEN resolved_at - created_at < INTERVAL '72 hours' THEN '1-3d'
                                ELSE '3d+'
                            END
                    END as age_bucket,
                    COUNT(*) as exception_count,
                    COUNT(CASE WHEN resolved_at IS NOT NULL THEN 1 END) as resolved_count
                FROM exceptions 
                WHERE tenant = :tenant 
                  AND created_at >= :cutoff
                GROUP BY 1, 2
                ORDER BY 1, 2
            """)
            
            result = await db.execute(query, {
                "tenant": tenant,
                "cutoff": cutoff
            })
            
            data = []
            cohort_totals = {}
            
            for row in result:
                cohort_date = row.cohort_date.isoformat()
                if cohort_date not in cohort_totals:
                    cohort_totals[cohort_date] = 0
                cohort_totals[cohort_date] += row.exception_count
                
                data.append({
                    "cohort_date": cohort_date,
                    "age_bucket": row.age_bucket,
                    "exception_count": row.exception_count,
                    "resolved_count": row.resolved_count,
                    "resolution_rate": (row.resolved_count / row.exception_count * 100) if row.exception_count > 0 else 0
                })
            
            # Calculate aging insights
            current_open = sum(d["exception_count"] - d["resolved_count"] for d in data)
            total_exceptions = sum(cohort_totals.values())
            overall_resolution_rate = ((total_exceptions - current_open) / total_exceptions * 100) if total_exceptions > 0 else 0
            
            response = {
                "title": f"Exception Aging Cohorts ({days} days)",
                "description": "Resolution patterns by creation date - track aging trends",
                "chart_type": "cohort",
                "data": data,
                "config": {
                    "x_axis": "cohort_date",
                    "y_axis": "age_bucket",
                    "value": "exception_count",
                    "color_scale": "blues"
                },
                "annotations": [
                    {"type": "target", "bucket": "0-4h", "target": 80, "label": "Target: 80% in 4h"},
                    {"type": "target", "bucket": "4-24h", "target": 95, "label": "Target: 95% in 24h"}
                ],
                "insights": {
                    "current_open": current_open,
                    "total_exceptions": total_exceptions,
                    "overall_resolution_rate": overall_resolution_rate,
                    "aging_trend": "improving" if overall_resolution_rate > 85 else "concerning"
                },
                "metadata": {
                    "days_analyzed": days,
                    "cohorts_analyzed": len(cohort_totals),
                    "generated_at": datetime.utcnow().isoformat()
                }
            }
            
            logger.info("Exception aging cohorts generated", extra={
                "cohorts": len(cohort_totals),
                "total_exceptions": total_exceptions
            })
            return response
            
        except Exception as e:
            span.record_exception(e)
            logger.error("Failed to generate aging cohorts", extra={"error": str(e)})
            raise HTTPException(status_code=500, detail=f"Failed to generate cohorts: {str(e)}")


@router.get("/charts/processing-funnel")
async def get_processing_funnel(
    days: int = Query(7, ge=1, le=30, description="Number of days to analyze"),
    tenant: str = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Get order processing funnel showing stage drop-offs and conversion rates.
    
    Identifies bottlenecks in the order fulfillment process from creation
    to shipment with drop-off analysis by reason.
    """
    with tracer.start_as_current_span("bi_processing_funnel") as span:
        span.set_attribute("tenant", tenant)
        span.set_attribute("days", days)
        
        try:
            cutoff = datetime.utcnow() - timedelta(days=days)
            
            from sqlalchemy import text
            query = text("""
                WITH order_stages AS (
                    SELECT 
                        order_id,
                        MAX(CASE WHEN event_type = 'order_created' THEN 1 ELSE 0 END) as created,
                        MAX(CASE WHEN event_type = 'payment_confirmed' THEN 1 ELSE 0 END) as paid,
                        MAX(CASE WHEN event_type = 'pick_completed' THEN 1 ELSE 0 END) as picked,
                        MAX(CASE WHEN event_type = 'pack_completed' THEN 1 ELSE 0 END) as packed,
                        MAX(CASE WHEN event_type = 'manifested' THEN 1 ELSE 0 END) as shipped
                    FROM order_events 
                    WHERE tenant = :tenant 
                      AND created_at >= :cutoff
                    GROUP BY order_id
                ),
                funnel_counts AS (
                    SELECT 
                        SUM(created) as orders_created,
                        SUM(paid) as orders_paid,
                        SUM(picked) as orders_picked,
                        SUM(packed) as orders_packed,
                        SUM(shipped) as orders_shipped
                    FROM order_stages
                )
                SELECT * FROM funnel_counts
            """)
            
            result = await db.execute(query, {
                "tenant": tenant,
                "cutoff": cutoff
            })
            row = result.first()
            
            if not row:
                raise HTTPException(status_code=404, detail="No order data found for the specified period")
            
            # Build funnel data
            stages = [
                {"stage": "Created", "count": row.orders_created or 0, "color": "#3b82f6"},
                {"stage": "Paid", "count": row.orders_paid or 0, "color": "#06b6d4"},
                {"stage": "Picked", "count": row.orders_picked or 0, "color": "#10b981"},
                {"stage": "Packed", "count": row.orders_packed or 0, "color": "#f59e0b"},
                {"stage": "Shipped", "count": row.orders_shipped or 0, "color": "#ef4444"}
            ]
            
            # Calculate conversion rates and drop-offs
            for i in range(1, len(stages)):
                prev_count = stages[i-1]["count"]
                curr_count = stages[i]["count"]
                
                stages[i]["conversion_rate"] = (curr_count / prev_count * 100) if prev_count > 0 else 0
                stages[i]["drop_off"] = prev_count - curr_count
                stages[i]["drop_off_rate"] = ((prev_count - curr_count) / prev_count * 100) if prev_count > 0 else 0
            
            # Overall conversion rate
            overall_conversion = (stages[-1]["count"] / stages[0]["count"] * 100) if stages[0]["count"] > 0 else 0
            
            response = {
                "title": f"Order Processing Funnel ({days} days)",
                "description": "Order fulfillment conversion rates and drop-off analysis",
                "chart_type": "funnel",
                "data": stages,
                "config": {
                    "stage_field": "stage",
                    "count_field": "count",
                    "color_field": "color"
                },
                "annotations": [
                    {"type": "target", "stage": "Paid", "target": 95, "label": "Payment Target: 95%"},
                    {"type": "target", "stage": "Shipped", "target": 98, "label": "Fulfillment Target: 98%"}
                ],
                "insights": {
                    "overall_conversion": overall_conversion,
                    "biggest_drop_off": max(stages[1:], key=lambda x: x.get("drop_off", 0))["stage"],
                    "total_orders": stages[0]["count"],
                    "completed_orders": stages[-1]["count"]
                },
                "metadata": {
                    "days_analyzed": days,
                    "stages_tracked": len(stages),
                    "generated_at": datetime.utcnow().isoformat()
                }
            }
            
            logger.info("Processing funnel generated", extra={
                "total_orders": stages[0]["count"],
                "overall_conversion": overall_conversion
            })
            return response
            
        except Exception as e:
            span.record_exception(e)
            logger.error("Failed to generate processing funnel", extra={"error": str(e)})
            raise HTTPException(status_code=500, detail=f"Failed to generate funnel: {str(e)}")


@router.get("/executive-summary")
async def get_executive_summary(
    tenant: str = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Get executive summary with key insights and recommendations.
    
    Provides high-level business insights, trend analysis, and actionable
    recommendations for executive decision-making.
    """
    with tracer.start_as_current_span("bi_executive_summary") as span:
        span.set_attribute("tenant", tenant)
        
        try:
            metrics_service = BIMetricsService(db, tenant)
            
            # Get key metrics
            sla_breach_rate = await metrics_service.get_sla_breach_rate()
            revenue_at_risk = await metrics_service.get_revenue_at_risk()
            ai_metrics = await metrics_service.get_ai_metrics()
            
            # Generate insights and recommendations
            insights = []
            recommendations = []
            
            # SLA Analysis
            if sla_breach_rate.value > 10:
                insights.append(f"SLA breach rate at {sla_breach_rate.value:.1f}% - above acceptable threshold")
                recommendations.append("Immediate review of SLA policies and resource allocation needed")
            
            # Revenue Risk Analysis
            if revenue_at_risk.value > 25000:
                insights.append(f"High revenue at risk: ${revenue_at_risk.value:,.0f}")
                recommendations.append("Focus on high-value exception resolution to minimize financial impact")
            
            # AI Effectiveness Analysis
            ai_coverage = ai_metrics["ai_coverage"].value
            if ai_coverage < 80:
                insights.append(f"AI coverage at {ai_coverage:.1f}% - opportunity for automation")
                recommendations.append("Expand AI analysis to more exception types to improve efficiency")
            
            # Determine overall health
            health_score = _calculate_health_score(sla_breach_rate, revenue_at_risk, ai_metrics)
            health_status = "excellent" if health_score > 85 else "good" if health_score > 70 else "needs_attention"
            
            response = {
                "timestamp": datetime.utcnow().isoformat(),
                "tenant": tenant,
                "health_score": health_score,
                "health_status": health_status,
                "key_metrics": {
                    "sla_breach_rate": f"{sla_breach_rate.value:.1f}%",
                    "revenue_at_risk": f"${revenue_at_risk.value:,.0f}",
                    "ai_coverage": f"{ai_coverage:.1f}%",
                    "active_exceptions": revenue_at_risk.metadata.get("active_exceptions", 0)
                },
                "insights": insights,
                "recommendations": recommendations,
                "trends": {
                    "sla_trend": _analyze_trend(sla_breach_rate.trend),
                    "revenue_trend": _analyze_trend(revenue_at_risk.trend),
                    "period": "7 days"
                }
            }
            
            logger.info("Executive summary generated", extra={
                "health_score": health_score,
                "insights_count": len(insights)
            })
            return response
            
        except Exception as e:
            span.record_exception(e)
            logger.error("Failed to generate executive summary", extra={"error": str(e)})
            raise HTTPException(status_code=500, detail=f"Failed to generate summary: {str(e)}")


# ==== UTILITY FUNCTIONS ====

def _serialize_kpi(kpi: KPIResult) -> Dict[str, Any]:
    """Serialize KPI result for JSON response."""
    return {
        "value": kpi.value,
        "unit": kpi.unit,
        "status": kpi.status,
        "trend": kpi.trend,
        "metadata": kpi.metadata
    }


def _interpret_ai_correlation(r_squared: float) -> str:
    """Interpret AI confidence correlation strength."""
    if r_squared > 0.5:
        return "Strong correlation - AI confidence is a reliable predictor of resolution time"
    elif r_squared > 0.25:
        return "Moderate correlation - AI confidence provides some predictive value"
    else:
        return "Weak correlation - AI confidence may not be strongly predictive of resolution time"


def _calculate_health_score(sla_breach: KPIResult, revenue_risk: KPIResult, ai_metrics: Dict[str, KPIResult]) -> float:
    """Calculate overall system health score (0-100)."""
    # SLA component (40% weight)
    sla_score = max(0, 100 - (sla_breach.value * 2))  # Penalty for breach rate
    
    # Financial component (30% weight)
    risk_score = max(0, 100 - (revenue_risk.value / 1000))  # Penalty for revenue risk
    
    # AI component (30% weight)
    ai_score = (ai_metrics["ai_coverage"].value + ai_metrics["ai_acceptance"].value) / 2
    
    health_score = (sla_score * 0.4) + (risk_score * 0.3) + (ai_score * 0.3)
    return min(100, max(0, health_score))


def _analyze_trend(trend_data: List[Dict[str, Any]]) -> str:
    """Analyze trend direction from time series data."""
    if len(trend_data) < 2:
        return "insufficient_data"
    
    values = [point["value"] for point in trend_data]
    
    # Simple linear trend analysis
    if values[-1] > values[0] * 1.1:
        return "increasing"
    elif values[-1] < values[0] * 0.9:
        return "decreasing"
    else:
        return "stable"
