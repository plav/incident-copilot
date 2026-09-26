from contextlib import asynccontextmanager

from fastapi import FastAPI, Query

from app.db import close_pool, db_healthy, open_pool
from app.search import search_runbooks


@asynccontextmanager
async def lifespan(app: FastAPI):
    open_pool()
    yield
    close_pool()


app = FastAPI(title="Incident Copilot", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok", "db": "ok" if db_healthy() else "down"}


@app.get("/search")
def search(
    q: str = Query(..., min_length=3, description="Incident description or symptoms"),
    k: int = Query(5, ge=1, le=20, description="Number of chunks to return"),
):
    return {"query": q, "results": search_runbooks(q, k)}
