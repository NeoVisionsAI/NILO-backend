"""Application configuration.

Configuration is split in two places:

- ``config.yaml``     -> non-sensitive settings (ports, names, defaults...).
- ``credentials.env`` -> secrets (connection URIs, access keys, passwords).

Both file locations can be overridden with the ``NILO_CONFIG_FILE`` and
``NILO_CREDENTIALS_FILE`` environment variables. Real environment variables
always take precedence, which is what makes container deployment easy: the
image ships ``config.yaml`` and the runtime injects secrets / overrides as
env vars (see docker-compose.yml).

Precedence (highest first): init args > env vars > credentials.env > config.yaml.
"""

import os
from functools import lru_cache
from urllib.parse import quote_plus

from pydantic import Field
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

CONFIG_FILE = os.getenv("NILO_CONFIG_FILE", "config.yaml")
CREDENTIALS_FILE = os.getenv("NILO_CREDENTIALS_FILE", "credentials.env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=CREDENTIALS_FILE,
        env_file_encoding="utf-8",
        yaml_file=CONFIG_FILE,
        yaml_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- General (config.yaml) ---
    PROJECT_NAME: str = "NILO"
    ENVIRONMENT: str = "development"
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = True

    # --- MongoDB (all in config.yaml) ---
    MONGODB_HOST: str = "localhost"
    MONGODB_PORT: int = 27017
    MONGODB_DB: str = "nilo"
    # Admin credentials, used ONLY at startup to provision the app user/db.
    MONGODB_ADMIN_USER: str = "admin"
    MONGODB_ADMIN_PASSWORD: str = "upaelo"
    MONGODB_ADMIN_AUTH_SOURCE: str = "admin"
    # Application user (auto-created/updated at startup) used for all normal
    # operations. It authenticates against the application database itself.
    MONGODB_APP_USER: str = "nilo"
    MONGODB_APP_PASSWORD: str = "nilo"
    # When true, connect as admin at startup to ensure the app user + db exist.
    # Set to false if you connect directly with an already-provisioned user.
    MONGODB_PROVISION: bool = True

    # --- MinIO / S3 object storage ---
    MINIO_ENDPOINT: str = "localhost:9000"  # config.yaml
    MINIO_ACCESS_KEY: str = "minioadmin"  # credentials.env
    MINIO_SECRET_KEY: str = "minioadmin"  # credentials.env
    MINIO_SECURE: bool = False  # config.yaml
    MINIO_BUCKET: str = "nilo-data"  # config.yaml
    # How long presigned URLs stay valid, in seconds.
    MINIO_PRESIGN_EXPIRY: int = 3600  # config.yaml
    # Enable server-side encryption (SSE-S3) as bucket default. Requires a KMS
    # configured on the MinIO server (see docker-compose.yml).
    MINIO_SSE: bool = True  # config.yaml

    # --- Security / JWT ---
    JWT_SECRET_KEY: str = "CHANGE_ME_IN_PRODUCTION"  # credentials.env
    JWT_ALGORITHM: str = "HS256"  # config.yaml
    # Short-lived access token; refreshed via the long-lived refresh token.
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60  # config.yaml
    REFRESH_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 30  # config.yaml (30 days)

    # --- Field-level encryption (patient data at rest) ---
    # base64-encoded master key (>= 32 bytes). Generate with:
    #   python -c "import base64,os; print(base64.b64encode(os.urandom(32)).decode())"
    ENCRYPTION_MASTER_KEY: str = ""  # credentials.env

    # --- Bootstrap root user (created on startup if it does not exist) ---
    ROOT_EMAIL: str = "root@niloapp.com"  # credentials.env
    ROOT_PASSWORD: str = "changeme"  # credentials.env
    ROOT_FULL_NAME: str = "NILO Root"  # config.yaml

    # --- Seed demo users (created on startup when SEED_USERS is true) ---
    # Handy so you can log in right after `docker compose up`. Disable in prod.
    SEED_USERS: bool = False  # config.yaml
    SEED_CLINICIAN_EMAIL: str = "clinician@niloapp.com"  # credentials.env
    SEED_CLINICIAN_PASSWORD: str = "changeme"  # credentials.env
    SEED_PATIENT_EMAIL: str = "patient@niloapp.com"  # credentials.env
    SEED_PATIENT_PASSWORD: str = "changeme"  # credentials.env

    # --- Local media storage (config.yaml) ---
    # Small files kept on the backend filesystem (e.g. user avatars), NOT in
    # MinIO. Served as static files under MEDIA_URL_PREFIX.
    MEDIA_ROOT: str = "media"
    MEDIA_URL_PREFIX: str = "/media"
    # Max accepted size for an uploaded user photo, in bytes.
    MAX_PHOTO_BYTES: int = 5 * 1024 * 1024

    # --- Video / recording defaults (config.yaml) ---
    # Default duration (seconds) of an archival video chunk. Hybrid strategy:
    # short HLS segments for live view + consolidated archive chunks.
    DEFAULT_VIDEO_CHUNK_SECONDS: int = 300
    # Duration (seconds) of the short live HLS segments.
    DEFAULT_HLS_SEGMENT_SECONDS: int = 6

    # --- CORS (config.yaml) ---
    CORS_ORIGINS: list[str] = Field(default_factory=lambda: ["*"])

    @property
    def mongodb_admin_uri(self) -> str:
        """Connection URI using admin credentials (for provisioning only)."""
        user = quote_plus(self.MONGODB_ADMIN_USER)
        pw = quote_plus(self.MONGODB_ADMIN_PASSWORD)
        return (
            f"mongodb://{user}:{pw}@{self.MONGODB_HOST}:{self.MONGODB_PORT}"
            f"/?authSource={self.MONGODB_ADMIN_AUTH_SOURCE}"
        )

    @property
    def mongodb_app_uri(self) -> str:
        """Connection URI using the application user against its database."""
        user = quote_plus(self.MONGODB_APP_USER)
        pw = quote_plus(self.MONGODB_APP_PASSWORD)
        return (
            f"mongodb://{user}:{pw}@{self.MONGODB_HOST}:{self.MONGODB_PORT}"
            f"/{self.MONGODB_DB}?authSource={self.MONGODB_DB}"
        )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            YamlConfigSettingsSource(settings_cls),
            file_secret_settings,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
