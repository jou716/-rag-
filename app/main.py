from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.ask import router as ask_router
from app.api.health import router as health_router
from app.config import settings
from app.index_guard import ensure_index_ready
from app.logging_config import configure_logging
from app.ui import mount_ui

configure_logging(settings.log_level)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    ensure_index_ready()
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Industrial exoskeleton selection and catalog RAG service.",
    lifespan=lifespan,
)
app.include_router(health_router)
app.include_router(ask_router)
app = mount_ui(app)
