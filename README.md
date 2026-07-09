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

## Schedule

Windows 작업 스케줄러로 **매일 15:50** (장 마감 직후) `run.bat`을 실행하도록 등록합니다.

## Tests

```bat
python -m pytest tests/ -v
```
