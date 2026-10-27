from typing import Any

from fastapi import APIRouter, Response, status

from app.config import settings
from app.db import check_database

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "app": settings.app_name,
        "environment": settings.app_env,
        "source_doc": {
            "path": str(settings.source_doc_path),
            "exists": settings.source_doc_path.exists(),
        },
        "database": {
            "configured": settings.database_configured,
            "target": settings.mysql_target,
        },
    }


@router.get("/health/db")
def health_db(response: Response) -> dict[str, Any]:
    result = check_database()
    if result["status"] != "ok":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return result
