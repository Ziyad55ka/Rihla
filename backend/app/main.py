import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.accounts import router as accounts_router
from app.api.routes.activities import router as activities_router
from app.api.routes.activity_suggestions import router as activity_suggestions_router
from app.api.routes.health import router as health_router
from app.api.routes.login import router as login_router
from app.api.routes.proposals import router as proposals_router
from app.api.routes.trips import router as trips_router
from app.core.config import Settings


def configure_logging() -> None:
    """Show Rihla's own INFO lines (generation cost, failed options) in the console.

    Only the "app" logger: httpx logs full request URLs at INFO, and SerpApi takes
    its key in the URL, so third-party loggers are left at their defaults.
    """
    logger = logging.getLogger("app")
    if logger.handlers:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build an app that can run locally without any external credentials."""
    settings = settings if settings is not None else Settings()
    configure_logging()
    application = FastAPI(
        title="Rihla API",
        description="Foundation for the SWE 444 group travel planning project.",
        version="0.1.0",
    )
    application.state.settings = settings

    @application.middleware("http")
    async def prevent_private_response_caching(request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )
    application.include_router(health_router)
    application.include_router(accounts_router)
    application.include_router(login_router)
    application.include_router(proposals_router)
    application.include_router(activities_router)
    application.include_router(activity_suggestions_router)
    application.include_router(trips_router)
    return application


app = create_app()
