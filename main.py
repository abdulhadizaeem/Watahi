import asyncio
import logging
import os
from contextlib import asynccontextmanager
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.utils.db import init_db, AsyncSessionLocal
from src.api.auth.router import router as auth_router
from src.api.retell.router import router as retell_router
from src.api.settings.router import router as settings_router
from src.api.menu.router import router as menu_router
from src.api.prompts.router import router as prompts_router

CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*")
origins = [o.strip() for o in CORS_ORIGINS.split(",")] if CORS_ORIGINS != "*" else ["*"]

_sched_logger = logging.getLogger("clover_menu_sync")
SYNC_INTERVAL_SECONDS = 300  # 5 minutes


async def _clover_menu_sync_loop():
    """Background task: sync Clover inventory to local DB every 5 minutes."""
    from src.services.clover_service import fetch_all_clover_items
    from src.utils.db_functions import full_sync_menu_from_clover

    await asyncio.sleep(10)

    while True:
        try:
            items = await fetch_all_clover_items()
            async with AsyncSessionLocal() as db:
                result = await full_sync_menu_from_clover(db, items)
            _sched_logger.info(
                "Clover menu sync complete: %d synced, %d skipped.",
                result["synced"], result["skipped"],
            )
        except Exception as exc:
            _sched_logger.error("Clover menu sync failed: %s", exc)
        await asyncio.sleep(SYNC_INTERVAL_SECONDS)



@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    sync_task = asyncio.create_task(_clover_menu_sync_loop())
    yield
    sync_task.cancel()
    try:
        await sync_task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="Restaurant Calling Agent API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(retell_router)
app.include_router(settings_router)
app.include_router(menu_router)
app.include_router(prompts_router)


class HealthResponse(BaseModel):
    status: str
    service: str


@app.get("/", response_model=HealthResponse)
async def health():
    return HealthResponse(status="ok", service="restaurant-calling-agent")
