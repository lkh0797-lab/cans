"""
DART operating-profit YoY attachment with disk cache.

Same report type YoY (11013/11012/11014/11011); no cumulative conversion.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import config
from dart_api import DartClient
from metrics import op_yoy_pct

logger = logging.getLogger(__name__)

# Report codes: Q1, H1, Q3, annual
REPRT_Q1 = "11013"
REPRT_H1 = "11012"
REPRT_Q3 = "11014"
REPRT_ANNUAL = "11011"

# Within a calendar year, newer filings first (annual is prior year)
_REPRT_RECENCY_IN_YEAR = (REPRT_Q3, REPRT_H1, REPRT_Q1)

OP_ACCOUNT_NAMES = (
    "영업이익",
    "영업이익(손실)",
    "영업이익 (손실)",
    "영업손익",
)

# Common DART / IFRS account_id fragments for operating profit
_OP_ACCOUNT_ID_HINTS = (
    "operatingprofit",
    "operating_profit",
    "ifrs-full_operatingprofitloss",
    "ifrs_operatingprofitloss",
    "dart_operatingincome",
)

_IS_SJ = frozenset({"IS", "CIS", "is", "cis"})
CACHE_TTL = timedelta(days=7)

_cache: dict[str, Any] = {}
_cache_loaded = False


def _cache_path() -> Path:
    return Path(config.EARNINGS_CACHE_FILE)


def _load_cache() -> None:
    global _cache, _cache_loaded
    if _cache_loaded:
        return
    path = _cache_path()
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                _cache = json.load(f)
        except Exception as e:
            logger.warning("earnings cache load failed: %s", e)
            _cache = {}
    else:
        _cache = {}
    _cache_loaded = True


def _save_cache() -> None:
    path = _cache_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(_cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning("earnings cache save failed: %s", e)


def _cache_key(corp_code: str, year: int | str, reprt_code: str) -> str:
    return f"{corp_code}|{year}|{reprt_code}"


def _get_cached_op(corp_code: str, year: int | str, reprt_code: str) -> Optional[float]:
    """Return cached OP amount if present and fresh; None if miss / expired."""
    _load_cache()
    key = _cache_key(corp_code, year, reprt_code)
    entry = _cache.get(key)
    if not isinstance(entry, dict):
        return None
    ts = entry.get("cached_at")
    if not ts:
        return None
    try:
        cached_at = datetime.fromisoformat(ts)
    except (TypeError, ValueError):
        return None
    if datetime.now() - cached_at > CACHE_TTL:
        return None
    if "op" not in entry:
        return None
    op = entry["op"]
    if op is None:
        # Explicit miss cached (no OP found) — still respect TTL
        return None
    try:
        return float(op)
    except (TypeError, ValueError):
        return None


def _has_fresh_cache_entry(corp_code: str, year: int | str, reprt_code: str) -> bool:
    """True if key exists with valid TTL (including op=None sentinel)."""
    _load_cache()
    key = _cache_key(corp_code, year, reprt_code)
    entry = _cache.get(key)
    if not isinstance(entry, dict):
        return False
    ts = entry.get("cached_at")
    if not ts:
        return False
    try:
        cached_at = datetime.fromisoformat(ts)
    except (TypeError, ValueError):
        return False
    return datetime.now() - cached_at <= CACHE_TTL


def _set_cached_op(corp_code: str, year: int | str, reprt_code: str, op: float | None) -> None:
    _load_cache()
    key = _cache_key(corp_code, year, reprt_code)
    _cache[key] = {
        "op": op,
        "cached_at": datetime.now().isoformat(timespec="seconds"),
    }


def _parse_amount(raw: Any) -> Optional[float]:
    if raw is None:
        return None
    s = str(raw).replace(",", "").strip()
    if not s or s in ("-", "—", "–"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _is_op_account(item: dict) -> bool:
    nm = (item.get("account_nm") or "").strip()
    if nm in OP_ACCOUNT_NAMES:
        return True
    # Heuristic: exact-ish name containing 영업이익 without subcomponents
    if nm.startswith("영업이익") and "판관" not in nm and "세부" not in nm:
        return True
    aid = (item.get("account_id") or "").strip().lower()
    if aid:
        for hint in _OP_ACCOUNT_ID_HINTS:
            if hint in aid.replace(" ", ""):
                return True
    return False


def _sj_ok(item: dict) -> bool:
    sj = (item.get("sj_div") or item.get("sj_nm") or "").strip()
    if not sj:
        # Some endpoints omit sj_div; allow and rank later
        return True
    if sj in _IS_SJ:
        return True
    # Korean statement names
    if "손익" in sj:
        return True
    return False


def _fs_rank(item: dict) -> int:
    """Lower is better: prefer consolidated (CFS)."""
    fs = (item.get("fs_div") or item.get("fs_nm") or "").strip().upper()
    if fs in ("CFS", "연결"):
        return 0
    if fs in ("OFS", "별도"):
        return 1
    return 2


def pick_operating_profit(items: list[dict]) -> Optional[float]:
    """
    Extract 영업이익 (thstrm_amount) from DART account rows.
    Prefers IS/CIS, consolidated if multiple matches.
    """
    if not items:
        return None

    candidates: list[tuple[int, float]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if not _is_op_account(item):
            continue
        if not _sj_ok(item):
            continue
        amount = _parse_amount(item.get("thstrm_amount"))
        if amount is None:
            continue
        candidates.append((_fs_rank(item), amount))

    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0])
    return candidates[0][1]


def compute_yoy_from_ops(current_op: float, year_ago_op: float) -> Optional[float]:
    """Wrapper around metrics.op_yoy_pct (None if prior OP <= 0)."""
    return op_yoy_pct(current_op, year_ago_op)


def _report_candidates(now: datetime | None = None) -> list[tuple[int, str]]:
    """
    (bsns_year, reprt_code) pairs from most recent toward older.
    Annual for year Y is filed ~March Y+1, so listed after current-year quarterlies.
    """
    now = now or datetime.now()
    y = now.year
    out: list[tuple[int, str]] = []
    for year in (y, y - 1, y - 2):
        if year == y:
            for rc in _REPRT_RECENCY_IN_YEAR:
                out.append((year, rc))
        else:
            # Prior years: annual then quarters
            out.append((year, REPRT_ANNUAL))
            for rc in _REPRT_RECENCY_IN_YEAR:
                out.append((year, rc))
    return out


def _fetch_op(
    client: DartClient,
    corp_code: str,
    year: int,
    reprt_code: str,
    *,
    use_cache: bool = True,
) -> Optional[float]:
    """OP for one report; cache hit or network + pick."""
    if use_cache and _has_fresh_cache_entry(corp_code, year, reprt_code):
        return _get_cached_op(corp_code, year, reprt_code)

    items = client.fetch_accounts(corp_code, year, reprt_code)
    op = pick_operating_profit(items) if items else None
    if use_cache:
        _set_cached_op(corp_code, year, reprt_code, op)
    return op


def resolve_op_yoy_for_corp(
    client: DartClient,
    corp_code: str,
    *,
    now: datetime | None = None,
) -> Optional[float]:
    """
    Find latest report with OP; compare same reprt_code year-1; return YoY %.

    Once the newest report that has OP is found, do not fall back to older types.
    Missing prior same-type report or prior OP <= 0 → None for this stock.
    """
    for year, reprt_code in _report_candidates(now):
        cur = _fetch_op(client, corp_code, year, reprt_code)
        if cur is None:
            continue
        prev = _fetch_op(client, corp_code, year - 1, reprt_code)
        if prev is None:
            return None
        return compute_yoy_from_ops(cur, prev)
    return None


def attach_op_yoy(
    rows: list[dict],
    client: DartClient | None = None,
) -> list[dict]:
    """
    Add op_yoy_pct when computable. Does not drop rows; leaves key missing/absent on failure.
    Does not apply OP_YOY_MIN threshold (screener does that).
    """
    if not rows:
        return []

    dart = client or DartClient()
    out: list[dict] = []
    _load_cache()

    for row in rows:
        r = dict(row)
        code = str(r.get("code") or "").strip()
        try:
            corp = dart.map_stock_to_corp(code)
            if not corp:
                logger.debug("no corp_code for %s", code)
                out.append(r)
                continue
            yoy = resolve_op_yoy_for_corp(dart, corp)
            if yoy is not None:
                r["op_yoy_pct"] = float(yoy)
        except Exception as e:
            logger.warning("attach_op_yoy failed for %s: %s", code, e)
        out.append(r)

    _save_cache()
    return out
