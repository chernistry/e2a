"""Configuration for automated resolution attempts."""

import os
from typing import Dict, Any


class ResolutionConfig:
    """Configuration for automated resolution behavior."""
    
    # Default maximum resolution attempts per exception
    DEFAULT_MAX_ATTEMPTS = 2
    
    # Environment variable for max attempts
    MAX_ATTEMPTS_ENV_VAR = "OCTUP_MAX_RESOLUTION_ATTEMPTS"
    
    # Confidence thresholds for AI resolution
    MIN_CONFIDENCE_THRESHOLD = 0.7
    MIN_SUCCESS_PROBABILITY = 0.6
    
    # Low confidence threshold for immediate blocking
    LOW_CONFIDENCE_BLOCK_THRESHOLD = 0.3
    
    @classmethod
    def get_max_resolution_attempts(cls) -> int:
        """Get maximum resolution attempts from environment or default."""
        try:
            return int(os.getenv(cls.MAX_ATTEMPTS_ENV_VAR, cls.DEFAULT_MAX_ATTEMPTS))
        except (ValueError, TypeError):
            return cls.DEFAULT_MAX_ATTEMPTS
    
    @classmethod
    def get_ai_thresholds(cls) -> Dict[str, float]:
        """Get AI confidence thresholds."""
        return {
            'min_confidence': cls.MIN_CONFIDENCE_THRESHOLD,
            'min_success_probability': cls.MIN_SUCCESS_PROBABILITY,
            'low_confidence_block': cls.LOW_CONFIDENCE_BLOCK_THRESHOLD
        }
    
    @classmethod
    def should_attempt_resolution(cls, exception_attempts: int, max_attempts: int = None) -> bool:
        """Check if resolution should be attempted based on attempt count."""
        if max_attempts is None:
            max_attempts = cls.get_max_resolution_attempts()
        return exception_attempts < max_attempts
    
    @classmethod
    def get_config_summary(cls) -> Dict[str, Any]:
        """Get current configuration summary."""
        return {
            'max_resolution_attempts': cls.get_max_resolution_attempts(),
            'ai_thresholds': cls.get_ai_thresholds(),
            'env_var_name': cls.MAX_ATTEMPTS_ENV_VAR,
            'default_max_attempts': cls.DEFAULT_MAX_ATTEMPTS
        }


# Convenience functions for use in flows
def get_max_attempts() -> int:
    """Get maximum resolution attempts."""
    return ResolutionConfig.get_max_resolution_attempts()


def should_attempt_resolution(attempts: int) -> bool:
    """Check if resolution should be attempted."""
    return ResolutionConfig.should_attempt_resolution(attempts)


def get_ai_confidence_thresholds() -> Dict[str, float]:
    """Get AI confidence thresholds."""
    return ResolutionConfig.get_ai_thresholds()
