from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from core.index_contract import validate_index_contract_or_raise

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def ensure_index_ready() -> dict[str, Any]:
    """Validate persisted indexes once per process and fail fast on drift."""
    try:
        report = validate_index_contract_or_raise().as_dict()
    except RuntimeError as exc:
        logger.error("索引校验失败：\n%s", exc)
        raise
    logger.info("索引校验通过：%d 项检查", len(report["checks"]))
    return report
