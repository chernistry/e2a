# Resolution Attempt Tracking

## Overview

This document describes the resolution attempt tracking system that prevents repeated failed automation attempts on exception records. The system addresses the issue where the exception management flow would attempt to resolve ALL exceptions on every run, including those that had already failed multiple times.

## Problem Statement

**Before:** The exception management flow processed all active exceptions without tracking previous attempts, leading to:
- Wasted computational resources on repeatedly failed attempts
- Noise in logs from repeated failures
- No visibility into processing history
- Potential infinite loops on problematic exceptions

**After:** Smart tracking system that:
- Limits resolution attempts per exception (configurable, default: 2)
- Blocks exceptions after max attempts reached
- Provides full visibility into attempt history
- Prevents processing of blocked exceptions

## Database Schema Changes

### New Fields in `exceptions` Table

```sql
-- Resolution attempt tracking
resolution_attempts INTEGER NOT NULL DEFAULT 0,
max_resolution_attempts INTEGER NOT NULL DEFAULT 2,
last_resolution_attempt_at TIMESTAMP NULL,
resolution_blocked BOOLEAN NOT NULL DEFAULT FALSE,
resolution_block_reason TEXT NULL,

-- New index for efficient querying
CREATE INDEX ix_exceptions_resolution_eligible ON exceptions 
(tenant, status, resolution_attempts, resolution_blocked);
```

### Migration

Run the migration to add these fields:

```bash
# Apply the migration
python scripts/apply_resolution_tracking.py

# Or manually with Alembic
alembic upgrade head
```

## Configuration

### Environment Variable

Control the maximum resolution attempts via environment variable:

```bash
# Set max attempts to 3 (default is 2)
export OCTUP_MAX_RESOLUTION_ATTEMPTS=3

# Verify current setting
echo $OCTUP_MAX_RESOLUTION_ATTEMPTS
```

### Configuration Class

```python
from app.config.resolution_config import ResolutionConfig

# Get current max attempts
max_attempts = ResolutionConfig.get_max_resolution_attempts()

# Check if resolution should be attempted
should_attempt = ResolutionConfig.should_attempt_resolution(current_attempts)

# Get AI confidence thresholds
thresholds = ResolutionConfig.get_ai_thresholds()
```

## Model Methods

### ExceptionRecord Methods

```python
# Check if exception is eligible for resolution
if exception.is_resolution_eligible:
    # Attempt resolution
    pass

# Increment attempt counter
exception.increment_resolution_attempt()

# Block exception from further attempts
exception.block_resolution("Custom reason")

# Reset tracking (for manual intervention)
exception.reset_resolution_tracking()
```

## Flow Behavior Changes

### Before Resolution Tracking

```python
# OLD: Processed ALL active exceptions every time
active_exceptions = db.query(ExceptionRecord).filter(
    ExceptionRecord.status.in_(['OPEN', 'IN_PROGRESS'])
).all()

# Result: 174 exceptions processed every run
```

### After Resolution Tracking

```python
# NEW: Only processes resolution-eligible exceptions
eligible_exceptions = db.query(ExceptionRecord).filter(
    and_(
        ExceptionRecord.status.in_(['OPEN', 'IN_PROGRESS']),
        ExceptionRecord.resolution_blocked == False,
        ExceptionRecord.resolution_attempts < ExceptionRecord.max_resolution_attempts
    )
).all()

# Result: Only new exceptions + those under attempt limit
```

## Blocking Logic

### Automatic Blocking Conditions

1. **Max Attempts Reached**: After `max_resolution_attempts` failed attempts
2. **Low AI Confidence**: AI confidence < 0.3 (immediate block)
3. **Repeated AI Failures**: Multiple AI analysis failures
4. **Manual Blocking**: Via `block_resolution()` method

### Block Reasons

- `"Maximum resolution attempts (2) reached"`
- `"AI confidence too low (0.15) - manual review required"`
- `"Repeated AI analysis failures: Connection timeout"`
- Custom reasons via manual blocking

## Monitoring and Visibility

### Database Queries

```sql
-- Get resolution statistics
SELECT 
    resolution_attempts,
    COUNT(*) as count
FROM exceptions 
GROUP BY resolution_attempts;

-- Get blocked exceptions
SELECT 
    id, order_id, reason_code, 
    resolution_attempts, resolution_block_reason
FROM exceptions 
WHERE resolution_blocked = true;

-- Get resolution-eligible exceptions
SELECT COUNT(*) as eligible_count
FROM exceptions 
WHERE status IN ('OPEN', 'IN_PROGRESS')
  AND resolution_blocked = false
  AND resolution_attempts < max_resolution_attempts;
```

### Flow Output

The exception management flow now includes detailed tracking information:

```json
{
  "automation_results": {
    "automation_attempts": 45,
    "successful_resolutions": 12,
    "failed_attempts": 33,
    "blocked_exceptions": 106,
    "automation_success_rate": 0.267
  },
  "prioritized_lists": {
    "summary": {
      "blocked_count": 106
    }
  },
  "blocked_exceptions": [
    {
      "id": 123,
      "order_id": "ORD-456",
      "reason_code": "LATE_SHIPMENT",
      "attempts": 2,
      "block_reason": "Maximum resolution attempts (2) reached"
    }
  ]
}
```

## Testing

### Test the System

```bash
# Run the test suite
python test_resolution_tracking.py

# Test with different max attempts
OCTUP_MAX_RESOLUTION_ATTEMPTS=1 python test_resolution_tracking.py
```

### Expected Behavior

1. **First Run**: Processes all eligible exceptions, some succeed, some fail
2. **Second Run**: Only processes exceptions with attempts < max_attempts
3. **Third Run**: Only processes new exceptions (previous ones blocked)

## Performance Impact

### Database Performance

- **New Index**: Efficient querying of resolution-eligible exceptions
- **Reduced Load**: Fewer exceptions processed per run
- **Better Scaling**: O(new_exceptions) vs O(all_exceptions)

### Processing Efficiency

**Before:**
- 174 exceptions processed every run
- Repeated AI analysis on same failed cases
- High computational waste

**After:**
- ~20-30 new/eligible exceptions per run
- No repeated processing of blocked exceptions
- 80-85% reduction in unnecessary processing

## Operational Benefits

### For Operations Teams

1. **Clear Visibility**: See exactly how many attempts were made
2. **Failure Patterns**: Identify consistently failing exception types
3. **Resource Optimization**: No wasted cycles on hopeless cases
4. **Manual Intervention**: Clear indicators when human review needed

### For Development Teams

1. **Configurable Limits**: Adjust via environment variables
2. **Debugging Support**: Full attempt history in database
3. **Performance Monitoring**: Track success rates over time
4. **Extensible Design**: Easy to add new blocking conditions

## Migration Checklist

- [ ] Run database migration: `python scripts/apply_resolution_tracking.py`
- [ ] Verify new fields exist in exceptions table
- [ ] Test exception management flow
- [ ] Set `OCTUP_MAX_RESOLUTION_ATTEMPTS` environment variable if needed
- [ ] Monitor flow logs for resolution tracking information
- [ ] Update monitoring dashboards to include blocked exception counts

## Troubleshooting

### Common Issues

**Q: All exceptions are blocked, none being processed**
A: Check if `max_resolution_attempts` is set too low or if there's a bug in blocking logic

**Q: Exceptions not being blocked after failures**
A: Verify migration was applied and `increment_resolution_attempt()` is being called

**Q: Want to retry blocked exceptions**
A: Use `reset_resolution_tracking()` method or update database directly

### Reset Blocked Exceptions

```sql
-- Reset all blocked exceptions (use carefully!)
UPDATE exceptions 
SET resolution_attempts = 0,
    resolution_blocked = false,
    resolution_block_reason = null,
    last_resolution_attempt_at = null
WHERE resolution_blocked = true;
```

## Future Enhancements

1. **Time-based Reset**: Auto-reset attempts after X days
2. **Reason-specific Limits**: Different limits per exception type
3. **Success Rate Tracking**: Track resolution success by reason code
4. **Escalation Rules**: Auto-escalate after multiple failures
5. **Dashboard Integration**: Visual monitoring of resolution metrics
