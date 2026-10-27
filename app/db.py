from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app.config import settings


def get_engine() -> Engine:
    return create_engine(
        settings.mysql_url,
        pool_pre_ping=True,
        pool_recycle=1800,
        connect_args={"connect_timeout": settings.mysql_connect_timeout},
    )


def check_database() -> dict[str, Any]:
    if not settings.database_configured:
        return {
            "status": "not_configured",
            "target": settings.mysql_target,
            "detail": "Set MYSQL_PASSWORD in the local .env file.",
        }

    try:
        engine = get_engine()
        with engine.connect() as connection:
            version = connection.execute(text("SELECT VERSION()")).scalar_one()
            database = connection.execute(text("SELECT DATABASE()")).scalar_one()
        return {
            "status": "ok",
            "target": settings.mysql_target,
            "version": version,
            "database": database,
        }
    except Exception as exc:
        detail = str(exc)
        if settings.mysql_password:
            detail = detail.replace(settings.mysql_password, "***")
        return {
            "status": "error",
            "target": settings.mysql_target,
            "error_type": type(exc).__name__,
            "detail": detail,
        }
