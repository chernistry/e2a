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
- Financial Status: {{ financial_status }}
- Fulfillment Status: {{ fulfillment_status }}
- Total Price: ${{ total_price }}
- Currency: {{ currency }}
- Created: {{ created_at }}
- Updated: {{ updated_at }}
{%- if payment_issues is defined %}
- Payment Issues: {{ payment_issues }}
{%- endif %}
{%- if shipping_address is defined %}
- Shipping Address: {{ shipping_address }}
{%- endif %}
{%- if customer is defined %}
- Customer: {{ customer }}
{%- endif %}
{%- if line_items is defined %}
- Line Items: {{ line_items | length }} items
{%- endif %}
{%- if fulfillment_delay_hours is defined %}
- Fulfillment Delay: {{ fulfillment_delay_hours }} hours
{%- endif %}
{%- if estimated_delivery_date is defined %}
- Expected Delivery: {{ estimated_delivery_date }}
{%- endif %}

**Your Analysis Task:**
Look at this raw order data and determine:

1. **What is the actual problem?** 
   - Is payment stuck? → PAYMENT_FAILED
   - Is address invalid? → ADDRESS_ERROR or ADDRESS_INVALID  
   - Is fulfillment delayed? → PICK_DELAY, PACK_DELAY, or SHIP_DELAY
   - Is carrier having issues? → CARRIER_ISSUE or DELIVERY_DELAY
   - Is inventory missing? → INVENTORY_SHORTAGE or STOCK_MISMATCH

2. **What evidence supports your conclusion?**
   - financial_status = "pending" suggests payment issues
   - fulfillment_status = "pending" for old orders suggests delays
   - Invalid postal codes suggest address problems
   - Missing line items suggest inventory issues

3. **How severe is this issue?**
   - High-value orders are more critical
   - Long delays are more severe
   - Payment failures need immediate attention

**Analysis Guidelines:**
- Base your classification ONLY on the raw data provided
- Don't assume pre-existing classifications
- Look for patterns in the data that indicate specific problems
- Consider timing, amounts, and status fields
- Provide specific evidence for your classification

Analyze the raw data and determine what actually went wrong.
