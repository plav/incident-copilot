from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from app.db import close_pool, db_healthy, open_pool
from app.search import search_runbooks
from app.triage import TriageResponse, triage


@asynccontextmanager
async def lifespan(app: FastAPI):
    open_pool()
    yield
    close_pool()


app = FastAPI(title="Incident Copilot", lifespan=lifespan)


class TriageRequest(BaseModel):
    incident: str = Field(..., min_length=10, description="What's going wrong, in plain English")
    k: int = Field(8, ge=1, le=20, description="Runbook sections to retrieve")


@app.get("/health")
def health():
    return {"status": "ok", "db": "ok" if db_healthy() else "down"}


@app.get("/search")
def search(
    q: str = Query(..., min_length=3, description="Incident description or symptoms"),
    k: int = Query(5, ge=1, le=20, description="Number of chunks to return"),
):
    return {"query": q, "results": search_runbooks(q, k)}


@app.post("/triage", response_model=TriageResponse)
def triage_incident(request: TriageRequest):
    try:
        return triage(request.incident, request.k)
    except ValueError as e:
        raise HTTPException(status_code=502, detail=str(e))
