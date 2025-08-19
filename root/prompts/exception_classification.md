You are an expert logistics operations analyst. Analyze this RAW ORDER DATA to identify what went wrong and classify the issue.

**IMPORTANT: You are analyzing RAW order data, NOT pre-classified exceptions. Determine what the actual problem is based on the data.**

**Required JSON Response Format:**
```json
{
  "label": "EXACT_ENUM_VALUE",
  "confidence": 0.85,
  "root_cause_analysis": "Your analysis of what actually went wrong based on the raw data",
  "ops_note": "Technical analysis with specific actions for this case",
  "client_note": "Customer explanation for this specific situation",
  "recommendations": "Specific prevention measures for this type of issue",
  "priority_factors": ["actual", "factors", "from", "this", "case"],
  "reasoning": "Your logic for determining this classification from raw data"
}
```

**Valid Labels (choose the MOST APPROPRIATE one):**
PICK_DELAY, PACK_DELAY, CARRIER_ISSUE, STOCK_MISMATCH, ADDRESS_ERROR, ADDRESS_INVALID, SYSTEM_ERROR, DELIVERY_DELAY, DAMAGED_PACKAGE, CUSTOMER_UNAVAILABLE, PAYMENT_FAILED, INVENTORY_SHORTAGE, MISSING_SCAN, SHIP_DELAY, OTHER

**Raw Order Data:**
- Order ID: {{ order_id }}
- Tenant: {{ tenant }}
- Created: {{ created_at }}
{%- if financial_status is defined %}
- Financial Status: {{ financial_status }}
{%- endif %}
{%- if fulfillment_status is defined %}
- Fulfillment Status: {{ fulfillment_status }}
{%- endif %}
{%- if total_price is defined %}
- Total Price: ${{ total_price }}
{%- endif %}
{%- if currency is defined %}
- Currency: {{ currency }}
{%- endif %}
{%- if updated_at is defined %}
- Updated: {{ updated_at }}
{%- endif %}
{%- if payment_gateway_response is defined %}
- Payment Gateway Response: {{ payment_gateway_response }}
{%- endif %}
{%- if shipping_address is defined %}
- Shipping Address: {{ shipping_address }}
{%- endif %}
{%- if customer is defined %}
- Customer: {{ customer }}
{%- endif %}
{%- if line_items is defined %}
- Line Items: {{ line_items }}
{%- endif %}
{%- if inventory_snapshot is defined %}
- Inventory Snapshot: {{ inventory_snapshot }}
{%- endif %}
{%- if warehouse_events is defined %}
- Warehouse Events: {{ warehouse_events }}
{%- endif %}
{%- if estimated_delivery_date is defined %}
- Expected Delivery: {{ estimated_delivery_date }}
{%- endif %}
{%- if shipping_lines is defined %}
- Shipping Lines: {{ shipping_lines }}
{%- endif %}

**Your Analysis Task:**
Analyze ALL the raw data above and determine:

1. **What is the actual problem?** 
   - Payment gateway failures or pending status → PAYMENT_FAILED
   - Invalid addresses or postal codes → ADDRESS_ERROR or ADDRESS_INVALID  
   - Warehouse delays (stuck in pick/pack) → PICK_DELAY, PACK_DELAY
   - Shipping delays (left warehouse but delayed) → SHIP_DELAY, CARRIER_ISSUE, DELIVERY_DELAY
   - Inventory issues (not enough stock) → INVENTORY_SHORTAGE or STOCK_MISMATCH
   - System failures or missing events → SYSTEM_ERROR or MISSING_SCAN

2. **What evidence supports your conclusion?**
   - payment_gateway_response with "failed" status indicates payment failure
   - inventory_snapshot vs line_items quantity mismatch indicates stock shortage
   - warehouse_events showing stuck processes indicate fulfillment delays
   - shipping_address with invalid postal codes indicates address problems
   - fulfillment_status "pending" for days indicates operational delays

3. **Analyze timing and patterns:**
   - Compare created_at vs updated_at timestamps to detect delays
   - Look at warehouse_events to see where the order got stuck
   - Check inventory_snapshot against line_items to find shortages
   - Examine payment_gateway_response for actual failure reasons

4. **How severe is this issue?**
   - High-value orders are more critical
   - Long delays are more severe  
   - Payment failures need immediate attention
   - Inventory shortages affect multiple orders

**Analysis Guidelines:**
- Base your classification ONLY on the raw data provided above
- Don't assume pre-existing classifications or reason codes
- Look for patterns and mismatches in the data that indicate specific problems
- Consider ALL data fields, not just status fields
- Provide specific evidence from the data for your classification
- If you see inventory_snapshot and line_items, compare quantities
- If you see warehouse_events, analyze the event sequence for gaps
- If you see payment_gateway_response, check for failure indicators

Analyze the raw data comprehensively and determine what actually went wrong.
