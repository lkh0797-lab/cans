from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

DART_API_KEY = os.getenv("DART_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

OP_YOY_MIN = float(os.getenv("OP_YOY_MIN", "10"))
DRAWDOWN_MAX = float(os.getenv("DRAWDOWN_MAX", "-20"))  # pass if drawdown <= this
MIN_MARKET_CAP = int(float(os.getenv("MIN_MARKET_CAP_UK", "1000")) * 100_000_000)  # 억 → 원
MIN_TRADING_VALUE = int(float(os.getenv("MIN_VALUE_UK", "100")) * 100_000_000)

PREFER_CREON = os.getenv("PREFER_CREON", "true").lower() in ("1", "true", "yes")
ALLOW_PRICE_FALLBACK = os.getenv("ALLOW_PRICE_FALLBACK", "true").lower() in ("1", "true", "yes")
SKIP_IF_ALREADY_RAN_TODAY = os.getenv("SKIP_IF_ALREADY_RAN_TODAY", "true").lower() in (
    "1",
    "true",
    "yes",
)

LOOKBACK_BARS = int(os.getenv("LOOKBACK_BARS", "260"))  # ~52w trading days + buffer
DART_SLEEP_SEC = float(os.getenv("DART_SLEEP_SEC", "0.15"))

STATE_DIR = BASE_DIR / "state"
LOG_DIR = BASE_DIR / "logs"
CACHE_DIR = BASE_DIR / "cache"
LAST_CANDIDATES_FILE = STATE_DIR / "last_candidates.json"
LAST_RUN_FILE = STATE_DIR / "last_run.json"
LOG_FILE = LOG_DIR / "earnings_dip.log"
EARNINGS_CACHE_FILE = CACHE_DIR / "earnings_cache.json"
CORPCODE_CACHE = CACHE_DIR / "CORPCODE.xml"

for d in (STATE_DIR, LOG_DIR, CACHE_DIR):
    d.mkdir(parents=True, exist_ok=True)
