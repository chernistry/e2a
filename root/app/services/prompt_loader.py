# ==== PROMPT LOADER SERVICE ==== #

"""
Prompt loader for external prompt templates.

This module provides comprehensive prompt template management with Jinja2
support, caching, fallback mechanisms, and template variable rendering
for AI-powered operations and content generation.
"""

from pathlib import Path
from typing import Dict, Optional, Any
from functools import lru_cache

try:
    from jinja2 import Template, Environment, FileSystemLoader
    JINJA2_AVAILABLE = True
except ImportError:
    JINJA2_AVAILABLE = False

from app.observability.logging import ContextualLogger


logger = ContextualLogger(__name__)

# Base directory for prompts
PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts"


# ==== PROMPT LOADER CLASS ==== #


class PromptLoader:
    """
    Loader for external prompt templates with Jinja2 support.
    
    Provides comprehensive prompt template management including file loading,
    Jinja2 rendering, caching, and fallback mechanisms for reliable
    AI prompt generation across different environments.
    """
    
    def __init__(self, prompts_dir: Optional[Path] = None):
        """
        Initialize prompt loader.
        
        Sets up Jinja2 environment if available and configures
        template loading with comprehensive fallback support.
        
        Args:
            prompts_dir (Optional[Path]): Optional custom prompts directory
        """
        self.prompts_dir = prompts_dir or PROMPTS_DIR
        self._cache: Dict[str, str] = {}
        
        # Initialize Jinja2 environment if available
        if JINJA2_AVAILABLE and self.prompts_dir.exists():
            self.jinja_env = Environment(
                loader=FileSystemLoader(str(self.prompts_dir)),
                trim_blocks=True,
                lstrip_blocks=True
            )
        else:
            self.jinja_env = None
    
    # ==== TEMPLATE LOADING AND CACHING ==== #
    
    @lru_cache(maxsize=32)
    def load_prompt(self, prompt_name: str) -> str:
        """
        Load prompt template from file.
        
        Loads prompt templates from markdown files with comprehensive
        error handling and caching for optimal performance.
        
        Args:
            prompt_name (str): Name of the prompt file (without .md extension)
            
        Returns:
            str: Prompt template content
            
        Raises:
            FileNotFoundError: If prompt file doesn't exist
            IOError: If file cannot be read
        """
        prompt_file = self.prompts_dir / f"{prompt_name}.md"
        
        if not prompt_file.exists():
            logger.error(f"Prompt file not found: {prompt_file}")
            raise FileNotFoundError(f"Prompt file not found: {prompt_name}.md")
        
        try:
            with open(prompt_file, 'r', encoding='utf-8') as f:
                content = f.read().strip()
            
            logger.debug(f"Loaded prompt template: {prompt_name}")
            return content
            
        except IOError as e:
            logger.error(f"Failed to read prompt file {prompt_file}: {e}")
            raise
    
    # ==== TEMPLATE RENDERING ==== #
    
    def render_prompt(self, prompt_name: str, **kwargs: Any) -> str:
        """
        Render prompt template with variables.
        
        Renders prompt templates using Jinja2 if available, with
        comprehensive fallback to Python string formatting for
        reliability across different environments.
        
        Args:
            prompt_name (str): Name of the prompt template
            **kwargs (Any): Template variables for rendering
            
        Returns:
            str: Rendered prompt content with variables substituted
        """
        if self.jinja_env:
            try:
                template = self.jinja_env.get_template(f"{prompt_name}.md")
                return template.render(**kwargs)
            except Exception as e:
                logger.warning(f"Jinja2 rendering failed for {prompt_name}: {e}, falling back to string format")
        
        # Fallback to simple string formatting
        prompt_content = self.load_prompt(prompt_name)
        
        # Convert Jinja2 syntax to Python format strings for fallback
        # Replace {{ variable }} with {variable}
        import re
        fallback_content = re.sub(r'\{\{\s*(\w+)\s*\}\}', r'{\1}', prompt_content)
        
        try:
            return fallback_content.format(**kwargs)
        except KeyError as e:
            logger.error(f"Missing template variable {e} for prompt {prompt_name}")
            raise
    
    # ==== SPECIALIZED PROMPT METHODS ==== #
    
    def get_exception_classification_prompt(self, **kwargs: Any) -> str:
        """
        Get rendered exception classification prompt.
        
        Provides exception classification prompts with comprehensive
        variable substitution and sensible defaults for missing values.
        
        Args:
            **kwargs (Any): Template variables (reason_code, order_id_suffix, etc.)
            
        Returns:
            str: Rendered exception classification prompt
        """
        # Provide defaults for missing variables
        context = {
            'reason_code': 'UNKNOWN',
            'order_id_suffix': 'XXX',
            'tenant': 'unknown',
            'duration_minutes': 0,
            'sla_minutes': 0,
            'delay_minutes': 0,
            **kwargs  # Override with provided values
        }
        
        return self.render_prompt("exception_classification", **context)
    
    def get_policy_linting_prompt(self, policy_type: str, policy_content: str) -> str:
        """
        Get rendered policy linting prompt.
        
        Provides policy linting prompts with type-specific context
        and content for comprehensive policy analysis.
        
        Args:
            policy_type (str): Type of policy being reviewed
            policy_content (str): Policy configuration content
            
        Returns:
            str: Rendered policy linting prompt
        """
        return self.render_prompt("policy_linting", 
                                policy_type=policy_type, 
                                policy_content=policy_content)
    
    def get_automated_resolution_prompt(self, **kwargs: Any) -> str:
        """
        Get rendered automated resolution analysis prompt.
        
        Renders the automated resolution prompt template with provided context
        for AI-powered analysis of exception resolution possibilities.
        
        Args:
            **kwargs: Context variables for prompt rendering including:
                - exception_id: Exception identifier
                - order_id: Order identifier  
                - reason_code: Exception reason code
                - Raw order data fields (without preprocessing)
                
        Returns:
            str: Rendered prompt for automated resolution analysis
        """
        return self.render_prompt("automated_resolution", **kwargs)
    
    def get_order_problem_detection_prompt(self, **kwargs: Any) -> str:
        """
        Get rendered order problem detection prompt.
        
        Renders the order problem detection prompt template with provided context
        for AI-powered analysis of order data to detect potential issues.
        
        Args:
            **kwargs: Context variables for prompt rendering including:
                - order_data: Complete raw order data (without preprocessing)
                - analysis_timestamp: Timestamp of analysis
                
        Returns:
            str: Rendered prompt for order problem detection analysis
        """
        return self.render_prompt("order_problem_detection", **kwargs)
    
    # ==== TEMPLATE MANAGEMENT ==== #
    
    def list_available_prompts(self) -> list[str]:
        """
        List all available prompt templates.
        
        Scans the prompts directory to identify available templates
        for dynamic prompt discovery and management.
        
        Returns:
            list[str]: List of available prompt names (without .md extension)
        """
        if not self.prompts_dir.exists():
            return []
        
        prompts = []
        for file_path in self.prompts_dir.glob("*.md"):
            prompts.append(file_path.stem)
        
        return sorted(prompts)
    
    def reload_prompt(self, prompt_name: str) -> str:
        """
        Reload prompt template, bypassing cache.
        
        Forces reload of prompt templates for development and testing
        scenarios where template changes need immediate effect.
        
        Args:
            prompt_name (str): Name of the prompt to reload
            
        Returns:
            str: Reloaded prompt template content
        """
        # Clear cache for this prompt
        self.load_prompt.cache_clear()
        
        # Clear Jinja2 cache if available
        if self.jinja_env:
            self.jinja_env.cache.clear()
        
        return self.load_prompt(prompt_name)


# ==== GLOBAL SERVICE INSTANCE ==== #


# Global instance
_prompt_loader: Optional[PromptLoader] = None


def get_prompt_loader() -> PromptLoader:
    """
    Get global prompt loader instance.
    
    Provides singleton access to the prompt loader for consistent
    configuration and resource management across the application.
    
    Returns:
        PromptLoader: Global prompt loader instance
    """
    global _prompt_loader
    if _prompt_loader is None:
        _prompt_loader = PromptLoader()
    return _prompt_loader
