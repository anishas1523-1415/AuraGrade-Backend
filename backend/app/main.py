from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from app.config import get_settings
from app.logging_config import setup_logging
from app.middleware import request_id_middleware, register_error_handlers
from app.routers import (
    system_router,
    assessment_router,
    grading_router,
    staff_router,
    student_router,
    institutional_router,
)

def create_app() -> FastAPI:
    """AuraGrade Application Factory."""
    settings = get_settings()
    
    # ─── Initialize logging ──────────────────────────────────
    setup_logging(log_level=settings.LOG_LEVEL, is_production=settings.is_production)
    
    # ─── Initialise FastAPI app ──────────────────────────────
    app = FastAPI(
        title="AuraGrade AI Grading Engine",
        version=settings.APP_VERSION,
        description="Production-ready AI grading platform with modular architecture and enterprise security.",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # ─── Register Middleware ──────────────────────────────────
    app.middleware("http")(request_id_middleware)

    cors_origins = list(settings.cors_origins)
    if not settings.is_production:
        for local_origin in (
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:3001",
            "http://127.0.0.1:3001",
        ):
            if local_origin not in cors_origins:
                cors_origins.append(local_origin)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Accept", "X-Requested-With"],
    )

    # ─── Register Routers ─────────────────────────────────────
    app.include_router(system_router)
    app.include_router(assessment_router)
    app.include_router(grading_router)
    app.include_router(staff_router)
    app.include_router(student_router)
    app.include_router(institutional_router)

    # ─── Register Error Handlers ──────────────────────────────
    register_error_handlers(app)

    return app

# Singleton app instance
app = create_app()
