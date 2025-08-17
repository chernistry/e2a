# AI Prompts

This directory contains external prompt templates used by the AI client service, written in Markdown format with Jinja2 templating support.

## Structure

- `exception_classification.md` - Prompt for analyzing logistics exceptions and generating operational/customer notes
- `policy_linting.md` - Prompt for reviewing policy configurations and suggesting improvements

## Usage

Prompts are loaded automatically by the `PromptLoader` class in `app/services/prompt_loader.py`. The AI client uses these external templates instead of hardcoded prompts.

### Template Engine

The system supports **Jinja2 templating** with fallback to Python string formatting:
- Primary: Jinja2 syntax `{{ variable_name }}`
- Fallback: Python format strings `{variable_name}`

### Template Variables

#### Exception Classification (`exception_classification.md`)
- `{{ reason_code }}` - Exception reason code (e.g., PICK_DELAY)
- `{{ order_id_suffix }}` - Masked order ID for privacy
- `{{ tenant }}` - Tenant identifier
- `{{ duration_minutes }}` - Actual processing duration
- `{{ sla_minutes }}` - Expected SLA duration
- `{{ delay_minutes }}` - Delay amount (duration - sla)

#### Policy Linting (`policy_linting.md`)
- `{{ policy_type }}` - Type of policy being reviewed (sla, billing, etc.)
- `{{ policy_content }}` - The actual policy configuration content

## Adding New Prompts

1. Create a new `.md` file in this directory
2. Use Jinja2 syntax for variables: `{{ variable_name }}`
3. Add a corresponding method in `PromptLoader` class
4. Update the AI client to use the new prompt

Example new prompt file:
```markdown
# My New Prompt

Analyze this {{ item_type }} with the following details:
- **ID**: {{ item_id }}
- **Status**: {{ status }}

Provide recommendations in JSON format.
```

## Fallback Behavior

If a prompt file cannot be loaded or Jinja2 is unavailable, the AI client will:
1. Fall back to Python string formatting
2. Use inline prompts as final fallback
3. Ensure system reliability is maintained

## Best Practices

- **Markdown Format**: Use `.md` extension for better readability and syntax highlighting
- **Jinja2 Syntax**: Use `{{ variable }}` for template variables
- **Clear Structure**: Use markdown headers and formatting for organization
- **JSON Examples**: Include properly formatted JSON examples in code blocks
- **Variable Defaults**: The prompt loader provides sensible defaults for missing variables
- **Error Handling**: Always include fallback behavior for missing templates

## Development

### Testing Prompts
```python
from app.services.prompt_loader import get_prompt_loader

loader = get_prompt_loader()

# Test exception classification
prompt = loader.get_exception_classification_prompt(
    reason_code="PICK_DELAY",
    order_id_suffix="123",
    tenant="demo-3pl",
    duration_minutes=150,
    sla_minutes=120,
    delay_minutes=30
)

# Test policy linting
prompt = loader.get_policy_linting_prompt(
    policy_type="sla",
    policy_content="pick_minutes: 120\npack_minutes: 180"
)
```

### Reloading Prompts
```python
# Reload a specific prompt (clears cache)
loader.reload_prompt("exception_classification")

# List available prompts
available = loader.list_available_prompts()
```

## Dependencies

- **Optional**: `jinja2` for advanced templating features
- **Fallback**: Built-in Python string formatting if Jinja2 unavailable
