"""Hub API entry point. Vercel keeps the public /api prefix, so routes include it."""

from fastapi import FastAPI

app = FastAPI(title="Jigworks Hub API")


@app.get("/api/health")
def health() -> dict[str, bool]:
    return {"ok": True}
