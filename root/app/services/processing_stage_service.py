"""Processing stage service for managing order processing stages and data completeness."""

import datetime as dt
import logging
from typing import Dict, List, Optional, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import and_, or_, func, select

from app.storage.models import OrderProcessingStage, DataCompletenessCheck

logger = logging.getLogger(__name__)


class ProcessingStageService:
    """Service for managing order processing stages and data completeness tracking."""
    
    # Standard processing stages
    STANDARD_STAGES = [
        "data_ingestion",
        "data_validation", 
        "data_transformation",
        "business_rules",
        "ai_processing",
        "output_generation",
        "delivery"
    ]
    
    # Stage dependencies mapping
    STAGE_DEPENDENCIES = {
        "data_validation": ["data_ingestion"],
        "data_transformation": ["data_validation"],
        "business_rules": ["data_transformation"],
        "ai_processing": ["business_rules"],
        "output_generation": ["ai_processing"],
        "delivery": ["output_generation"]
    }
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def initialize_order_stages(self, tenant: str, order_id: str, 
                              stages: Optional[List[str]] = None) -> List[OrderProcessingStage]:
        """Initialize processing stages for a new order."""
        if stages is None:
            stages = self.STANDARD_STAGES
        
        created_stages = []
        
        for stage_name in stages:
            # Check if stage already exists
            result = await self.db.execute(
                select(OrderProcessingStage).filter(
                    and_(
                        OrderProcessingStage.tenant == tenant,
                        OrderProcessingStage.order_id == order_id,
                        OrderProcessingStage.stage_name == stage_name
                    )
                )
            )
            existing = result.scalar_one_or_none()
            
            if existing:
                logger.info(f"Stage {stage_name} already exists for order {order_id}")
                created_stages.append(existing)
                continue
            
            # Determine if dependencies are met
            dependencies_met = await self._check_dependencies_met(tenant, order_id, stage_name)
            
            stage = OrderProcessingStage(
                tenant=tenant,
                order_id=order_id,
                stage_name=stage_name,
                stage_status="PENDING",
                dependencies_met=dependencies_met,
                retry_count=0,
                max_retries=3
            )
            
            self.db.add(stage)
            created_stages.append(stage)
            
        await self.db.commit()
        logger.info(f"Initialized {len(created_stages)} stages for order {order_id}")
        return created_stages
    
    async def start_stage(self, tenant: str, order_id: str, stage_name: str) -> Optional[OrderProcessingStage]:
        """Start a processing stage."""
        stage = await self._get_stage(tenant, order_id, stage_name)
        if not stage:
            logger.error(f"Stage {stage_name} not found for order {order_id}")
            return None
        
        if not stage.is_eligible_to_run:
            logger.warning(f"Stage {stage_name} is not eligible to run for order {order_id}")
            return None
        
        stage.stage_status = "RUNNING"
        stage.started_at = dt.datetime.utcnow()
        
        await self.db.commit()
        logger.info(f"Started stage {stage_name} for order {order_id}")
        return stage
    
    async def complete_stage(self, tenant: str, order_id: str, stage_name: str, 
                      stage_data: Optional[Dict[str, Any]] = None) -> Optional[OrderProcessingStage]:
        """Complete a processing stage successfully."""
        stage = await self._get_stage(tenant, order_id, stage_name)
        if not stage:
            return None
        
        stage.stage_status = "COMPLETED"
        stage.completed_at = dt.datetime.utcnow()
        if stage_data:
            stage.stage_data = stage_data
        
        # Update dependencies for downstream stages
        await self._update_downstream_dependencies(tenant, order_id, stage_name)
        
        await self.db.commit()
        logger.info(f"Completed stage {stage_name} for order {order_id}")
        return stage
    
    async def fail_stage(self, tenant: str, order_id: str, stage_name: str, 
                  error_message: str) -> Optional[OrderProcessingStage]:
        """Mark a processing stage as failed."""
        stage = await self._get_stage(tenant, order_id, stage_name)
        if not stage:
            return None
        
        stage.stage_status = "FAILED"
        stage.failed_at = dt.datetime.utcnow()
        stage.error_message = error_message
        stage.retry_count += 1
        
        # Reset to PENDING if retries available
        if stage.retry_count < stage.max_retries:
            stage.stage_status = "PENDING"
            stage.failed_at = None
            logger.info(f"Stage {stage_name} failed, retry {stage.retry_count}/{stage.max_retries}")
        else:
            logger.error(f"Stage {stage_name} permanently failed after {stage.retry_count} attempts")
        
        await self.db.commit()
        return stage
    
    async def get_order_stages(self, tenant: str, order_id: str) -> List[OrderProcessingStage]:
        """Get all processing stages for an order."""
        result = await self.db.execute(
            select(OrderProcessingStage).filter(
                and_(
                    OrderProcessingStage.tenant == tenant,
                    OrderProcessingStage.order_id == order_id
                )
            ).order_by(OrderProcessingStage.created_at)
        )
        return list(result.scalars().all())
    
    async def get_eligible_stages(self, tenant: str, limit: Optional[int] = None) -> List[OrderProcessingStage]:
        """Get stages eligible to run (dependencies met, pending status)."""
        query = select(OrderProcessingStage).filter(
            and_(
                OrderProcessingStage.tenant == tenant,
                OrderProcessingStage.stage_status == "PENDING",
                OrderProcessingStage.dependencies_met == True,
                OrderProcessingStage.retry_count < OrderProcessingStage.max_retries
            )
        ).order_by(OrderProcessingStage.created_at)
        
        if limit:
            query = query.limit(limit)
        
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def get_stage_metrics(self, tenant: str) -> Dict[str, Any]:
        """Get processing stage metrics for dashboard."""
        # Stage status counts
        result = await self.db.execute(
            select(
                OrderProcessingStage.stage_status,
                func.count(OrderProcessingStage.id)
            ).filter(
                OrderProcessingStage.tenant == tenant
            ).group_by(OrderProcessingStage.stage_status)
        )
        status_counts = dict(result.all())
        
        # Stage completion rates - simplified approach
        result = await self.db.execute(
            select(
                OrderProcessingStage.stage_name,
                func.count(OrderProcessingStage.id).label('total')
            ).filter(
                OrderProcessingStage.tenant == tenant
            ).group_by(OrderProcessingStage.stage_name)
        )
        
        completion_rates = {}
        for stat in result.all():
            stage_name = stat.stage_name
            total = stat.total or 0
            
            # Get completed count for this stage
            completed_result = await self.db.execute(
                select(func.count(OrderProcessingStage.id)).filter(
                    and_(
                        OrderProcessingStage.tenant == tenant,
                        OrderProcessingStage.stage_name == stage_name,
                        OrderProcessingStage.stage_status == 'COMPLETED'
                    )
                )
            )
            completed = completed_result.scalar() or 0
            
            # Get failed count for this stage
            failed_result = await self.db.execute(
                select(func.count(OrderProcessingStage.id)).filter(
                    and_(
                        OrderProcessingStage.tenant == tenant,
                        OrderProcessingStage.stage_name == stage_name,
                        OrderProcessingStage.stage_status == 'FAILED'
                    )
                )
            )
            failed = failed_result.scalar() or 0
            
            completion_rates[stage_name] = {
                'total': total,
                'completed': completed,
                'failed': failed,
                'completion_rate': (completed / total * 100) if total > 0 else 0
            }
        
        # Average processing times
        result = await self.db.execute(
            select(
                OrderProcessingStage.stage_name,
                func.avg(
                    func.extract('epoch', OrderProcessingStage.completed_at - OrderProcessingStage.started_at)
                ).label('avg_seconds')
            ).filter(
                and_(
                    OrderProcessingStage.tenant == tenant,
                    OrderProcessingStage.stage_status == 'COMPLETED',
                    OrderProcessingStage.started_at.isnot(None),
                    OrderProcessingStage.completed_at.isnot(None)
                )
            ).group_by(OrderProcessingStage.stage_name)
        )
        avg_times = dict(result.all())
        
        eligible_stages = await self.get_eligible_stages(tenant)
        
        return {
            'status_counts': status_counts,
            'completion_rates': completion_rates,
            'average_processing_times': avg_times,
            'eligible_stages_count': len(eligible_stages)
        }
    
    async def _get_stage(self, tenant: str, order_id: str, stage_name: str) -> Optional[OrderProcessingStage]:
        """Get a specific processing stage."""
        result = await self.db.execute(
            select(OrderProcessingStage).filter(
                and_(
                    OrderProcessingStage.tenant == tenant,
                    OrderProcessingStage.order_id == order_id,
                    OrderProcessingStage.stage_name == stage_name
                )
            )
        )
        return result.scalar_one_or_none()
    
    async def _check_dependencies_met(self, tenant: str, order_id: str, stage_name: str) -> bool:
        """Check if all dependencies for a stage are met."""
        dependencies = self.STAGE_DEPENDENCIES.get(stage_name, [])
        if not dependencies:
            return True  # No dependencies means ready to run
        
        result = await self.db.execute(
            select(func.count(OrderProcessingStage.id)).filter(
                and_(
                    OrderProcessingStage.tenant == tenant,
                    OrderProcessingStage.order_id == order_id,
                    OrderProcessingStage.stage_name.in_(dependencies),
                    OrderProcessingStage.stage_status == "COMPLETED"
                )
            )
        )
        completed_count = result.scalar()
        
        return completed_count == len(dependencies)
    
    async def _update_downstream_dependencies(self, tenant: str, order_id: str, completed_stage: str):
        """Update dependencies for stages that depend on the completed stage."""
        for stage_name, dependencies in self.STAGE_DEPENDENCIES.items():
            if completed_stage in dependencies:
                stage = await self._get_stage(tenant, order_id, stage_name)
                if stage and not stage.dependencies_met:
                    stage.dependencies_met = await self._check_dependencies_met(tenant, order_id, stage_name)


class DataCompletenessService:
    """Service for managing data completeness checks."""
    
    # Standard completeness check types
    CHECK_TYPES = [
        "required_fields",
        "data_format",
        "business_rules",
        "referential_integrity",
        "data_quality"
    ]
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def create_completeness_check(self, tenant: str, order_id: str, check_type: str) -> DataCompletenessCheck:
        """Create a new data completeness check."""
        # Check if already exists
        result = await self.db.execute(
            select(DataCompletenessCheck).filter(
                and_(
                    DataCompletenessCheck.tenant == tenant,
                    DataCompletenessCheck.order_id == order_id,
                    DataCompletenessCheck.check_type == check_type
                )
            )
        )
        existing = result.scalar_one_or_none()
        
        if existing:
            return existing
        
        check = DataCompletenessCheck(
            tenant=tenant,
            order_id=order_id,
            check_type=check_type,
            check_status="PENDING"
        )
        
        self.db.add(check)
        await self.db.commit()
        return check
    
    async def complete_check(self, tenant: str, order_id: str, check_type: str, 
                      result: Dict[str, Any], passed: bool) -> Optional[DataCompletenessCheck]:
        """Complete a data completeness check."""
        db_result = await self.db.execute(
            select(DataCompletenessCheck).filter(
                and_(
                    DataCompletenessCheck.tenant == tenant,
                    DataCompletenessCheck.order_id == order_id,
                    DataCompletenessCheck.check_type == check_type
                )
            )
        )
        check = db_result.scalar_one_or_none()
        
        if not check:
            return None
        
        check.check_status = "PASSED" if passed else "FAILED"
        check.check_result = result
        check.checked_at = dt.datetime.utcnow()
        
        await self.db.commit()
        return check
    
    async def get_order_completeness(self, tenant: str, order_id: str) -> Dict[str, Any]:
        """Get completeness status for an order."""
        result = await self.db.execute(
            select(DataCompletenessCheck).filter(
                and_(
                    DataCompletenessCheck.tenant == tenant,
                    DataCompletenessCheck.order_id == order_id
                )
            )
        )
        checks = list(result.scalars().all())
        
        total_checks = len(checks)
        passed_checks = sum(1 for check in checks if check.validation_passed)
        
        return {
            'total_checks': total_checks,
            'passed_checks': passed_checks,
            'completion_percentage': (passed_checks / total_checks * 100) if total_checks > 0 else 0,
            'checks': [
                {
                    'check_type': check.check_type,
                    'status': check.check_status,
                    'checked_at': check.checked_at,
                    'result': check.check_result
                }
                for check in checks
            ]
        }
    
    async def get_completeness_metrics(self, tenant: str) -> Dict[str, Any]:
        """Get data completeness metrics for dashboard."""
        # Overall completeness stats
        result = await self.db.execute(
            select(func.count(DataCompletenessCheck.id)).filter(
                DataCompletenessCheck.tenant == tenant
            )
        )
        total_checks = result.scalar()
        
        result = await self.db.execute(
            select(func.count(DataCompletenessCheck.id)).filter(
                and_(
                    DataCompletenessCheck.tenant == tenant,
                    DataCompletenessCheck.check_status == "PASSED"
                )
            )
        )
        passed_checks = result.scalar()
        
        # Check type breakdown
        result = await self.db.execute(
            select(
                DataCompletenessCheck.check_type,
                func.count(DataCompletenessCheck.id)
            ).filter(
                DataCompletenessCheck.tenant == tenant
            ).group_by(DataCompletenessCheck.check_type)
        )
        check_type_stats = dict(result.all())
        
        return {
            'total_checks': total_checks,
            'passed_checks': passed_checks,
            'overall_completion_rate': (passed_checks / total_checks * 100) if total_checks > 0 else 0,
            'check_type_breakdown': check_type_stats
        }
