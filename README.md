# Earnings-Dip Telegram Bot

장 마감 후 1회, 코스피·코스닥에서 **영업이익 YoY ≥ 10%** 이면서 **52주 고점 대비 ≤ −20%** 인 종목을 스크리닝해 텔레그램으로 일일 요약을 보냅니다.

시세·유니버스는 CREON Plus COM 우선, 실패 시 FinanceDataReader/pykrx 폴백. 분기 영업이익 YoY는 DART OpenAPI.

## Requirements

- Windows
- Python **3.11 32-bit** (CREON COM)
- CREON Plus 로그인
- DART API 키, Telegram bot token / chat id

32-bit Python 경로 예:

```text
C:\Users\lkh07\AppData\Local\Programs\Python\Python311-32\python.exe
```

## Setup

```bat
cd /d C:\Users\lkh07\Desktop\Claude\cans
"C:\Users\lkh07\AppData\Local\Programs\Python\Python311-32\python.exe" -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
copy .env.example .env
```

`.env`에 `DART_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` 등을 채웁니다.

## Run

1. CREON Plus에 로그인합니다.
2. 배치 실행:

```bat
run.bat
```

(또는 `python main.py`)

## Schedule (Windows Task Scheduler)

장 마감 후 1일 1회 실행을 권장합니다 (평일 **15:50~16:30**).

1. CREON Plus에 로그인된 세션이 있는 Windows 계정으로 작업 등록
2. **기본 작업 만들기** → 트리거: 매주 월–금, 시작 시각 예) `15:50`
3. 동작: 프로그램 시작
   - 프로그램/스크립트:  
     `C:\Users\lkh07\Desktop\Claude\cans\run.bat`  
     (또는 이 워크트리 경로의 `run.bat`)
   - 인수: `nopause`  (스케줄러에서 pause 대기 방지)
   - 시작 위치: `run.bat`이 있는 프로젝트 폴더
4. 조건/설정: 로그인 상태에서도 실행, 배터리·유휴 제한 해제 권장
5. 재실행 방지: `.env`의 `SKIP_IF_ALREADY_RAN_TODAY=true` (기본)이면 당일 성공 run 후 스킵

수동 실행:

```bat
run.bat
run.bat nopause
```

로그: `logs/earnings_dip.log`  
상태: `state/last_run.json`, `state/last_candidates.json`

### Exit codes

| Code | 의미 |
|------|------|
| 0 | 성공 또는 당일 이미 실행으로 스킵 |
| 1 | 실패 (DART 키 없음, 시세 전 경로 실패, 텔레그램 미설정/전송 실패, 미처리 예외 등) |

에러 시 가능하면 텔레그램 `[ERROR] earnings-dip: ...` 알림을 보냅니다.

## Tests

```bat
"C:\Users\lkh07\AppData\Local\Programs\Python\Python311-32\python.exe" -m pytest tests -v
```
