"""Hub API entry point. Vercel keeps the public /api prefix, so routes include it."""

from fastapi import FastAPI
from jigworks_contracts.models import HealthResponse

app = FastAPI(title="Jigworks Hub API")


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(ok=True)
