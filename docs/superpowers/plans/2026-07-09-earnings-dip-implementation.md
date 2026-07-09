# Earnings-Dip Telegram Bot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 장 마감 후 1회, 코스피·코스닥에서 영업이익 YoY ≥10% 이면서 52주 고점 대비 ≤−20% 인 종목을 스크리닝해 텔레그램으로 일일 요약(+신규 진입 강조)을 보낸다.

**Architecture:** Windows 배치 `run.bat` → `main.py` 오케스트레이션. 시세·유니버스는 CREON Plus COM 우선, 실패 시 FinanceDataReader/pykrx 폴백. 분기 영업이익 YoY는 DART OpenAPI. 상태는 JSON(`state/`). DB 없음.

**Tech Stack:** Python 3.11 **32-bit** (CREON), `pywin32`, `requests`, `python-dotenv`, `FinanceDataReader`, `pykrx`(폴백), `pytest`. 경로: `C:\Users\lkh07\Desktop\Claude\cans\` (remote: `https://github.com/lkh0797-lab/cans.git`).

**Spec:** `docs/superpowers/specs/2026-07-09-earnings-dip-telegram-design.md`

## Global Constraints

- 내부 종목코드: 6자리 문자열 (`005930`). CREON 호출 시에만 `A` 접두.
- 시총 ≥ 1,000억, 당일 거래대금 ≥ 100억; ETF/ETN/스팩/우선주 제외.
- OP YoY ≥ 10; 전년 동기 OP ≤ 0 이면 제외.
- drawdown_pct = (close/high_52w − 1)×100; 통과 조건 ≤ −20.
- YoY: 동일 보고서 유형 전년 동기 비교 (누적 환산 없음).
- `PREFER_CREON=true`, `ALLOW_PRICE_FALLBACK=true`.
- Mock으로 운영 결과 대체 금지. 테스트 픽스처 mock만 허용.
- 커밋 시 identity 미설정이면: `git -c user.name="lkh0797-lab" -c user.email="lkh0797-lab@users.noreply.github.com"`.
- 32-bit Python 경로(이 머신): `C:\Users\lkh07\AppData\Local\Programs\Python\Python311-32\python.exe`

---

## File Structure

| Path | Responsibility |
|------|----------------|
| `config.py` | env + 임계값 + 경로 |
| `metrics.py` | drawdown, yoy, set diff (순수 함수) |
| `state_store.py` | last_candidates / last_run JSON |
| `telegram_sender.py` | Telegram HTTP |
| `creon_client.py` | 접속, 코드 변환, rate limit, StockChart/종목목록 래퍼 |
| `universe.py` | 유니버스 빌드 (CREON → 폴백) |
| `prices.py` | 52주 고점·종가·drawdown (CREON → 폴백) |
| `earnings.py` | DART OP YoY + 캐시 |
| `screener.py` | 필터·정렬·신규/유지/이탈 |
| `formatter.py` | 텔레그램 메시지 문자열 |
| `main.py` | 오케스트레이션, 로깅, exit code |
| `run.bat` | 32-bit venv 실행 |
| `requirements.txt`, `.env.example`, `README.md` | 의존성·설정·운영 |
| `tests/test_metrics.py` | 순수 계산 |
| `tests/test_screener.py` | 스크리닝·diff |
| `tests/test_formatter.py` | 메시지 |
| `tests/test_creon_codes.py` | A접두 변환 |
| `state/`, `logs/`, `cache/` | 런타임 산출물 (gitkeep) |

---

### Task 1: Scaffold + pure metrics (TDD)

**Files:**
- Create: `config.py`, `metrics.py`, `requirements.txt`, `.env.example`, `tests/test_metrics.py`, `state/.gitkeep`, `logs/.gitkeep`, `cache/.gitkeep`
- Create: `README.md` (최소 실행 안내)

**Interfaces:**
- Produces:
  - `metrics.drawdown_pct(close: float, high_52w: float) -> float | None`
  - `metrics.op_yoy_pct(current_op: float, year_ago_op: float) -> float | None`  # year_ago_op <= 0 → None
  - `metrics.diff_sets(today: set[str], yesterday: set[str]) -> tuple[set[str], set[str], set[str]]`  # new, kept, exited
  - `config` module attributes listed in Step 3

- [ ] **Step 1: Write failing tests**

Create `tests/test_metrics.py`:

```python
from metrics import drawdown_pct, op_yoy_pct, diff_sets


def test_drawdown_pct_basic():
    assert abs(drawdown_pct(80.0, 100.0) - (-20.0)) < 1e-9


def test_drawdown_pct_invalid():
    assert drawdown_pct(100.0, 0.0) is None
    assert drawdown_pct(100.0, -1.0) is None


def test_op_yoy_pct_basic():
    assert abs(op_yoy_pct(110.0, 100.0) - 10.0) < 1e-9


def test_op_yoy_pct_nonpositive_base():
    assert op_yoy_pct(50.0, 0.0) is None
    assert op_yoy_pct(50.0, -10.0) is None


def test_diff_sets():
    new, kept, exited = diff_sets({"A", "B", "C"}, {"B", "C", "D"})
    assert new == {"A"}
    assert kept == {"B", "C"}
    assert exited == {"D"}
```

- [ ] **Step 2: Run tests — expect FAIL**

```bat
cd /d C:\Users\lkh07\Desktop\Claude\cans
"C:\Users\lkh07\AppData\Local\Programs\Python\Python311-32\python.exe" -m pip install pytest -q
"C:\Users\lkh07\AppData\Local\Programs\Python\Python311-32\python.exe" -m pytest tests/test_metrics.py -v
```

Expected: import/collection error or FAIL (metrics missing).

- [ ] **Step 3: Implement `metrics.py` and `config.py`**

`metrics.py`:

```python
from __future__ import annotations


def drawdown_pct(close: float, high_52w: float) -> float | None:
    if high_52w is None or close is None:
        return None
    if high_52w <= 0:
        return None
    return (float(close) / float(high_52w) - 1.0) * 100.0


def op_yoy_pct(current_op: float, year_ago_op: float) -> float | None:
    if current_op is None or year_ago_op is None:
        return None
    if float(year_ago_op) <= 0:
        return None
    return (float(current_op) / float(year_ago_op) - 1.0) * 100.0


def diff_sets(today: set[str], yesterday: set[str]) -> tuple[set[str], set[str], set[str]]:
    today = set(today)
    yesterday = set(yesterday)
    return today - yesterday, today & yesterday, yesterday - today
```

`config.py`:

```python
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
```

`requirements.txt`:

```
requests>=2.28
python-dotenv>=1.0
pywin32>=306
FinanceDataReader>=0.9.50
pykrx>=1.0.45
pytest>=7.0
```

`.env.example`:

```
DART_API_KEY=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
OP_YOY_MIN=10
DRAWDOWN_MAX=-20
MIN_MARKET_CAP_UK=1000
MIN_VALUE_UK=100
PREFER_CREON=true
ALLOW_PRICE_FALLBACK=true
SKIP_IF_ALREADY_RAN_TODAY=true
```

`README.md` (short): project purpose, 32-bit venv setup, CREON login, `.env`, `run.bat`, schedule 15:50.

- [ ] **Step 4: Run tests — expect PASS**

```bat
"C:\Users\lkh07\AppData\Local\Programs\Python\Python311-32\python.exe" -m pip install -r requirements.txt -q
"C:\Users\lkh07\AppData\Local\Programs\Python\Python311-32\python.exe" -m pytest tests/test_metrics.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bat
git add config.py metrics.py requirements.txt .env.example README.md tests/test_metrics.py state/.gitkeep logs/.gitkeep cache/.gitkeep
git -c user.name="lkh0797-lab" -c user.email="lkh0797-lab@users.noreply.github.com" commit -m "feat: scaffold config and pure screening metrics"
```

---

### Task 2: state_store + telegram_sender + formatter

**Files:**
- Create: `state_store.py`, `telegram_sender.py`, `formatter.py`
- Create: `tests/test_formatter.py`, `tests/test_state_store.py`

**Interfaces:**
- Consumes: `config`, `metrics.diff_sets`
- Produces:
  - `state_store.load_yesterday_codes() -> set[str]`
  - `state_store.save_candidates(date: str, candidates: list[dict]) -> None`
  - `state_store.already_ran_today() -> bool`
  - `state_store.save_last_run(summary: dict) -> None`
  - `TelegramSender.send_message(text) -> bool`, `send_long_message`, `send_error`
  - `formatter.format_report(...) -> str`

Candidate dict shape (canonical for rest of plan):

```python
{
  "code": "005930",
  "name": "삼성전자",
  "drawdown_pct": -23.1,
  "op_yoy_pct": 18.0,
  "market_cap": 400_000_000_000_000,
  "close": 70000.0,
  "high_52w": 91000.0,
}
```

- [ ] **Step 1: Write failing tests**

`tests/test_formatter.py`:

```python
from formatter import format_report


def test_format_report_highlights_new():
    cands = [
        {
            "code": "005930",
            "name": "삼성전자",
            "drawdown_pct": -23.1,
            "op_yoy_pct": 18.0,
            "market_cap": 400_000_000_000_000,
        }
    ]
    text = format_report(
        date="2026-07-09",
        universe_n=248,
        candidates=cands,
        new_codes={"005930"},
        kept_codes=set(),
        exited_codes={"000660"},
        source="CREON",
    )
    assert "신규" in text
    assert "005930" in text
    assert "CREON" in text
    assert "000660" in text
```

`tests/test_state_store.py`:

```python
import json
from pathlib import Path

import config
import state_store


def test_save_and_load_candidates(tmp_path, monkeypatch):
    p = tmp_path / "last_candidates.json"
    monkeypatch.setattr(config, "LAST_CANDIDATES_FILE", p)
    state_store.save_candidates(
        "2026-07-09",
        [{"code": "005930", "name": "삼성전자", "drawdown_pct": -22.0, "op_yoy_pct": 15.0, "market_cap": 1}],
    )
    codes = state_store.load_yesterday_codes()
    assert codes == {"005930"}
```

- [ ] **Step 2: Run — expect FAIL**

```bat
"C:\Users\lkh07\AppData\Local\Programs\Python\Python311-32\python.exe" -m pytest tests/test_formatter.py tests/test_state_store.py -v
```

- [ ] **Step 3: Implement modules**

`state_store.py`:

```python
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
```

`telegram_sender.py` — Dart-alert-bot과 동일 패턴 (HTML, retry, `send_long_message`, `send_error`). `config.TELEGRAM_*` 사용. 토큰 없으면 `__init__`에서 `ValueError`.

`formatter.py`:

```python
from __future__ import annotations

from typing import Any


def _cap_str(market_cap: float | int | None) -> str:
    if not market_cap:
        return "-"
    uk = float(market_cap) / 1e8  # 억
    if uk >= 10000:
        return f"{uk/10000:.1f}조"
    return f"{uk:.0f}억"


def _line(c: dict[str, Any]) -> str:
    return (
        f"• {c['code']} {c.get('name', '')}  "
        f"고점대비 {c['drawdown_pct']:+.1f}%  "
        f"OP YoY {c['op_yoy_pct']:+.1f}%  "
        f"시총 {_cap_str(c.get('market_cap'))}"
    )


def format_report(
    *,
    date: str,
    universe_n: int,
    candidates: list[dict[str, Any]],
    new_codes: set[str],
    kept_codes: set[str],
    exited_codes: set[str],
    source: str,
) -> str:
    by_code = {c["code"]: c for c in candidates}
    lines = [
        f"📉 어닝+낙폭 스크리닝  {date}",
        f"유니버스 {universe_n} · 후보 {len(candidates)} · 신규 {len(new_codes)}  |  source={source}",
        "",
        "⭐ 신규 진입",
    ]
    new_list = [by_code[c] for c in sorted(new_codes) if c in by_code]
    if new_list:
        lines.extend(_line(c) for c in new_list)
    else:
        lines.append("• (없음)")

    lines += ["", f"📋 유지 ({len(kept_codes)})"]
    kept_list = [by_code[c] for c in sorted(kept_codes) if c in by_code]
    if kept_list:
        lines.extend(_line(c) for c in kept_list)
    else:
        lines.append("• (없음)")

    lines += ["", f"↩ 이탈 ({len(exited_codes)}): " + (", ".join(sorted(exited_codes)) if exited_codes else "없음")]
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests — PASS**

```bat
"C:\Users\lkh07\AppData\Local\Programs\Python\Python311-32\python.exe" -m pytest tests/test_formatter.py tests/test_state_store.py -v
```

- [ ] **Step 5: Commit**

```bat
git add state_store.py telegram_sender.py formatter.py tests/test_formatter.py tests/test_state_store.py
git -c user.name="lkh0797-lab" -c user.email="lkh0797-lab@users.noreply.github.com" commit -m "feat: state store, telegram sender, report formatter"
```

---

### Task 3: creon_client (code helpers + optional COM)

**Files:**
- Create: `creon_client.py`
- Create: `tests/test_creon_codes.py`

**Interfaces:**
- Produces:
  - `to_creon_code(code: str) -> str`
  - `from_creon_code(code: str) -> str`
  - `CreonClient.is_connected() -> bool`
  - `CreonClient.list_stock_codes() -> list[tuple[str, str, str]]`  # (code6, name, market) market in {"KOSPI","KOSDAQ"}
  - `CreonClient.get_market_cap_and_value(code6: str) -> tuple[float|None, float|None]`  # cap, trading_value won
  - `CreonClient.get_ohlcv_daily(code6: str, count: int) -> list[dict]`  # [{date, open, high, low, close, volume}, ...] oldest→newest
  - `CreonClient.wait_request_slot() -> None`

- [ ] **Step 1: Failing tests for pure code conversion**

```python
from creon_client import to_creon_code, from_creon_code


def test_to_creon_code():
    assert to_creon_code("005930") == "A005930"
    assert to_creon_code("A005930") == "A005930"


def test_from_creon_code():
    assert from_creon_code("A005930") == "005930"
    assert from_creon_code("005930") == "005930"
```

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Implement `creon_client.py`**

Include:
- `to_creon_code` / `from_creon_code` pure functions.
- `CreonClient` class:
  - Import `win32com.client` only inside methods / `__init__` try.
  - `is_connected`: `CpUtil.CpCybos`.IfConnect() == 1
  - `wait_request_slot`: loop `GetLimitRemainCount(1)` (시세 제한 타입; 환경에 맞게 조정), remain==0이면 short sleep.
  - `list_stock_codes`: `CpCodeMgr.GetStockListByMarket(1)` KOSPI, `(2)` KOSDAQ; skip ETFs via `GetStockSectionKind` / name heuristics if available; skip names matching preferred/spac regex.
  - `get_market_cap_and_value`: `dscbo1.StockMst` SetInputValue code, BlockRequest; header fields for 시가총액·거래대금 (구현 시 CREON 헤더 번호 실측 — 주석으로 필드 번호 기록). 실패 시 `(None, None)`.
  - `get_ohlcv_daily`: `CpSysDib.StockChart` 일봉, count bars, fields 날짜/시/고/저/종/거래량.

If COM not available, methods raise `CreonNotAvailable` or return not connected — callers handle fallback.

Reference pattern used in Korean CREON samples; if a header index is wrong, fix during manual Task 7 verification and update comment.

- [ ] **Step 4: Run unit tests PASS (COM not required for code tests)**

```bat
"C:\Users\lkh07\AppData\Local\Programs\Python\Python311-32\python.exe" -m pytest tests/test_creon_codes.py -v
```

- [ ] **Step 5: Commit**

```bat
git add creon_client.py tests/test_creon_codes.py
git -c user.name="lkh0797-lab" -c user.email="lkh0797-lab@users.noreply.github.com" commit -m "feat: CREON client wrapper and code conversion"
```

---

### Task 4: universe + prices (CREON then fallback)

**Files:**
- Create: `universe.py`, `prices.py`
- Create: `tests/test_universe_filter.py`

**Interfaces:**
- Produces:
  - `universe.build_universe() -> tuple[list[dict], str, str]`
    - each item: `{code, name, market_cap, trading_value}`
    - as_of date `YYYYMMDD`, source `"CREON"|"FDR"|"pykrx"`
  - `prices.attach_drawdowns(rows: list[dict], source_hint: str) -> tuple[list[dict], str]`
    - adds `close`, `high_52w`, `drawdown_pct`; drops rows missing data
    - returns possibly updated source string

- [ ] **Step 1: Test exclusion + market-cap filter pure helpers**

Put filter helpers in `universe.py`:

```python
def is_excluded_name(name: str) -> bool: ...
def passes_liquidity(market_cap: float, trading_value: float) -> bool: ...
```

Test:

```python
from universe import is_excluded_name, passes_liquidity
import config


def test_exclude_preferred_and_spac():
    assert is_excluded_name("삼성전자우") is True
    assert is_excluded_name("하이제6호스팩") is True
    assert is_excluded_name("삼성전자") is False


def test_liquidity_boundary():
    assert passes_liquidity(config.MIN_MARKET_CAP, config.MIN_TRADING_VALUE) is True
    assert passes_liquidity(config.MIN_MARKET_CAP - 1, config.MIN_TRADING_VALUE) is False
    assert passes_liquidity(config.MIN_MARKET_CAP, config.MIN_TRADING_VALUE - 1) is False
```

- [ ] **Step 2: FAIL then implement helpers + full build**

`universe.build_universe` logic:
1. If `config.PREFER_CREON`: try `CreonClient`; if connected, list stocks, for each get cap/value (rate-limited), filter; if non-empty return source=CREON.
2. Else/fail and `ALLOW_PRICE_FALLBACK`: use FDR `StockListing("KOSPI")`/`KOSDAQ` + price snapshot if available; or pykrx `get_market_cap_by_ticker` like Dart-alert `canslim/universe.py` (시가총액·거래대금 컬럼). Prefer FDR first then pykrx if one fails.
3. Both fail → raise `RuntimeError("시세 유니버스 구축 실패")`.

`prices.attach_drawdowns`:
1. If source CREON and client connected: StockChart per code (only for universe rows — still many; optional prefilter later). Compute high_52w=max(high), close=last close, drawdown via `metrics.drawdown_pct`. Keep if drawdown is not None.
2. Fallback: FDR or pykrx OHLCV for ~400 calendar days; same math.
3. For v1 performance: after universe liquidity filter, only compute drawdown for those names (hundreds not thousands).

- [ ] **Step 3: unit tests PASS**

- [ ] **Step 4: Commit**

```bat
git add universe.py prices.py tests/test_universe_filter.py
git -c user.name="lkh0797-lab" -c user.email="lkh0797-lab@users.noreply.github.com" commit -m "feat: universe and 52w drawdown via CREON with fallback"
```

---

### Task 5: earnings (DART OP YoY)

**Files:**
- Create: `earnings.py`, `dart_api.py` (thin OpenAPI wrapper)
- Create: `tests/test_earnings_yoy.py`

**Interfaces:**
- Produces:
  - `dart_api.DartClient` with `download_corp_codes()`, `map_stock_to_corp(code6)->corp_code|None`, `fetch_accounts(corp_code, bsns_year, reprt_code)->list[dict]`
  - `earnings.attach_op_yoy(rows: list[dict]) -> list[dict]`  # adds op_yoy_pct; drops if None or < threshold applied in screener not here — attach only raw yoy, screener filters
  - Actually: `attach_op_yoy` adds `op_yoy_pct` when computable; leaves missing if fail

Reprort codes:
- `11013` 1분기, `11012` 반기, `11014` 3분기, `11011` 사업

Algorithm per stock:
1. Map code → corp_code (skip if none).
2. Determine latest available report: try current year then previous for each reprt_code in order of recency (use presence of OP account).
3. Parse 영업이익 from items: account_nm in `("영업이익", "영업이익(손실)", ...)` or account_id heuristics; sj_div in IS/CIS; prefer consolidated if multiple.
4. Fetch same reprt_code for year-1; parse OP.
5. `op_yoy_pct = metrics.op_yoy_pct(cur, prev)`; cache key `corp|year|reprt`.

Cache: `config.EARNINGS_CACHE_FILE` JSON, TTL 7 days per key.

- [ ] **Step 1: Unit test parse + yoy without network**

```python
from earnings import pick_operating_profit, compute_yoy_from_ops


def test_pick_operating_profit():
    items = [
        {"account_nm": "매출액", "thstrm_amount": "100", "sj_div": "IS"},
        {"account_nm": "영업이익", "thstrm_amount": "1,000", "sj_div": "IS"},
    ]
    assert pick_operating_profit(items) == 1000.0


def test_compute_yoy():
    assert abs(compute_yoy_from_ops(110, 100) - 10.0) < 1e-9
    assert compute_yoy_from_ops(110, 0) is None
```

- [ ] **Step 2–4: implement, pass tests, commit**

```bat
git add dart_api.py earnings.py tests/test_earnings_yoy.py
git -c user.name="lkh0797-lab" -c user.email="lkh0797-lab@users.noreply.github.com" commit -m "feat: DART operating profit YoY with cache"
```

---

### Task 6: screener

**Files:**
- Create: `screener.py`
- Create: `tests/test_screener.py`

**Interfaces:**
- Produces: `screener.run_screen(rows: list[dict]) -> list[dict]`  
  Filter: `drawdown_pct <= config.DRAWDOWN_MAX` and `op_yoy_pct >= config.OP_YOY_MIN`  
  Sort: drawdown ascending (more negative first), then op_yoy descending.

- [ ] **Step 1: Test**

```python
import config
from screener import run_screen


def test_run_screen_filters_and_sorts(monkeypatch):
    monkeypatch.setattr(config, "DRAWDOWN_MAX", -20.0)
    monkeypatch.setattr(config, "OP_YOY_MIN", 10.0)
    rows = [
        {"code": "A", "drawdown_pct": -10.0, "op_yoy_pct": 20.0},  # fail dd
        {"code": "B", "drawdown_pct": -25.0, "op_yoy_pct": 5.0},   # fail yoy
        {"code": "C", "drawdown_pct": -30.0, "op_yoy_pct": 12.0},
        {"code": "D", "drawdown_pct": -22.0, "op_yoy_pct": 40.0},
    ]
    out = run_screen(rows)
    assert [r["code"] for r in out] == ["C", "D"]
```

- [ ] **Step 2–4: implement, pass, commit**

```python
def run_screen(rows):
    passed = []
    for r in rows:
        dd = r.get("drawdown_pct")
        yoy = r.get("op_yoy_pct")
        if dd is None or yoy is None:
            continue
        if dd <= config.DRAWDOWN_MAX and yoy >= config.OP_YOY_MIN:
            passed.append(r)
    passed.sort(key=lambda x: (x["drawdown_pct"], -x["op_yoy_pct"]))
    return passed
```

```bat
git add screener.py tests/test_screener.py
git -c user.name="lkh0797-lab" -c user.email="lkh0797-lab@users.noreply.github.com" commit -m "feat: candidate screener filter and sort"
```

---

### Task 7: main.py + run.bat end-to-end wiring

**Files:**
- Create: `main.py`, `run.bat`
- Modify: `README.md` (scheduler section)

**Interfaces:**
- `main.run() -> int` exit code
- Flow:
  1. setup logging (stdout + RotatingFileHandler `config.LOG_FILE`)
  2. if skip_if_already_ran and already_ran_today → log, return 0
  3. if not DART_API_KEY → try telegram error, return 1
  4. build_universe → attach_drawdowns → optional prefilter dd<=-20 to cut DART calls → attach_op_yoy → run_screen
  5. diff_sets vs load_yesterday_codes
  6. format_report; TelegramSender.send_long_message
  7. save_candidates; save_last_run(ok=True, counts, source)
  8. exceptions → send_error, save_last_run(ok=False), return 1

`run.bat`:

```bat
@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Create 32-bit venv first:
  echo   "C:\Users\lkh07\AppData\Local\Programs\Python\Python311-32\python.exe" -m venv .venv
  echo   .venv\Scripts\python.exe -m pip install -r requirements.txt
  pause
  exit /b 1
)
".venv\Scripts\python.exe" main.py
echo Exit %ERRORLEVEL%
if "%1"=="nopause" exit /b %ERRORLEVEL%
pause
exit /b %ERRORLEVEL%
```

- [ ] **Step 1: Implement main.py fully**

- [ ] **Step 2: Run unit suite**

```bat
"C:\Users\lkh07\AppData\Local\Programs\Python\Python311-32\python.exe" -m pytest tests -v
```

Expected: all pass.

- [ ] **Step 3: Manual dry checks (document results in commit message or README)**

1. Without `.env` keys: exit ≠0, clear error.
2. With keys, CREON off, fallback on: completes or fails with explicit source error.
3. With CREON logged in: `source=CREON` in telegram/log.

Do not commit secrets. `.env` is gitignored.

Add `.gitignore`:

```
.env
.venv/
__pycache__/
*.pyc
logs/*.log
state/*.json
cache/*
!cache/.gitkeep
!state/.gitkeep
!logs/.gitkeep
```

- [ ] **Step 4: Commit**

```bat
git add main.py run.bat README.md .gitignore
git -c user.name="lkh0797-lab" -c user.email="lkh0797-lab@users.noreply.github.com" commit -m "feat: main orchestration and run.bat for daily earnings-dip screen"
```

- [ ] **Step 5: Push**

```bat
git push origin main
```

---

## Spec Coverage Checklist

| Spec item | Task |
|-----------|------|
| YoY ≥10, drawdown ≤−20 | 1, 6 |
| Universe filters | 4 |
| CREON first + fallback | 3, 4 |
| DART same-report-type YoY | 5 |
| Daily telegram + new highlight | 2, 7 |
| state JSON tracking | 2, 7 |
| skip if already ran | 2, 7 |
| 32-bit run.bat | 7 |
| unit tests metrics/diff/filter | 1, 2, 4, 5, 6 |
| error exit codes | 7 |

## Placeholder / consistency review

- Candidate dict keys unified: `code`, `name`, `drawdown_pct`, `op_yoy_pct`, `market_cap`, `close`, `high_52w`.
- CREON header field numbers may need live calibration in Task 3/4 — code must log raw failures; fix indexes when running against live CREON (not left as TBD in behavior: return None and fallback).
- Project root is `cans` repo (not `earnings-dip-bot`).

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-09-earnings-dip-implementation.md`.

**Two execution options:**

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks  
2. **Inline Execution** — this session, task-by-task with checkpoints  

Which approach?
