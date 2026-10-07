"""Safe HTTP error responses shared by the Web API routers."""

from __future__ import annotations

import logging

from fastapi import HTTPException


def internal_server_error(logger: logging.Logger, action: str) -> HTTPException:
    """Log an active exception and return a response without its details."""
    logger.exception("%s", action)
    return HTTPException(status_code=500, detail="Internal server error")
