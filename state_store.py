from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

import config

logger = logging.getLogger(__name__)


def load_yesterday_codes() -> set[str]:
    path = config.LAST_CANDIDATES_FILE
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return set(data.get("codes") or [])
    except Exception as e:
        logger.warning("last_candidates load failed: %s", e)
        return set()


def save_candidates(date: str, candidates: list[dict[str, Any]]) -> None:
    payload = {
        "date": date,
        "codes": [c["code"] for c in candidates],
        "candidates": candidates,
        "ts": datetime.now().isoformat(),
    }
    config.LAST_CANDIDATES_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def already_ran_today() -> bool:
    path = config.LAST_RUN_FILE
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("date") == datetime.now().strftime("%Y-%m-%d") and data.get("ok") is True
    except Exception:
        return False


def save_last_run(summary: dict[str, Any]) -> None:
    payload = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "ts": datetime.now().isoformat(),
        **summary,
    }
    config.LAST_RUN_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
