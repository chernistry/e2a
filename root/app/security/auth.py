# ==== AUTHENTICATION AND AUTHORIZATION ==== #

"""
Authentication and authorization for admin endpoints in Octup E²A.

This module provides comprehensive JWT-based authentication with secure token
validation, role-based access control, and comprehensive error handling
for protected administrative operations.
"""

import jwt
from typing import Dict, Any, Optional

from fastapi import Header, HTTPException

from app.settings import settings


# ==== AUTHENTICATION FUNCTIONS ==== #

def require_admin(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    """
    Require admin authentication for protected endpoints.
    
    Implements comprehensive JWT token validation with Bearer token extraction,
    signature verification, and payload decoding for secure administrative
    access control with detailed error reporting.
    
    Args:
        authorization (Optional[str]): Authorization header with Bearer token
        
    Returns:
        Dict[str, Any]: Decoded JWT payload with user claims
        
    Raises:
        HTTPException: If authentication fails with specific error details
    """
    try:
        # --► AUTHORIZATION HEADER VALIDATION
        if not authorization:
            raise HTTPException(
                status_code=401,
                detail="Authorization header required"
            )
        
        # --► BEARER TOKEN FORMAT VALIDATION
        if not authorization.startswith("Bearer "):
            raise HTTPException(
                status_code=401,
                detail="Invalid authorization header format"
            )
        
        # --► TOKEN EXTRACTION
        token = authorization.split(" ", 1)[1]
        
        # Decode and verify JWT
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=["HS256"]
        )
        
        # Check role
        if payload.get("role") != "admin":
            raise HTTPException(
                status_code=401,
                detail="Insufficient privileges"
            )
        
        return payload
        
    except HTTPException:
        # Re-raise HTTPExceptions as-is
        raise
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=401,
            detail="Token has expired"
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=401,
            detail="Invalid token"
        )
    except Exception:
        raise HTTPException(
            status_code=401,
            detail="Authentication failed"
        )


def create_admin_token(user_id: str, expires_in_hours: int = 24) -> str:
    """Create an admin JWT token.
    
    Args:
        user_id: User identifier
        expires_in_hours: Token expiration time in hours
        
    Returns:
        JWT token string
    """
    import datetime as dt
    
    payload = {
        "sub": user_id,
        "role": "admin",
        "iat": dt.datetime.utcnow(),
        "exp": dt.datetime.utcnow() + dt.timedelta(hours=expires_in_hours)
    }
    
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")


def verify_tenant_access(token_payload: Dict[str, Any], tenant_id: str) -> bool:
    """Verify if user has access to specific tenant.
    
    Args:
        token_payload: Decoded JWT payload
        tenant_id: Tenant identifier to check access for
        
    Returns:
        True if access is allowed, False otherwise
    """
    # For admin users, allow access to all tenants
    if token_payload.get("role") == "admin":
        return True
    
    # Check tenant-specific access
    allowed_tenants = token_payload.get("tenants", [])
    return tenant_id in allowed_tenants or "*" in allowed_tenants


def create_service_token(service_name: str, expires_in_hours: int = 8760) -> str:
    """Create a service-to-service JWT token.
    
    Args:
        service_name: Name of the service
        expires_in_hours: Token expiration time in hours (default: 1 year)
        
    Returns:
        JWT token string
    """
    import datetime as dt
    
    payload = {
        "sub": f"service:{service_name}",
        "role": "service",
        "service": service_name,
        "iat": dt.datetime.utcnow(),
        "exp": dt.datetime.utcnow() + dt.timedelta(hours=expires_in_hours)
    }
    
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")


def require_service_auth(authorization: str = Header(...)) -> Dict[str, Any]:
    """Require service authentication for internal endpoints.
    
    Args:
        authorization: Authorization header with Bearer token
        
    Returns:
        Decoded JWT payload
        
    Raises:
        HTTPException: If authentication fails
    """
    try:
        # Extract token from Bearer header
        if not authorization.startswith("Bearer "):
            raise ValueError("Invalid authorization header format")
        
        token = authorization.split(" ", 1)[1]
        
        # Decode and verify JWT
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=["HS256"]
        )
        
        # Check role
        if payload.get("role") not in ["admin", "service"]:
            raise ValueError("Insufficient privileges")
        
        return payload
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=401,
            detail="Token has expired"
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=401,
            detail="Invalid token"
        )
    except ValueError as e:
        raise HTTPException(
            status_code=401,
            detail=str(e)
        )
    except Exception:
        raise HTTPException(
            status_code=401,
            detail="Authentication failed"
        )
