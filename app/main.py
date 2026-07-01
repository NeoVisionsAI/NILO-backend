"""FastAPI application entrypoint for the NILO backend."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import api_router
from app.core import crypto
from app.core.config import settings
from app.core.security import hash_password
from app.db.mongodb import close_mongo_connection, connect_to_mongo
from app.db.seed import seed_demo_users
from app.models.enums import UserRole
from app.models.user import User
from app.storage.minio_client import ensure_bucket

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("nilo")


async def _bootstrap_root_user() -> None:
    """Create the root admin user on first startup if it does not exist."""
    existing = await User.find_one(
        User.email_bidx == crypto.blind_index(settings.ROOT_EMAIL)
    )
    if existing is None:
        parts = settings.ROOT_FULL_NAME.split(" ", 1)
        name = parts[0]
        lastname = parts[1] if len(parts) > 1 else "Root"
        root = User(
            name=name,
            lastname=lastname,
            type_user=UserRole.ROOT,
            email=settings.ROOT_EMAIL,
            email_bidx=crypto.blind_index(settings.ROOT_EMAIL),
            hashed_password=hash_password(settings.ROOT_PASSWORD),
        )
        await root.insert()
        logger.info("Bootstrapped root user '%s'", settings.ROOT_EMAIL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_to_mongo()
    try:
        ensure_bucket()
    except Exception as exc:  # noqa: BLE001 - storage may be down at boot
        logger.warning("Could not ensure MinIO bucket at startup: %s", exc)
    await _bootstrap_root_user()
    await seed_demo_users()
    yield
    await close_mongo_connection()


app = FastAPI(
    title=f"{settings.PROJECT_NAME} API",
    version="0.1.0",
    description="Integral patient monitoring platform backend.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_V1_PREFIX)

# Serve locally-stored media (e.g. user photos) from the backend filesystem.
_media_root = Path(settings.MEDIA_ROOT)
_media_root.mkdir(parents=True, exist_ok=True)
app.mount(
    settings.MEDIA_URL_PREFIX,
    StaticFiles(directory=str(_media_root)),
    name="media",
)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.PROJECT_NAME}
