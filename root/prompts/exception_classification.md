Act as a logistics operations analyst. Perform root cause analysis and return one JSON object only (no markdown).

**Schema:**
```json
{
  "label": "{{ exception_type }}",
  "confidence": 0.00,
  "root_cause_analysis": "<=150 words - WHY this happened",
  "ops_note": "<=200 words - technical analysis with actions",
  "client_note": "<=100 words - customer-friendly explanation", 
  "recommendations": "<=100 words - prevention measures",
  "priority_factors": ["list", "of", "key", "factors"],
  "reasoning": "<=50 words - analysis logic"
}
```

**Context:**
- Exception: {{ exception_type }}
- Order: {{ order_id_suffix }}
- Tenant: {{ tenant }}
- Delay: {{ delay_minutes }} min ({{ delay_percentage }}% over SLA)
- Time: {{ hour_of_day }}:00 on {{ day_of_week }}
- Peak Hours: {{ is_peak_hours }}
- Weekend: {{ is_weekend }}

**Analysis Method:**

1. **Root Cause Analysis**: Determine WHY this happened based on:
   - Timing patterns (peak hours suggest capacity issues)
   - Delay severity (>50% indicates systemic problems)
   - Operational context (weekends = reduced staffing)

2. **Priority Assessment**: Consider:
   - Business impact and urgency
   - Customer tier and order value
   - Time sensitivity and SLA criticality

3. **Recommendations**: Provide specific, actionable prevention measures

**Examples:**
- Peak hour delays → capacity constraints → dynamic staffing
- Weekend delays → reduced staffing → weekend coverage plans  
- High delay % → systemic issue → process review needed
- Recurring patterns → root cause → preventive measures

Use the exact exception_type as label. Focus on actionable insights, not just description.
