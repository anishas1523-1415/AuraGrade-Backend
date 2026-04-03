"""
AuraGrade — Global Error Handler Middleware
===========================================
Catches unhandled exceptions and returns standardized error responses.
Prevents stack trace leaks in production.
"""

from __future__ import annotations

import time
import traceback

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.logging_config import get_logger, request_id_var, generate_request_id

logger = get_logger("middleware")


async def request_id_middleware(request: Request, call_next):
    """Add a unique request ID to every request for correlation tracking."""
    req_id = request.headers.get("X-Request-ID") or generate_request_id()
    request_id_var.set(req_id)

    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - start) * 1000, 2)

    response.headers["X-Request-ID"] = req_id
    response.headers["X-Response-Time-Ms"] = str(duration_ms)

    # Log request completion
    logger.info(
        f"{request.method} {request.url.path} -> {response.status_code} ({duration_ms}ms)",
        extra={
            "method": request.method,
            "path": str(request.url.path),
            "status_code": response.status_code,
            "duration_ms": duration_ms,
        },
    )

    return response


async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle all unhandled exceptions with safe error responses."""
    req_id = request_id_var.get()

    # Log the full exception internally
    logger.error(
        f"Unhandled exception on {request.method} {request.url.path}: {exc}",
        exc_info=True,
        extra={"method": request.method, "path": str(request.url.path)},
    )

    # Return safe response — no stack traces to client
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal server error",
            "message": "An unexpected error occurred. Please try again later.",
            "request_id": req_id,
        },
    )


def register_error_handlers(app: FastAPI) -> None:
    """Register global error handlers on the FastAPI app."""

    @app.exception_handler(Exception)
    async def handle_generic_exception(request: Request, exc: Exception):
        return await global_exception_handler(request, exc)

    @app.exception_handler(ValueError)
    async def handle_value_error(request: Request, exc: ValueError):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": "Validation error",
                "message": str(exc),
                "request_id": request_id_var.get(),
            },
        )
