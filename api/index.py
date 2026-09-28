"""Vercel serverless entrypoint: wraps the FastAPI app with Mangum.

Vercel does not deliver ASGI lifespan events to serverless functions, so the
database seed (idempotent) runs lazily via middleware on the first request
instead of in a lifespan handler.
"""
import asyncio
import os
import sys
import types
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv(Path(__file__).parent / ".env")

MONGO_URL = os.environ.get("MONGO_URL", "")
DB_NAME = os.environ.get("DB_NAME", "voltcraft")
if not MONGO_URL:
    raise RuntimeError("MONGO_URL environment variable is not set")

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

# routes.py lazily does `from server import db`; satisfy it without a server.py.
server_module = types.ModuleType("server")
server_module.db = db
sys.modules["server"] = server_module

app = FastAPI(title="VoltCraft · Site Operations")

cors_origins = os.environ.get("CORS_ORIGINS", "*")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins.split(",") if cors_origins != "*" else ["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

from routes import router  # noqa: E402
from operations import router as operations_router  # noqa: E402

app.include_router(router, prefix="/api")
app.include_router(operations_router, prefix="/api")


@app.get("/api/health", include_in_schema=False)
async def vercel_health():
    return {"status": "ok", "app": "VoltCraft"}


# --- Idempotent seed guard (runs inside the request's event loop) ---
from seed import initialize  # noqa: E402

_seed_done = False
_seed_lock = asyncio.Lock()


@app.middleware("http")
async def ensure_seed(request, call_next):
    global _seed_done
    if not _seed_done:
        async with _seed_lock:
            if not _seed_done:
                await initialize(db)
                _seed_done = True
    return await call_next(request)


handler = Mangum(app, lifespan="off")
