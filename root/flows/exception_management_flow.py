# ==== EXCEPTION MANAGEMENT FLOW ==== #

"""
Prefect flow for proactive exception management and resolution in Octup E²A.

This flow implements intelligent exception handling that goes beyond simple
detection to include:
1. Exception prioritization and escalation
2. Automated resolution attempts
3. Customer communication triggers
4. Performance analytics and insights
5. Preventive measures identification

Designed for real-world operations where exceptions need active management
rather than just passive monitoring.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple

from prefect import flow, task, get_run_logger
from sqlalchemy import select, and_, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.storage.db import get_session
from app.storage.models import ExceptionRecord, OrderEvent
from app.services.ai_automated_resolution import (
    analyze_automated_resolution_possibility,
    execute_automated_actions
)


# ==== EXCEPTION ANALYSIS TASKS ==== #


@task
async def analyze_exception_patterns(
    tenant: str = "demo-3pl",
    lookback_hours: int = 168  # 1 week
) -> Dict[str, Any]:
    """
    Analyze exception patterns to identify trends and root causes.
    
    This task performs deep analysis of exception data to identify:
    - Recurring patterns and root causes
    - Peak exception times and triggers
    - Customer impact correlation
    - Prevention opportunities
    
    Args:
        tenant: Tenant to analyze
        lookback_hours: Analysis time window
        
    Returns:
        Dict with pattern analysis results
    """
    logger = get_run_logger()
    logger.info(f"Analyzing exception patterns for tenant {tenant}")
    
    async with get_session() as db:
        cutoff_time = datetime.utcnow() - timedelta(hours=lookback_hours)
        
        # Get exceptions for analysis
        query = select(ExceptionRecord).where(
            and_(
                ExceptionRecord.tenant == tenant,
                ExceptionRecord.created_at >= cutoff_time
            )
        ).order_by(desc(ExceptionRecord.created_at))
        
        result = await db.execute(query)
        exceptions = result.scalars().all()
        
        if not exceptions:
            return {
                'tenant': tenant,
                'analysis_period_hours': lookback_hours,
                'total_exceptions': 0,
                'patterns': {}
            }
        
        # Analyze patterns
        patterns = {
            'by_reason_code': {},
            'by_severity': {},
            'by_hour_of_day': {},
            'by_day_of_week': {},
            'resolution_trends': {},
            'customer_impact': {}
        }
        
        # Group by reason code
        for exc in exceptions:
            reason = exc.reason_code
            if reason not in patterns['by_reason_code']:
                patterns['by_reason_code'][reason] = {
                    'count': 0,
                    'avg_resolution_hours': 0,
                    'customer_impact_orders': []
                }
            
            patterns['by_reason_code'][reason]['count'] += 1
            patterns['by_reason_code'][reason]['customer_impact_orders'].append(exc.order_id)
            
            # Calculate resolution time if resolved
            if exc.status == 'RESOLVED' and exc.resolved_at:
                resolution_hours = (exc.resolved_at - exc.created_at).total_seconds() / 3600
                current_avg = patterns['by_reason_code'][reason]['avg_resolution_hours']
                current_count = patterns['by_reason_code'][reason]['count']
                patterns['by_reason_code'][reason]['avg_resolution_hours'] = (
                    (current_avg * (current_count - 1) + resolution_hours) / current_count
                )
        
        # Group by severity
        for exc in exceptions:
            severity = exc.severity
            patterns['by_severity'][severity] = patterns['by_severity'].get(severity, 0) + 1
        
        # Group by time patterns
        for exc in exceptions:
            hour = exc.created_at.hour
            day_of_week = exc.created_at.strftime('%A')
            
            patterns['by_hour_of_day'][hour] = patterns['by_hour_of_day'].get(hour, 0) + 1
            patterns['by_day_of_week'][day_of_week] = patterns['by_day_of_week'].get(day_of_week, 0) + 1
        
        # Identify top issues
        top_issues = sorted(
            patterns['by_reason_code'].items(),
            key=lambda x: x[1]['count'],
            reverse=True
        )[:5]
        
        # Calculate overall metrics
        total_exceptions = len(exceptions)
        resolved_exceptions = len([e for e in exceptions if e.status == 'RESOLVED'])
        critical_exceptions = len([e for e in exceptions if e.severity == 'CRITICAL'])
        
        logger.info(f"Pattern analysis complete: {total_exceptions} exceptions analyzed, "
                   f"top issue: {top_issues[0][0] if top_issues else 'None'}")
        
        return {
            'tenant': tenant,
            'analysis_period_hours': lookback_hours,
            'total_exceptions': total_exceptions,
            'resolved_exceptions': resolved_exceptions,
            'critical_exceptions': critical_exceptions,
            'resolution_rate': resolved_exceptions / total_exceptions if total_exceptions > 0 else 0,
            'patterns': patterns,
            'top_issues': top_issues,
            'insights': {
                'peak_hour': max(patterns['by_hour_of_day'].items(), key=lambda x: x[1])[0] if patterns['by_hour_of_day'] else None,
                'peak_day': max(patterns['by_day_of_week'].items(), key=lambda x: x[1])[0] if patterns['by_day_of_week'] else None,
                'most_common_issue': top_issues[0][0] if top_issues else None
            }
        }


@task
async def prioritize_active_exceptions(
    tenant: str = "demo-3pl"
) -> Dict[str, Any]:
    """
    Prioritize active exceptions based on business impact and urgency.
    
    This task implements intelligent prioritization that considers:
    - Customer impact (order value, customer tier)
    - Time sensitivity (SLA deadlines)
    - Business criticality (revenue at risk)
    - Resolution complexity
    - Resolution attempt history (NEW)
    
    Args:
        tenant: Tenant to prioritize exceptions for
        
    Returns:
        Dict with prioritized exception lists
    """
    logger = get_run_logger()
    logger.info(f"Prioritizing active exceptions for tenant {tenant}")
    
    async with get_session() as db:
        # Get all active exceptions that are eligible for resolution
        query = select(ExceptionRecord).where(
            and_(
                ExceptionRecord.tenant == tenant,
                ExceptionRecord.status.in_(['OPEN', 'IN_PROGRESS']),
                # NEW: Only include resolution-eligible exceptions
                ExceptionRecord.resolution_blocked == False,
                ExceptionRecord.resolution_attempts < ExceptionRecord.max_resolution_attempts
            )
        ).order_by(desc(ExceptionRecord.created_at))
        
        result = await db.execute(query)
        active_exceptions = result.scalars().all()
        
        # Also get blocked exceptions for reporting
        blocked_query = select(ExceptionRecord).where(
            and_(
                ExceptionRecord.tenant == tenant,
                ExceptionRecord.status.in_(['OPEN', 'IN_PROGRESS']),
                ExceptionRecord.resolution_blocked == True
            )
        )
        blocked_result = await db.execute(blocked_query)
        blocked_exceptions = blocked_result.scalars().all()
        
        if not active_exceptions:
            return {
                'tenant': tenant,
                'total_active': 0,
                'total_blocked': len(blocked_exceptions),
                'prioritized_lists': {},
                'blocked_exceptions': [
                    {
                        'id': exc.id,
                        'order_id': exc.order_id,
                        'reason_code': exc.reason_code,
                        'attempts': exc.resolution_attempts,
                        'block_reason': exc.resolution_block_reason
                    } for exc in blocked_exceptions
                ]
            }
        
        # Prioritization logic (same as before but with attempt history)
        critical_urgent = []  # Critical severity + recent
        high_impact = []      # High customer/revenue impact
        sla_risk = []         # Approaching SLA deadlines
        standard = []         # Everything else
        
        current_time = datetime.utcnow()
        sla_threshold_hours = 4  # SLA deadline
        
        for exc in active_exceptions:
            age_hours = (current_time - exc.created_at).total_seconds() / 3600
            
            # Calculate priority score
            priority_score = 0
            
            # Severity weighting
            severity_weights = {'CRITICAL': 100, 'HIGH': 75, 'MEDIUM': 50, 'LOW': 25}
            priority_score += severity_weights.get(exc.severity, 25)
            
            # Age weighting (older = higher priority)
            priority_score += min(age_hours * 2, 50)  # Cap at 50 points
            
            # SLA risk weighting
            if age_hours > (sla_threshold_hours * 0.75):  # 75% of SLA time
                priority_score += 30
            
            # NEW: Reduce priority for exceptions with previous failed attempts
            if exc.resolution_attempts > 0:
                priority_score -= (exc.resolution_attempts * 10)  # Reduce by 10 points per attempt
            
            # Categorize based on criteria
            if exc.severity == 'CRITICAL' and age_hours < 2:
                critical_urgent.append({
                    'exception': exc,
                    'priority_score': priority_score,
                    'age_hours': age_hours,
                    'resolution_attempts': exc.resolution_attempts,
                    'category': 'critical_urgent'
                })
            elif priority_score > 120:  # High impact threshold
                high_impact.append({
                    'exception': exc,
                    'priority_score': priority_score,
                    'age_hours': age_hours,
                    'resolution_attempts': exc.resolution_attempts,
                    'category': 'high_impact'
                })
            elif age_hours > (sla_threshold_hours * 0.75):
                sla_risk.append({
                    'exception': exc,
                    'priority_score': priority_score,
                    'age_hours': age_hours,
                    'resolution_attempts': exc.resolution_attempts,
                    'category': 'sla_risk'
                })
            else:
                standard.append({
                    'exception': exc,
                    'priority_score': priority_score,
                    'age_hours': age_hours,
                    'resolution_attempts': exc.resolution_attempts,
                    'category': 'standard'
                })
        
        # Sort each category by priority score
        for category_list in [critical_urgent, high_impact, sla_risk, standard]:
            category_list.sort(key=lambda x: x['priority_score'], reverse=True)
        
        logger.info(f"Exception prioritization complete: {len(critical_urgent)} critical/urgent, "
                   f"{len(high_impact)} high impact, {len(sla_risk)} SLA risk, "
                   f"{len(standard)} standard, {len(blocked_exceptions)} blocked from resolution")
        
        return {
            'tenant': tenant,
            'total_active': len(active_exceptions),
            'total_blocked': len(blocked_exceptions),
            'prioritization_timestamp': current_time.isoformat(),
            'prioritized_lists': {
                'critical_urgent': critical_urgent,
                'high_impact': high_impact,
                'sla_risk': sla_risk,
                'standard': standard
            },
            'summary': {
                'critical_urgent_count': len(critical_urgent),
                'high_impact_count': len(high_impact),
                'sla_risk_count': len(sla_risk),
                'standard_count': len(standard),
                'blocked_count': len(blocked_exceptions)
            },
            'blocked_exceptions': [
                {
                    'id': exc.id,
                    'order_id': exc.order_id,
                    'reason_code': exc.reason_code,
                    'attempts': exc.resolution_attempts,
                    'block_reason': exc.resolution_block_reason
                } for exc in blocked_exceptions
            ]
        }


@task
async def attempt_automated_resolution(
    prioritized_exceptions: Dict[str, Any],
    tenant: str = "demo-3pl"
) -> Dict[str, Any]:
    """
    Attempt AI-powered automated resolution for suitable exceptions.
    
    This task implements intelligent AI-powered automation that analyzes
    RAW order data to determine if exceptions can be resolved without
    human intervention. Now includes proper attempt tracking to prevent
    repeated failed attempts.
    
    Args:
        prioritized_exceptions: Output from prioritize_active_exceptions
        tenant: Tenant context
        
    Returns:
        Dict with automation results including AI analysis and attempt tracking
    """
    logger = get_run_logger()
    logger.info(f"Attempting AI-powered automated resolution for tenant {tenant}")
    
    if not prioritized_exceptions.get('prioritized_lists'):
        return {
            'tenant': tenant,
            'automation_attempts': 0,
            'successful_resolutions': 0,
            'failed_attempts': 0,
            'blocked_exceptions': prioritized_exceptions.get('total_blocked', 0),
            'ai_analyses_performed': 0,
            'results': []
        }
    
    # Combine all exceptions for automation attempts
    all_exceptions = []
    for category_list in prioritized_exceptions['prioritized_lists'].values():
        all_exceptions.extend(category_list)
    
    automation_results = []
    successful_resolutions = 0
    failed_attempts = 0
    ai_analyses_performed = 0
    
    async with get_session() as db:
        for exc_data in all_exceptions:
            exc_id = exc_data['exception'].id
            reason_code = exc_data['exception'].reason_code
            order_id = exc_data['exception'].order_id
            current_attempts = exc_data.get('resolution_attempts', 0)
            
            # Reload the exception in this session to avoid detached object issues
            exc_query = select(ExceptionRecord).where(ExceptionRecord.id == exc_id)
            result = await db.execute(exc_query)
            exc = result.scalar_one_or_none()
            
            if not exc:
                logger.warning(f"Exception {exc_id} not found, skipping")
                continue
            
            # Skip if already resolved or blocked
            if exc.status in ['RESOLVED', 'CLOSED']:
                continue
                
            if not exc.is_resolution_eligible:
                logger.info(f"Exception {exc_id} not eligible for resolution: "
                           f"attempts={exc.resolution_attempts}/{exc.max_resolution_attempts}, "
                           f"blocked={exc.resolution_blocked}")
                continue
            
            # Increment attempt counter BEFORE trying resolution
            exc.increment_resolution_attempt()
            
            try:
                # AI-powered resolution analysis (NO random simulation!)
                ai_analysis = await analyze_automated_resolution_possibility(db, exc)
                ai_analyses_performed += 1
                
                logger.info(f"AI analysis for exception {exc.id} (attempt {exc.resolution_attempts}): "
                           f"can_resolve={ai_analysis.get('can_auto_resolve', False)}, "
                           f"confidence={ai_analysis.get('confidence', 0.0)}")
                
                # Check if AI recommends automation with sufficient confidence
                can_auto_resolve = ai_analysis.get('can_auto_resolve', False)
                confidence = ai_analysis.get('confidence', 0.0)
                success_probability = ai_analysis.get('success_probability', 0.0)
                
                # Use AI confidence thresholds (not random!)
                if can_auto_resolve and confidence >= 0.7 and success_probability >= 0.6:
                    # Execute AI-recommended automated actions
                    automated_actions = ai_analysis.get('automated_actions', [])
                    
                    if automated_actions:
                        execution_success = await execute_automated_actions(
                            db, exc, automated_actions
                        )
                        
                        if execution_success:
                            # Mark exception as resolved
                            exc.status = 'RESOLVED'
                            exc.resolved_at = datetime.utcnow()
                            exc.ops_note = (
                                f"AI-resolved via {', '.join(automated_actions)} "
                                f"(attempt {exc.resolution_attempts}, confidence: {confidence:.2f}, "
                                f"success_prob: {success_probability:.2f})"
                            )
                            
                            successful_resolutions += 1
                            
                            automation_results.append({
                                'exception_id': exc.id,
                                'order_id': exc.order_id,
                                'reason_code': reason_code,
                                'attempt_number': exc.resolution_attempts,
                                'automation_attempted': True,
                                'result': 'resolved',
                                'ai_analysis': ai_analysis,
                                'actions_executed': automated_actions
                            })
                            
                            logger.info(f"AI auto-resolved exception {exc.id} ({reason_code}) "
                                       f"for order {exc.order_id} on attempt {exc.resolution_attempts} "
                                       f"using {automated_actions}")
                        else:
                            failed_attempts += 1
                            automation_results.append({
                                'exception_id': exc.id,
                                'order_id': exc.order_id,
                                'reason_code': reason_code,
                                'attempt_number': exc.resolution_attempts,
                                'automation_attempted': True,
                                'result': 'execution_failed',
                                'ai_analysis': ai_analysis,
                                'action_required': 'manual_intervention',
                                'blocked': exc.resolution_blocked
                            })
                            
                            # If max attempts reached, add block reason
                            if exc.resolution_blocked:
                                logger.warning(f"Exception {exc.id} blocked after {exc.resolution_attempts} "
                                             f"failed attempts: {exc.resolution_block_reason}")
                    else:
                        failed_attempts += 1
                        automation_results.append({
                            'exception_id': exc.id,
                            'order_id': exc.order_id,
                            'reason_code': reason_code,
                            'attempt_number': exc.resolution_attempts,
                            'automation_attempted': False,
                            'result': 'no_actions_available',
                            'ai_analysis': ai_analysis,
                            'action_required': 'manual_review',
                            'blocked': exc.resolution_blocked
                        })
                else:
                    # AI determined automation not suitable
                    failed_attempts += 1
                    
                    # For low-confidence cases, block immediately to avoid repeated attempts
                    if confidence < 0.3:
                        exc.block_resolution(f"AI confidence too low ({confidence:.2f}) - manual review required")
                    
                    automation_results.append({
                        'exception_id': exc.id,
                        'order_id': exc.order_id,
                        'reason_code': reason_code,
                        'attempt_number': exc.resolution_attempts,
                        'automation_attempted': False,
                        'result': 'ai_not_recommended',
                        'ai_analysis': ai_analysis,
                        'action_required': 'manual_intervention',
                        'blocked': exc.resolution_blocked
                    })
                    
            except Exception as e:
                # Fallback for AI analysis failures
                failed_attempts += 1
                logger.warning(f"AI analysis failed for exception {exc.id} "
                             f"(attempt {exc.resolution_attempts}): {str(e)}")
                
                # Block exceptions with repeated AI failures
                if exc.resolution_attempts >= 2:
                    exc.block_resolution(f"Repeated AI analysis failures: {str(e)}")
                
                automation_results.append({
                    'exception_id': exc.id,
                    'order_id': exc.order_id,
                    'reason_code': reason_code,
                    'attempt_number': exc.resolution_attempts,
                    'automation_attempted': False,
                    'result': 'ai_analysis_failed',
                    'error': str(e),
                    'action_required': 'manual_review',
                    'blocked': exc.resolution_blocked
                })
        
        await db.commit()
    
    total_attempts = len(all_exceptions)
    blocked_count = prioritized_exceptions.get('total_blocked', 0)
    
    logger.info(f"AI-powered automation complete: {successful_resolutions}/{total_attempts} "
               f"exceptions resolved, {failed_attempts} failed attempts, "
               f"{blocked_count} exceptions blocked from further attempts, "
               f"{ai_analyses_performed} AI analyses performed")
    
    return {
        'tenant': tenant,
        'automation_attempts': total_attempts,
        'successful_resolutions': successful_resolutions,
        'failed_attempts': failed_attempts,
        'blocked_exceptions': blocked_count,
        'ai_analyses_performed': ai_analyses_performed,
        'automation_success_rate': successful_resolutions / total_attempts if total_attempts > 0 else 0,
        'ai_analysis_rate': ai_analyses_performed / total_attempts if total_attempts > 0 else 0,
        'results': automation_results
    }


@task
async def generate_exception_insights(
    pattern_analysis: Dict[str, Any],
    automation_results: Dict[str, Any],
    tenant: str = "demo-3pl"
) -> Dict[str, Any]:
    """
    Generate actionable insights and recommendations from exception data.
    
    This task creates business intelligence from exception patterns
    to help improve operations and prevent future issues.
    
    Args:
        pattern_analysis: Output from analyze_exception_patterns
        automation_results: Output from attempt_automated_resolution
        tenant: Tenant context
        
    Returns:
        Dict with insights and recommendations
    """
    logger = get_run_logger()
    logger.info(f"Generating exception insights for tenant {tenant}")
    
    insights = {
        'tenant': tenant,
        'analysis_timestamp': datetime.utcnow().isoformat(),
        'key_findings': [],
        'recommendations': [],
        'prevention_opportunities': [],
        'automation_opportunities': []
    }
    
    # Analyze patterns for insights
    if pattern_analysis.get('patterns'):
        patterns = pattern_analysis['patterns']
        
        # Key findings from patterns
        if patterns.get('by_reason_code'):
            top_issue = max(patterns['by_reason_code'].items(), key=lambda x: x[1]['count'])
            insights['key_findings'].append(
                f"Most common issue: {top_issue[0]} ({top_issue[1]['count']} occurrences)"
            )
        
        if pattern_analysis.get('insights', {}).get('peak_hour'):
            peak_hour = pattern_analysis['insights']['peak_hour']
            insights['key_findings'].append(
                f"Peak exception time: {peak_hour}:00 - consider proactive monitoring"
            )
        
        # Recommendations based on patterns
        if pattern_analysis.get('resolution_rate', 0) < 0.8:
            insights['recommendations'].append(
                "Resolution rate below 80% - consider additional training or process improvements"
            )
        
        # Prevention opportunities
        for reason_code, data in patterns.get('by_reason_code', {}).items():
            if data['count'] > 5:  # Frequent issues
                insights['prevention_opportunities'].append({
                    'issue_type': reason_code,
                    'frequency': data['count'],
                    'suggestion': f"Implement preventive measures for {reason_code} - occurs {data['count']} times"
                })
    
    # Analyze automation results
    if automation_results.get('automation_success_rate', 0) > 0:
        success_rate = automation_results['automation_success_rate']
        insights['automation_opportunities'].append(
            f"Current automation success rate: {success_rate:.1%} - "
            f"consider expanding automation for successful patterns"
        )
    
    # Generate specific recommendations
    insights['recommendations'].extend([
        "Implement proactive monitoring during peak exception hours",
        "Develop automation rules for frequently occurring, resolvable issues",
        "Create customer communication templates for common exception types",
        "Establish escalation procedures for critical exceptions"
    ])
    
    logger.info(f"Generated {len(insights['key_findings'])} key findings and "
               f"{len(insights['recommendations'])} recommendations")
    
    return insights


# ==== MAIN FLOW ==== #


@flow(name="exception-management-pipeline", log_prints=True)
async def exception_management_pipeline(
    tenant: str = "demo-3pl",
    analysis_hours: int = 168  # 1 week for pattern analysis
) -> Dict[str, Any]:
    """
    Comprehensive exception management pipeline.
    
    This flow implements proactive exception management that goes beyond
    simple monitoring to include intelligent analysis, prioritization,
    automated resolution, and continuous improvement insights.
    
    Args:
        tenant: Tenant to process
        analysis_hours: Time window for pattern analysis
        
    Returns:
        Dict with complete pipeline results
    """
    logger = get_run_logger()
    logger.info(f"Starting exception management pipeline for tenant {tenant}")
    
    # Step 1: Analyze exception patterns for insights
    pattern_analysis = await analyze_exception_patterns(tenant, analysis_hours)
    
    # Step 2: Prioritize active exceptions
    prioritized_exceptions = await prioritize_active_exceptions(tenant)
    
    # Step 3: Attempt automated resolution
    automation_results = await attempt_automated_resolution(prioritized_exceptions, tenant)
    
    # Step 4: Generate actionable insights
    insights = await generate_exception_insights(pattern_analysis, automation_results, tenant)
    
    # Compile comprehensive results
    pipeline_results = {
        'tenant': tenant,
        'execution_time': datetime.utcnow().isoformat(),
        'pattern_analysis': pattern_analysis,
        'exception_prioritization': prioritized_exceptions,
        'automation_results': automation_results,
        'insights_and_recommendations': insights,
        'summary': {
            'total_exceptions_analyzed': pattern_analysis.get('total_exceptions', 0),
            'active_exceptions': prioritized_exceptions.get('total_active', 0),
            'automated_resolutions': automation_results.get('successful_resolutions', 0),
            'key_insights_count': len(insights.get('key_findings', [])),
            'recommendations_count': len(insights.get('recommendations', []))
        }
    }
    
    logger.info(f"Exception management pipeline completed: "
               f"{pipeline_results['summary']['total_exceptions_analyzed']} exceptions analyzed, "
               f"{pipeline_results['summary']['automated_resolutions']} auto-resolved, "
               f"{pipeline_results['summary']['key_insights_count']} insights generated")
    
    return pipeline_results


# ==== DEPLOYMENT HELPER ==== #

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Exception Management Pipeline")
    parser.add_argument("--tenant", default="demo-3pl", help="Tenant to process")
    parser.add_argument("--hours", type=int, default=168, help="Analysis window hours")
    parser.add_argument("--run", action="store_true", help="Run the flow immediately")
    parser.add_argument("--serve", action="store_true", help="Serve the flow for scheduling")
    
    args = parser.parse_args()
    
    if args.run:
        # Run the flow immediately
        asyncio.run(exception_management_pipeline(args.tenant, args.hours))
    elif args.serve:
        # Serve the flow for scheduling
        print(f"Serving exception management pipeline for tenant {args.tenant}")
        print("This would set up a scheduled deployment in a real environment")
    else:
        print("Use --run to execute immediately or --serve to set up scheduling")
