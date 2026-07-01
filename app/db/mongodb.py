"""MongoDB connection, app-user provisioning and Beanie initialization.

On startup (when ``MONGODB_PROVISION`` is true) the app connects with the
admin credentials only to ensure the application database and its dedicated
user exist, then reconnects as that application user for all normal
operations. Beanie 2.x uses PyMongo's native async driver
(``AsyncMongoClient``).
"""

import logging

from beanie import init_beanie
from pymongo import AsyncMongoClient
from pymongo.errors import OperationFailure

from app.core.config import settings
from app.models import ALL_DOCUMENT_MODELS

logger = logging.getLogger(__name__)

# MongoDB error code raised by createUser when the user already exists.
_USER_ALREADY_EXISTS = 51003

_client: AsyncMongoClient | None = None


def get_client() -> AsyncMongoClient:
    if _client is None:
        raise RuntimeError("MongoDB client is not initialized")
    return _client


async def _provision_app_user() -> None:
    """Ensure the application user exists on the application database.

    Uses the admin credentials. Creates the user (with ``readWrite`` on the
    app database) if missing, or updates its password/roles if it already
    exists, so config.yaml stays authoritative. The database itself is created
    lazily by MongoDB on first write.
    """
    roles = [{"role": "readWrite", "db": settings.MONGODB_DB}]
    admin_client = AsyncMongoClient(settings.mongodb_admin_uri)
    try:
        db = admin_client[settings.MONGODB_DB]
        try:
            await db.command(
                "createUser",
                settings.MONGODB_APP_USER,
                pwd=settings.MONGODB_APP_PASSWORD,
                roles=roles,
            )
            logger.info(
                "Created MongoDB user '%s' on database '%s'",
                settings.MONGODB_APP_USER,
                settings.MONGODB_DB,
            )
        except OperationFailure as exc:
            if exc.code == _USER_ALREADY_EXISTS:
                await db.command(
                    "updateUser",
                    settings.MONGODB_APP_USER,
                    pwd=settings.MONGODB_APP_PASSWORD,
                    roles=roles,
                )
                logger.info(
                    "MongoDB user '%s' already existed; ensured password/roles",
                    settings.MONGODB_APP_USER,
                )
            else:
                raise
    finally:
        await admin_client.close()


async def connect_to_mongo() -> None:
    """Provision the app user (optional) and initialize Beanie as that user."""
    if settings.MONGODB_PROVISION:
        logger.info(
            "Provisioning MongoDB user/db on %s:%s",
            settings.MONGODB_HOST,
            settings.MONGODB_PORT,
        )
        await _provision_app_user()

    global _client
    logger.info(
        "Connecting to MongoDB db '%s' as user '%s'",
        settings.MONGODB_DB,
        settings.MONGODB_APP_USER,
    )
    _client = AsyncMongoClient(settings.mongodb_app_uri)
    await init_beanie(
        database=_client[settings.MONGODB_DB],
        document_models=ALL_DOCUMENT_MODELS,
    )
    logger.info("Beanie initialized on database '%s'", settings.MONGODB_DB)


async def close_mongo_connection() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None
        logger.info("MongoDB connection closed")
