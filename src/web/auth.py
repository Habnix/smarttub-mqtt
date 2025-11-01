"""HTTP Basic Authentication middleware for FastAPI."""

from __future__ import annotations

import secrets
from typing import Optional

from fastapi import HTTPException, Request, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials


class BasicAuthMiddleware:
    """Middleware to enforce HTTP Basic Authentication on all routes."""
    
    def __init__(self, username: str, password: str):
        """Initialize Basic Auth middleware.
        
        Args:
            username: Required username
            password: Required password
        """
        self.username = username
        self.password = password
        self.security = HTTPBasic()
    
    async def __call__(self, request: Request, call_next):
        """Process request and enforce authentication.
        
        Args:
            request: Incoming HTTP request
            call_next: Next middleware/handler in chain
            
        Returns:
            Response from next handler
            
        Raises:
            HTTPException: 401 if authentication fails
        """
        # Skip auth for health check endpoint
        if request.url.path == "/health":
            return await call_next(request)
        
        # Get credentials from Authorization header
        credentials = await self._get_credentials(request)
        
        if not credentials:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
                headers={"WWW-Authenticate": "Basic"},
            )
        
        # Verify credentials using constant-time comparison
        username_correct = secrets.compare_digest(
            credentials.username.encode("utf-8"),
            self.username.encode("utf-8")
        )
        password_correct = secrets.compare_digest(
            credentials.password.encode("utf-8"),
            self.password.encode("utf-8")
        )
        
        if not (username_correct and password_correct):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
                headers={"WWW-Authenticate": "Basic"},
            )
        
        # Authentication successful, proceed to handler
        return await call_next(request)
    
    async def _get_credentials(self, request: Request) -> Optional[HTTPBasicCredentials]:
        """Extract credentials from Authorization header.
        
        Args:
            request: HTTP request
            
        Returns:
            HTTPBasicCredentials if header present, None otherwise
        """
        authorization = request.headers.get("Authorization")
        if not authorization:
            return None
        
        try:
            scheme, credentials = authorization.split(" ", 1)
            if scheme.lower() != "basic":
                return None
            
            # Decode base64 credentials
            import base64
            decoded = base64.b64decode(credentials).decode("utf-8")
            username, password = decoded.split(":", 1)
            
            return HTTPBasicCredentials(username=username, password=password)
        except Exception:
            return None


__all__ = ["BasicAuthMiddleware"]
