"""
52-week high / close / drawdown attachment.

Primary: CREON StockChart when source_hint is CREON (and client connected).
Fallback: FinanceDataReader then pykrx OHLCV (~400 calendar days).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

import config
from creon_client import CreonClient, CreonNotAvailable
from metrics import drawdown_pct

logger = logging.getLogger(__name__)

# Calendar-day lookback for non-CREON OHLCV (~52w + buffer)
_FALLBACK_CALENDAR_DAYS = 400


def attach_drawdowns(rows: list[dict], source_hint: str) -> tuple[list[dict], str]:
    """
    Add close, high_52w, drawdown_pct to each row; drop rows missing data.

    Returns (enriched_rows, source) where source may update if fallback used.
    """
    if not rows:
        return [], source_hint or "CREON"

    errors: list[str] = []
    hint = (source_hint or "").strip().upper()

    if hint == "CREON" or (config.PREFER_CREON and hint in ("", "CREON")):
        try:
            out = _attach_from_creon(rows)
            if out:
                return out, "CREON"
            errors.append("CREON drawdowns empty")
        except CreonNotAvailable as e:
            errors.append(f"CREON unavailable: {e}")
            logger.warning("CREON prices unavailable: %s", e)
        except Exception as e:
            errors.append(f"CREON error: {e}")
            logger.warning("CREON attach_drawdowns failed: %s", e, exc_info=True)

    if config.ALLOW_PRICE_FALLBACK:
        try:
            out = _attach_from_fdr(rows)
            if out:
                return out, "FDR"
            errors.append("FDR drawdowns empty")
        except Exception as e:
            errors.append(f"FDR error: {e}")
            logger.warning("FDR attach_drawdowns failed: %s", e)

        try:
            out = _attach_from_pykrx(rows)
            if out:
                return out, "pykrx"
            errors.append("pykrx drawdowns empty")
        except Exception as e:
            errors.append(f"pykrx error: {e}")
            logger.warning("pykrx attach_drawdowns failed: %s", e)

    logger.error("attach_drawdowns produced no rows (%s)", "; ".join(errors) or "unknown")
    return [], source_hint or "CREON"


def _attach_from_creon(rows: list[dict]) -> list[dict]:
    client = CreonClient()
    if not client.is_connected():
        raise CreonNotAvailable("CREON not connected")

    out: list[dict] = []
    count = int(config.LOOKBACK_BARS)
    for row in rows:
        code = str(row.get("code") or "")
        if not code:
            continue
        bars = client.get_ohlcv_daily(code, count)
        enriched = _enrich_row(row, bars)
        if enriched is not None:
            out.append(enriched)
    return out


def _attach_from_fdr(rows: list[dict]) -> list[dict]:
    try:
        import FinanceDataReader as fdr  # type: ignore
    except ImportError as e:
        raise RuntimeError(
            "FinanceDataReader not installed (often blocked on 32-bit Python without pandas wheels)"
        ) from e

    end = datetime.now()
    start = end - timedelta(days=_FALLBACK_CALENDAR_DAYS)
    start_s = start.strftime("%Y-%m-%d")
    end_s = end.strftime("%Y-%m-%d")

    out: list[dict] = []
    for row in rows:
        code = str(row.get("code") or "")
        if not code:
            continue
        try:
            df = fdr.DataReader(code, start_s, end_s)
        except Exception as e:
            logger.debug("FDR DataReader(%s) failed: %s", code, e)
            continue
        bars = _df_to_bars(df, high_keys=("High", "high", "고가"), close_keys=("Close", "close", "종가"))
        enriched = _enrich_row(row, bars)
        if enriched is not None:
            out.append(enriched)
    return out


def _attach_from_pykrx(rows: list[dict]) -> list[dict]:
    try:
        from pykrx import stock  # type: ignore
    except ImportError as e:
        raise RuntimeError(
            "pykrx not installed (often blocked on 32-bit Python without pandas wheels)"
        ) from e

    end = datetime.now()
    start = end - timedelta(days=_FALLBACK_CALENDAR_DAYS)
    start_s = start.strftime("%Y%m%d")
    end_s = end.strftime("%Y%m%d")

    out: list[dict] = []
    for row in rows:
        code = str(row.get("code") or "")
        if not code:
            continue
        df = None
        for fn_name in ("get_market_ohlcv_by_date", "get_market_ohlcv"):
            fn = getattr(stock, fn_name, None)
            if fn is None:
                continue
            try:
                df = fn(start_s, end_s, code)
                if df is not None and len(df) > 0:
                    break
            except Exception as e:
                logger.debug("pykrx %s(%s) failed: %s", fn_name, code, e)
                df = None
        if df is None:
            continue
        bars = _df_to_bars(df, high_keys=("고가", "High", "high"), close_keys=("종가", "Close", "close"))
        enriched = _enrich_row(row, bars)
        if enriched is not None:
            out.append(enriched)
    return out


def _enrich_row(row: dict, bars: list[dict]) -> dict | None:
    stats = _bars_to_stats(bars)
    if stats is None:
        return None
    close, high_52w, dd = stats
    enriched = dict(row)
    enriched["close"] = close
    enriched["high_52w"] = high_52w
    enriched["drawdown_pct"] = dd
    return enriched


def _bars_to_stats(bars: list[dict]) -> tuple[float, float, float] | None:
    if not bars:
        return None
    highs: list[float] = []
    for b in bars:
        h = b.get("high")
        if h is None:
            continue
        try:
            hf = float(h)
        except (TypeError, ValueError):
            continue
        if hf == hf and hf > 0:  # not NaN
            highs.append(hf)
    if not highs:
        return None
    try:
        close = float(bars[-1]["close"])
    except (KeyError, TypeError, ValueError):
        return None
    if close != close or close <= 0:
        return None
    high_52w = max(highs)
    dd = drawdown_pct(close, high_52w)
    if dd is None:
        return None
    return close, high_52w, dd


def _df_to_bars(
    df: Any,
    high_keys: tuple[str, ...],
    close_keys: tuple[str, ...],
) -> list[dict]:
    if df is None or len(df) == 0:
        return []
    cols = list(getattr(df, "columns", []))
    lower = {str(c).lower(): c for c in cols}
    high_col = _match_col(cols, lower, high_keys)
    close_col = _match_col(cols, lower, close_keys)
    if not high_col or not close_col:
        return []

    # Ensure chronological order (oldest → newest)
    try:
        df = df.sort_index()
    except Exception:
        pass

    bars: list[dict] = []
    for _, rec in df.iterrows():
        try:
            h = float(rec[high_col])
            c = float(rec[close_col])
        except (TypeError, ValueError):
            continue
        if h != h or c != c:
            continue
        bars.append({"high": h, "close": c})
    return bars


def _match_col(cols: list[Any], lower: dict[str, Any], keys: tuple[str, ...]) -> Any | None:
    colset = {str(c): c for c in cols}
    for k in keys:
        if k in colset:
            return colset[k]
        if k.lower() in lower:
            return lower[k.lower()]
    return None
