from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.db import open_pool, close_pool, db_healthy

@asynccontextmanager
async def lifespan(app: FastAPI):
    open_pool()
    yield
    close_pool()

app = FastAPI(lifespan=lifespan)

@app.get("/health")
def health():
    return {"status": "ok", "db": "ok" if db_healthy() else "down"}