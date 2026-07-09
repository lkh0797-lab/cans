"""
CREON Plus COM wrapper.

- Pure helpers: to_creon_code / from_creon_code (no COM dependency).
- CreonClient: optional win32com; callers handle fallback when unavailable/disconnected.
"""
from __future__ import annotations

import logging
import re
import time
from typing import Any

logger = logging.getLogger(__name__)

# Name filters for preferred shares / SPACs (fallback when section kind is insufficient)
_PREFERRED_OR_SPAC_RE = re.compile(
    r"(우$|우B$|우C$|우D$|우[0-9A-Z]?$|우선|스팩|SPAC)",
    re.IGNORECASE,
)

# CpCodeMgr.GetStockSectionKind: 1=주권, 10=ETF, others excluded
_SECTION_COMMON = 1
_SECTION_ETF = 10

# GetLimitRemainCount limit type: 1 = 시세 요청
_LIMIT_TYPE_QUOTE = 1


class CreonNotAvailable(Exception):
    """Raised when win32com / CREON COM objects cannot be used."""


def to_creon_code(code: str) -> str:
    """Internal 6-digit (or already A-prefixed) → CREON `A######`."""
    code = (code or "").strip()
    if not code:
        return code
    if code.upper().startswith("A"):
        return "A" + code[1:]
    return "A" + code


def from_creon_code(code: str) -> str:
    """CREON `A######` or bare code → internal 6-digit (strip leading A)."""
    code = (code or "").strip()
    if not code:
        return code
    if code.upper().startswith("A"):
        return code[1:]
    return code


class CreonClient:
    """
    Thin CREON Plus client. COM is imported only in __init__ / methods so that
    unit tests of code conversion never require CREON or pywin32.
    """

    def __init__(self) -> None:
        self._win32: Any = None
        self._cybos: Any = None
        self._code_mgr: Any = None
        try:
            import win32com.client  # type: ignore

            self._win32 = win32com.client
            self._cybos = win32com.client.Dispatch("CpUtil.CpCybos")
            self._code_mgr = win32com.client.Dispatch("CpUtil.CpCodeMgr")
        except Exception as e:
            logger.warning("CREON COM init failed: %s", e)
            self._win32 = None
            self._cybos = None
            self._code_mgr = None

    def _require_com(self) -> None:
        if self._win32 is None or self._cybos is None:
            raise CreonNotAvailable("CREON COM (win32com) not available")

    def is_connected(self) -> bool:
        """True if CpUtil.CpCybos.IsConnect == 1."""
        if self._cybos is None:
            return False
        try:
            # CREON API: IsConnect (samples); brief typo IfConnect avoided
            return int(self._cybos.IsConnect) == 1
        except Exception as e:
            logger.warning("is_connected failed: %s", e)
            return False

    def wait_request_slot(self, sleep_sec: float = 0.25, max_wait_sec: float = 60.0) -> None:
        """
        Block until GetLimitRemainCount(1) > 0 (시세 제한 잔여).
        Short sleep when remain==0. No-op / raise if COM missing.
        """
        self._require_com()
        assert self._cybos is not None
        deadline = time.monotonic() + max_wait_sec
        while True:
            try:
                remain = int(self._cybos.GetLimitRemainCount(_LIMIT_TYPE_QUOTE))
            except Exception as e:
                logger.warning("GetLimitRemainCount failed: %s", e)
                time.sleep(sleep_sec)
                if time.monotonic() >= deadline:
                    return
                continue
            if remain > 0:
                return
            if time.monotonic() >= deadline:
                logger.warning("wait_request_slot timed out after %.1fs", max_wait_sec)
                return
            time.sleep(sleep_sec)

    def list_stock_codes(self) -> list[tuple[str, str, str]]:
        """
        List common stocks: (code6, name, market) with market in {KOSPI, KOSDAQ}.
        Skips ETF/ETN via GetStockSectionKind and preferred/SPAC name heuristics.
        """
        self._require_com()
        if not self.is_connected():
            raise CreonNotAvailable("CREON not connected")
        assert self._code_mgr is not None

        out: list[tuple[str, str, str]] = []
        # GetStockListByMarket: 1=KOSPI, 2=KOSDAQ
        markets = ((1, "KOSPI"), (2, "KOSDAQ"))
        for market_id, market_name in markets:
            try:
                codes = self._code_mgr.GetStockListByMarket(market_id)
            except Exception as e:
                logger.warning("GetStockListByMarket(%s) failed: %s", market_id, e)
                continue
            if codes is None:
                continue
            # COM may return a tuple/list or a collection with Count
            try:
                iterable = list(codes)
            except TypeError:
                try:
                    iterable = [codes.Item(i) for i in range(int(codes.Count))]  # type: ignore[attr-defined]
                except Exception as e:
                    logger.warning("cannot iterate market %s codes: %s", market_id, e)
                    continue

            for raw in iterable:
                try:
                    creon = str(raw)
                    code6 = from_creon_code(creon)
                    name = str(self._code_mgr.CodeToName(creon) or "")
                    if not code6 or not name:
                        continue
                    if _PREFERRED_OR_SPAC_RE.search(name):
                        continue
                    try:
                        section = int(self._code_mgr.GetStockSectionKind(creon))
                    except Exception:
                        section = _SECTION_COMMON
                    # Keep only 주권; drop ETF(10) and other section kinds
                    if section != _SECTION_COMMON:
                        continue
                    # Name heuristic for ETN/ETF leftover
                    upper = name.upper()
                    if "ETF" in upper or "ETN" in upper:
                        continue
                    out.append((code6, name, market_name))
                except Exception as e:
                    logger.debug("skip code %s: %s", raw, e)
                    continue
        return out

    def get_market_cap_and_value(self, code6: str) -> tuple[float | None, float | None]:
        """
        (시가총액 원, 당일 거래대금 원). Failure → (None, None) for caller fallback.

        DsCbo1.StockMst header fields (CREON sample / help — calibrate live if wrong):
          - 11: 현재가/종가 (원)
          - 18: 거래량
          - 19: 거래대금 (원)  — sample: vol_value = GetHeaderValue(19)
          - 31: 상장주식수     — 시가총액 ≈ 현재가 * 상장주식수
        If field 31 is wrong on live CREON, return None for cap and log; Task 7 may fix.
        """
        if not code6:
            return None, None
        try:
            self._require_com()
            if not self.is_connected():
                return None, None
            assert self._win32 is not None
            self.wait_request_slot()
            # ProgID casing per Daishin sample
            obj = self._win32.Dispatch("DsCbo1.StockMst")
            obj.SetInputValue(0, to_creon_code(code6))
            obj.BlockRequest()
            status = int(obj.GetDibStatus())
            if status != 0:
                logger.warning(
                    "StockMst status=%s msg=%s code=%s",
                    status,
                    obj.GetDibMsg1(),
                    code6,
                )
                return None, None

            # Field numbers — see docstring; wrong index → None + log, allow fallback
            close = _as_float(obj.GetHeaderValue(11))
            trading_value = _as_float(obj.GetHeaderValue(19))
            listed = _as_float(obj.GetHeaderValue(31))

            market_cap: float | None = None
            if close is not None and listed is not None and close > 0 and listed > 0:
                market_cap = close * listed
            else:
                logger.warning(
                    "market_cap fields missing code=%s close=%s listed=%s",
                    code6,
                    close,
                    listed,
                )

            if trading_value is None:
                logger.warning("trading_value missing code=%s field=19", code6)

            return market_cap, trading_value
        except CreonNotAvailable:
            return None, None
        except Exception as e:
            logger.warning("get_market_cap_and_value(%s) failed: %s", code6, e)
            return None, None

    def get_ohlcv_daily(self, code6: str, count: int) -> list[dict]:
        """
        Daily OHLCV bars via CpSysDib.StockChart, oldest → newest.

        Each item: {date, open, high, low, close, volume}
        date as int YYYYMMDD or str of same.

        StockChart SetInputValue (common sample):
          0: code, 1: '2' (by count), 4: count,
          5: (0,2,3,4,5,8) 날짜/시/고/저/종/거래량,
          6: 'D' 일봉, 9: '1' 수정주가
        GetDataValue order is newest-first; we reverse for oldest→newest.
        On failure return [] so callers can fallback.
        """
        if not code6 or count <= 0:
            return []
        try:
            self._require_com()
            if not self.is_connected():
                return []
            assert self._win32 is not None
            self.wait_request_slot()
            chart = self._win32.Dispatch("CpSysDib.StockChart")
            chart.SetInputValue(0, to_creon_code(code6))
            chart.SetInputValue(1, ord("2"))  # 개수 요청
            chart.SetInputValue(4, int(count))
            # field ids: 0=date, 2=open, 3=high, 4=low, 5=close, 8=volume
            chart.SetInputValue(5, (0, 2, 3, 4, 5, 8))
            chart.SetInputValue(6, ord("D"))
            chart.SetInputValue(9, ord("1"))  # 수정주가
            chart.BlockRequest()
            status = int(chart.GetDibStatus())
            if status != 0:
                logger.warning(
                    "StockChart status=%s msg=%s code=%s",
                    status,
                    chart.GetDibMsg1(),
                    code6,
                )
                return []

            # Header 3 = received bar count (common convention)
            n = int(chart.GetHeaderValue(3))
            rows: list[dict] = []
            for i in range(n):
                try:
                    rows.append(
                        {
                            "date": chart.GetDataValue(0, i),
                            "open": float(chart.GetDataValue(1, i)),
                            "high": float(chart.GetDataValue(2, i)),
                            "low": float(chart.GetDataValue(3, i)),
                            "close": float(chart.GetDataValue(4, i)),
                            "volume": float(chart.GetDataValue(5, i)),
                        }
                    )
                except Exception as e:
                    logger.warning("StockChart row %s code=%s: %s", i, code6, e)
                    continue
            # API returns newest first → oldest→newest
            rows.reverse()
            return rows
        except CreonNotAvailable:
            return []
        except Exception as e:
            logger.warning("get_ohlcv_daily(%s) failed: %s", code6, e)
            return []


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
