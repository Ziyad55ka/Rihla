from fastapi import APIRouter

from app.schemas.health import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Report API availability without contacting external services."""
    return HealthResponse(status="ok", service="rihla-api")
