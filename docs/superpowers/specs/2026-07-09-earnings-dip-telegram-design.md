# 어닝 서프라이즈 + 낙폭과대 텔레그램 알림 봇 — 설계 스펙

**날짜:** 2026-07-09  
**프로젝트 경로:** `C:\Users\lkh07\Desktop\Claude\earnings-dip-bot\`  
**상태:** Draft → 구현 전 사용자 검토

## 1. 목적

코스피·코스닥 종목 중 **영업이익 YoY가 양호한데도 52주 고점 대비 낙폭이 큰 종목**을 장 마감 후 1회 스크리닝하고, 텔레그램으로 일일 요약 + **신규 진입 강조** 알림을 보낸다.

1차에서는 증권사 컨센서스 대비 서프라이즈 대신 **영업이익 YoY ≥ +10%** 를 대리 지표로 사용한다.

## 2. 비목표 (1차 스코프 밖)

- 컨센서스(FnGuide 등) 대비 어닝 서프라이즈
- 장중 실시간 알림, 주문·매매 연동
- 웹 대시보드, SQLite 히스토리 DB
- 흑자 전환·적자 기업에 대한 특수 YoY 처리
- 대화형 텔레그램 봇 명령어 (`/start` 등)

## 3. 스크리닝 규칙

### 3.1 유니버스

| 규칙 | 값 |
|------|-----|
| 시장 | KOSPI + KOSDAQ |
| 시가총액 | ≥ 1,000억 원 |
| 당일 거래대금 | ≥ 100억 원 |
| 제외 | ETF, ETN, 스팩, 우선주, (가능 시) 관리종목 |

### 3.2 낙폭과대

```
drawdown_pct = (close / high_52w - 1) * 100
pass if drawdown_pct <= -20
```

- `high_52w`: 최근 약 252 거래일 일봉 고가의 최댓값
- `close`: 스크리닝 기준일(당일 또는 직전 영업일) 종가

### 3.3 어닝 (YoY 대리 지표)

```
op_yoy_pct = (op_this_quarter / op_year_ago_quarter - 1) * 100
pass if op_yoy_pct >= 10
```

| 항목 | 규칙 |
|------|------|
| 지표 | 영업이익 (손익계산서) |
| 기간 | 종목별 가장 최근 공시 분기 vs 전년 동기 |
| 분모 | 전년 동기 영업이익 ≤ 0 이면 **제외** (1차) |
| 분자 | 이번 분기 영업이익 데이터 없으면 제외 |

### 3.4 최종 후보

```
candidates = universe ∩ (drawdown_pct <= -20) ∩ (op_yoy_pct >= 10)
```

기본 정렬: 낙폭 큰 순(drawdown 오름차순) → 동률 시 YoY 높은 순.

### 3.5 트래킹 상태

- 저장: `state/last_candidates.json` (날짜 + 종목코드 집합 및 요약 필드)
- **신규 진입:** 오늘 후보 − 어제 후보 → 메시지 상단 강조
- **유지:** 교집합
- **이탈:** 어제 − 오늘 → 요약에 짧게 표기
- 후보 0개여도 정상 요약 1통 전송 (하트비트)

## 4. 아키텍처

```
[Windows 작업 스케줄러, 평일 15:50~16:30]
        │
        ▼
  run.bat → main.py
        │
        ├─ creon_client   접속 체크, 코드 변환, rate limit
        ├─ universe       시총·대금·시장 필터 종목 리스트
        ├─ prices         52주 고점, 종가, drawdown%
        ├─ earnings       DART 분기 영업이익 → OP YoY
        ├─ screener       조건 결합, 정렬, 신규/유지/이탈
        ├─ state_store    last_candidates / last_run JSON
        └─ telegram       요약·에러 전송
```

데이터 소스 역할:

| 데이터 | 1순위 | 폴백 |
|--------|--------|------|
| 종목·시총·대금·일봉·52주 고가 | **CREON Plus (COM)** | FinanceDataReader, 필요 시 pykrx |
| 분기 영업이익 | **DART OpenAPI** | 없음 (해당 종목 스킵) |
| 알림 | Telegram Bot API | 없음 |

정책: `prefer_creon=true`, `allow_price_fallback=true`  
→ CREON 미접속·연속 실패 시 시세 경로만 폴백. 폴백 사용 시 메시지에 `source=FDR` 등 표기.

## 5. CREON Plus 연동

### 5.1 환경 제약

- **32-bit Python** 필수 (CREON COM은 64-bit 불가)
- 스크리닝 전 **CREON Plus 로그인** 권장
- 연결 확인 후 진행; 실패 시 폴백 또는 에러(설정에 따름)
- API 호출은 잔여 한도(`GetLimitRemainCount` 등)를 존중. 고정 sleep 남발 금지
- 종목코드: 내부 표준은 6자리 `005930`, CREON 호출 시 `A005930` 변환

### 5.2 예상 사용 객체 (구현 시 실측 조정)

| 용도 | COM 계열 (예시) |
|------|-----------------|
| 접속 | `CpUtil.CpCybos` |
| 종목/시장 | `CpUtil.CpCodeMgr` |
| 시총·기본정보 | `dscbo1.StockMst` 또는 MarketEye |
| 일봉 OHLCV | `CpSysDib.StockChart` |

CREON 전용 모듈은 다른 모듈과 분리해, 폴백 경로가 COM에 의존하지 않게 한다.

## 6. DART 연동

- `DART_API_KEY` 로 기업 고유번호(corp_code) 매핑 후 분기 재무 조회
- 계정: 영업이익 (표기 변종 흡수: 계정명 후보 리스트 + sj_div IS/CIS)
- 보고서: 종목별 **가장 최근 정기 공시**(1분기·반기·3분기·사업)의 영업이익을 사용
- **누적 환산 없음.** 반기·3분기·사업은 누적 수치일 수 있으므로, YoY는 **동일 보고서 유형의 전년 동기 공시**와 비교 (반기 vs 전년 반기, 사업 vs 전년 사업). 이렇게 하면 누적끼리 비교가 되어 왜곡을 피한다
- 전년 동기 동일 유형 보고서가 없으면 해당 종목 제외
- 종목·보고서 단위 JSON 캐시로 재실행 시 호출 절약
- 개별 종목 실패 시 로그만 남기고 스킵, 전체 중단하지 않음

## 7. 텔레그램 메시지

### 7.1 성공 요약 (구조)

```
📉 어닝+낙폭 스크리닝  {date}
유니버스 N · 후보 M · 신규 K  |  source={CREON|FDR|...}

⭐ 신규 진입
• {code} {name}  고점대비 {dd}%  OP YoY {yoy}%  시총 {cap}

📋 유지 (count)
• ...

↩ 이탈 (count): {codes}
```

- 4096자 초과 시 분할 전송
- HTML/Markdown 중 구현 시 이스케이프 안전한 쪽 선택 (기본: plain text 또는 최소 Markdown)

### 7.2 에러

```
[ERROR] earnings-dip: {짧은 원인}
```

예: 시세 전 경로 실패, DART 키 없음, 예외 traceback 요약.

## 8. 설정 · 운영

### 8.1 경로·파일

```
earnings-dip-bot/
  main.py
  run.bat
  config.py
  requirements.txt
  .env.example
  creon_client.py
  universe.py
  prices.py
  earnings.py
  screener.py
  state_store.py
  telegram_sender.py
  logs/earnings_dip.log
  state/last_candidates.json
  state/last_run.json
  docs/superpowers/specs/...
  tests/
```

### 8.2 환경 변수 / 설정값

| 키 | 용도 |
|----|------|
| `TELEGRAM_BOT_TOKEN` | 봇 토큰 |
| `TELEGRAM_CHAT_ID` | 수신 채팅 |
| `DART_API_KEY` | 실적 |
| `OP_YOY_MIN` | 기본 10 |
| `DRAWDOWN_MAX` | 기본 -20 (이 값 이하 통과) |
| `MIN_MARKET_CAP_UK` | 기본 1000 (억) |
| `MIN_VALUE_UK` | 기본 100 (억, 거래대금) |
| `PREFER_CREON` | true |
| `ALLOW_PRICE_FALLBACK` | true |
| `SKIP_IF_ALREADY_RAN_TODAY` | true 권장 |

### 8.3 실행

- `run.bat`: 프로젝트 venv(32-bit)의 python으로 `main.py`
- Windows 작업 스케줄러: 평일 15:50~16:30
- 로그: rotating file under `logs/`
- `last_run.json`: 날짜, source, 후보 수, 신규 수, 종료 코드 요약

## 9. 에러 처리 · 종료 코드

| 상황 | 동작 | exit |
|------|------|------|
| CREON 실패 + 폴백 성공 | 경고 로그, source=폴백, 정상 스크리닝 | 0 |
| 시세 전 경로 실패 | 텔레그램 에러 | ≠0 |
| DART 키 없음 | 텔레그램 에러 | ≠0 |
| 개별 종목 실적 실패 | 스킵 | 0 유지 |
| 오늘 이미 성공 실행 + skip 옵션 | 로그 후 종료 | 0 |
| 미처리 예외 | 텔레그램 에러 + 로그 | ≠0 |

## 10. 테스트 전략

| 종류 | 내용 |
|------|------|
| 단위 | drawdown 계산, YoY 계산, 신규/유지/이탈 set 로직, 코드 A접두 변환 |
| 단위 | 유니버스 필터 경계값 (999억 제외, 1000억 포함) |
| 통합(옵션) | mock 시세+실적으로 end-to-end 메시지 문자열 |
| 수동 | CREON 로그인 후 실기 1회, CREON 종료 후 폴백 1회, 텔레그램 수신 확인 |

Mock 시세로 운영 결과를 대체하지 않는다. 테스트 픽스처만 mock 허용.

## 11. 성공 기준

1. CREON 로그인 상태에서 유니버스·52주 낙폭이 채워진다.
2. DART OP YoY 필터 후 후보가 산출된다 (0개여도 요약 전송).
3. 텔레그램에 신규 강조 포함 요약이 도착한다.
4. CREON 미기동 시 폴백으로 end-to-end 완료 가능하다.
5. 동일 일자 재실행 시 skip 옵션이 동작한다.
6. 핵심 계산·set diff에 대한 단위 테스트가 통과한다.

## 12. 구현 순서 (개요)

1. 프로젝트 스캐폴드, config, telegram, state
2. CREON client + 폴백 prices/universe
3. DART earnings + 캐시
4. screener + main 오케스트레이션
5. run.bat, 로그, 스케줄 문서
6. 단위 테스트 + 수동 검증

상세 태스크는 본 스펙 승인 후 implementation plan 문서에서 분해한다.

## 13. 결정 로그

| 결정 | 선택 |
|------|------|
| 어닝 정의 | OP YoY ≥ 10% (컨센서스 아님) |
| 낙폭 | 52주 고점 대비 ≤ -20% |
| 주기 | 장 마감 후 1일 1회 |
| 유니버스 | 시총 1000억 + 대금 100억 |
| 알림 | 매일 요약 + 신규 강조 |
| 프로젝트 | 독립 폴더 `earnings-dip-bot` |
| 아키텍처 | 경량 배치 봇 |
| 시세 | CREON 우선, FDR/pykrx 폴백 |
| 실적 | DART |
| DB | 1차 JSON state only |
---
