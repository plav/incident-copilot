from fastapi import FastAPI

from app.config import settings

app = FastAPI(
    title=settings.app_name,
    description="Retrieves relevant runbook content and suggests root causes/next "
    "steps for production incidents.",
    version="0.1.0",
)


@app.get("/health")
def health_check():
    return {"status": "ok", "environment": settings.environment}
