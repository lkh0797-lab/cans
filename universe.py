"""
Stock universe: liquidity + name filters.

Primary: CREON Plus (when PREFER_CREON and connected).
Fallback: FinanceDataReader then pykrx (when ALLOW_PRICE_FALLBACK).
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any

import config
from creon_client import CreonClient, CreonNotAvailable

logger = logging.getLogger(__name__)

# Preferred shares, SPACs, ETF/ETN name heuristics (shared intent with creon_client listing)
_EXCLUDED_NAME_RE = re.compile(
    r"(우$|우B$|우C$|우D$|우[0-9A-Z]?$|우선|스팩|SPAC|ETF|ETN)",
    re.IGNORECASE,
)


def is_excluded_name(name: str) -> bool:
    """True if name looks like preferred, SPAC, ETF, or ETN."""
    if name is None:
        return True
    s = str(name).strip()
    if not s:
        return True
    return bool(_EXCLUDED_NAME_RE.search(s))


def passes_liquidity(market_cap: float, trading_value: float) -> bool:
    """시총 ≥ MIN_MARKET_CAP and 거래대금 ≥ MIN_TRADING_VALUE (원)."""
    try:
        cap = float(market_cap)
        val = float(trading_value)
    except (TypeError, ValueError):
        return False
    return cap >= config.MIN_MARKET_CAP and val >= config.MIN_TRADING_VALUE


def build_universe() -> tuple[list[dict], str, str]:
    """
    Build filtered universe.

    Returns:
        (rows, as_of YYYYMMDD, source) where source is "CREON" | "FDR" | "pykrx"
        each row: {code, name, market_cap, trading_value}
    """
    errors: list[str] = []

    if config.PREFER_CREON:
        try:
            rows, as_of = _build_from_creon()
            if rows:
                logger.info("universe CREON: %s names as_of=%s", len(rows), as_of)
                return rows, as_of, "CREON"
            errors.append("CREON returned empty universe")
        except CreonNotAvailable as e:
            errors.append(f"CREON unavailable: {e}")
            logger.warning("CREON universe unavailable: %s", e)
        except Exception as e:
            errors.append(f"CREON error: {e}")
            logger.warning("CREON universe failed: %s", e, exc_info=True)

    if config.ALLOW_PRICE_FALLBACK:
        try:
            rows, as_of = _build_from_fdr()
            if rows:
                logger.info("universe FDR: %s names as_of=%s", len(rows), as_of)
                return rows, as_of, "FDR"
            errors.append("FDR returned empty universe")
        except Exception as e:
            errors.append(f"FDR error: {e}")
            logger.warning("FDR universe failed: %s", e)

        try:
            rows, as_of = _build_from_pykrx()
            if rows:
                logger.info("universe pykrx: %s names as_of=%s", len(rows), as_of)
                return rows, as_of, "pykrx"
            errors.append("pykrx returned empty universe")
        except Exception as e:
            errors.append(f"pykrx error: {e}")
            logger.warning("pykrx universe failed: %s", e)

    detail = "; ".join(errors) if errors else "no source configured"
    raise RuntimeError(f"시세 유니버스 구축 실패 ({detail})")


def _build_from_creon() -> tuple[list[dict], str]:
    client = CreonClient()
    if not client.is_connected():
        raise CreonNotAvailable("CREON not connected")

    stocks = client.list_stock_codes()
    rows: list[dict] = []
    for code6, name, _market in stocks:
        if is_excluded_name(name):
            continue
        cap, val = client.get_market_cap_and_value(code6)
        if cap is None or val is None:
            continue
        if not passes_liquidity(cap, val):
            continue
        rows.append(
            {
                "code": str(code6).zfill(6),
                "name": name,
                "market_cap": float(cap),
                "trading_value": float(val),
            }
        )
    as_of = datetime.now().strftime("%Y%m%d")
    return rows, as_of


def _build_from_fdr() -> tuple[list[dict], str]:
    try:
        import FinanceDataReader as fdr  # type: ignore
    except ImportError as e:
        raise RuntimeError(
            "FinanceDataReader not installed (often blocked on 32-bit Python without pandas wheels)"
        ) from e

    frames: list[Any] = []
    for market in ("KOSPI", "KOSDAQ"):
        try:
            df = fdr.StockListing(market)
            if df is not None and len(df) > 0:
                frames.append(df)
        except Exception as e:
            logger.warning("FDR StockListing(%s) failed: %s", market, e)

    if not frames:
        # Some FDR versions use KRX marcap snapshot
        try:
            df = fdr.StockListing("KRX")
            if df is not None and len(df) > 0:
                frames.append(df)
        except Exception as e:
            logger.warning("FDR StockListing(KRX) failed: %s", e)

    if not frames:
        return [], datetime.now().strftime("%Y%m%d")

    rows: list[dict] = []
    seen: set[str] = set()
    as_of = datetime.now().strftime("%Y%m%d")

    for df in frames:
        code_col = _pick_col(df, "Code", "Symbol", "code", "티커", "종목코드")
        name_col = _pick_col(df, "Name", "name", "종목명")
        cap_col = _pick_col(df, "Marcap", "MarCap", "MarketCap", "시가총액", "marcap")
        val_col = _pick_col(df, "Amount", "Value", "TradingValue", "거래대금", "amount")
        if not code_col or not name_col:
            logger.warning("FDR listing missing code/name columns: %s", list(df.columns))
            continue
        for _, rec in df.iterrows():
            code = _normalize_code(rec.get(code_col))
            name = str(rec.get(name_col) or "").strip()
            if not code or code in seen or is_excluded_name(name):
                continue
            cap = _as_float(rec.get(cap_col)) if cap_col else None
            val = _as_float(rec.get(val_col)) if val_col else None
            if cap is None or val is None:
                continue
            if not passes_liquidity(cap, val):
                continue
            seen.add(code)
            rows.append(
                {
                    "code": code,
                    "name": name,
                    "market_cap": cap,
                    "trading_value": val,
                }
            )
    return rows, as_of


def _build_from_pykrx() -> tuple[list[dict], str]:
    try:
        from pykrx import stock  # type: ignore
    except ImportError as e:
        raise RuntimeError(
            "pykrx not installed (often blocked on 32-bit Python without pandas wheels)"
        ) from e

    as_of = _pykrx_nearest_business_day(stock)
    rows: list[dict] = []
    seen: set[str] = set()

    for market in ("KOSPI", "KOSDAQ"):
        cap_df = None
        # Prefer get_market_cap_by_ticker; fall back to get_market_cap
        for fn_name in ("get_market_cap_by_ticker", "get_market_cap"):
            fn = getattr(stock, fn_name, None)
            if fn is None:
                continue
            try:
                cap_df = fn(as_of, market=market)
                if cap_df is not None and len(cap_df) > 0:
                    break
            except TypeError:
                try:
                    cap_df = fn(as_of)
                    if cap_df is not None and len(cap_df) > 0:
                        break
                except Exception as e:
                    logger.warning("pykrx %s(%s) failed: %s", fn_name, as_of, e)
            except Exception as e:
                logger.warning("pykrx %s(%s, %s) failed: %s", fn_name, as_of, market, e)

        if cap_df is None or len(cap_df) == 0:
            continue

        cap_col = _pick_col(cap_df, "시가총액", "Marcap", "market_cap")
        val_col = _pick_col(cap_df, "거래대금", "Amount", "trading_value")
        if not cap_col or not val_col:
            logger.warning("pykrx cap df missing columns: %s", list(cap_df.columns))
            continue

        # Index is typically ticker
        for ticker, rec in cap_df.iterrows():
            code = _normalize_code(ticker)
            if not code or code in seen:
                continue
            try:
                name = str(stock.get_market_ticker_name(code) or "").strip()
            except Exception:
                name = code
            if is_excluded_name(name):
                continue
            cap = _as_float(rec.get(cap_col))
            val = _as_float(rec.get(val_col))
            if cap is None or val is None:
                continue
            if not passes_liquidity(cap, val):
                continue
            seen.add(code)
            rows.append(
                {
                    "code": code,
                    "name": name,
                    "market_cap": cap,
                    "trading_value": val,
                }
            )
    return rows, as_of


def _pykrx_nearest_business_day(stock: Any) -> str:
    """Walk back up to ~10 calendar days for a date with data."""
    from datetime import timedelta

    day = datetime.now()
    for _ in range(10):
        s = day.strftime("%Y%m%d")
        try:
            # Lightweight probe: ticker list
            tickers = stock.get_market_ticker_list(s, market="KOSPI")
            if tickers:
                return s
        except Exception:
            pass
        day -= timedelta(days=1)
    return datetime.now().strftime("%Y%m%d")


def _pick_col(df: Any, *candidates: str) -> str | None:
    cols = list(getattr(df, "columns", []))
    colset = {str(c): c for c in cols}
    lower = {str(c).lower(): c for c in cols}
    for cand in candidates:
        if cand in colset:
            return str(colset[cand])
        if cand.lower() in lower:
            return str(lower[cand.lower()])
    return None


def _normalize_code(raw: Any) -> str:
    if raw is None:
        return ""
    s = str(raw).strip()
    if not s or s.lower() == "nan":
        return ""
    # Strip CREON A prefix if present
    if s.upper().startswith("A") and len(s) == 7:
        s = s[1:]
    # Numeric codes as float from pandas
    if re.fullmatch(r"\d+(\.0+)?", s):
        s = str(int(float(s)))
    if s.isdigit():
        return s.zfill(6)
    return s


def _as_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
        if f != f:  # NaN
            return None
        return f
    except (TypeError, ValueError):
        return None
