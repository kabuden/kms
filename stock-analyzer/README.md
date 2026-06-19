# 📈 주식 예측 멀티에이전트 시스템 (Stock Analyzer)

미국·한국 시장의 경제뉴스와 애널리스트 의견을 취합·분석하여 **매일 주가 방향을
예측**하고, 다음 거래일의 **실제 변화와 일치 여부를 평가**한다. 여러 사이클의
학습으로 **정확도와 신뢰도를 축적**한 뒤, 충분한 검증을 거치면 실거래 참고에
활용할 수 있도록 설계된 웹 기반 시스템이다.

> ⚠️ **면책**: 본 시스템은 연구·학습 목적입니다. 어떤 예측도 수익을 보장하지
> 않으며, 실제 투자 판단의 유일한 근거로 사용하지 마세요.

---

## 🧩 에이전트 구성

요청하신 멀티에이전트 구조를 그대로 구현했습니다.

### 📰 수집 에이전트 (2)
| 에이전트 | 역할 |
|---|---|
| `us-collector` | 미국 시장 경제뉴스 + 애널리스트 의견 수집 (CNBC/Yahoo RSS) |
| `kr-collector` | 한국 시장 경제뉴스 + 애널리스트 의견 수집 (인포맥스/한경 RSS) |

### 🧠 예측 에이전트 (5) — *각기 다른 방식*
| 에이전트 | 방법론 |
|---|---|
| `momentum` | 기술적 모멘텀(이동평균/추세 지속) |
| `sentiment` | 뉴스 감성 종합 |
| `analyst_consensus` | 증권사 등급·목표가 컨센서스 |
| `mean_reversion` | 평균회귀(z-score 되돌림, 역추세) |
| `llm_reasoner` | 뉴스·애널리스트·시세를 LLM으로 추론 종합 (폴백 내장) |

### 🔧 발전 에이전트 (3) — *평가하고 발전시킴*
| 에이전트 | 역할 |
|---|---|
| `weight_optimizer` | 최근 적중률에 비례해 앙상블 가중치 재배분 |
| `strategy_critic` | 부진한 예측 에이전트 진단·개선 방향 제시 |
| `confidence_calibrator` | 정확도 추적 → 보정 신뢰도 산출 → **실거래 가능 여부 판정** |

### 🔁 매일 반복되는 루프
```
수집(2) → 예측(5) → 앙상블 종합 → [다음날] 실제값과 평가 → 발전(3)가 개선
        └────────────  작업 → 결과 평가 → 발전  ────────────┘
```

---

## 🚀 실행 방법

별도 설치 없이 **표준 라이브러리만으로** 동작합니다 (Python 3.11+).

```bash
cd stock-analyzer

# 1) 학습 시뮬레이션 (예: 30 사이클 백테스트)
python run.py backtest --days 30

# 2) 현재 신뢰도/정확도 확인
python run.py status

# 3) 웹 대시보드 실행 → 브라우저에서 http://localhost:8000
python run.py serve --port 8000
```

대시보드에서 **'새 사이클 실행'** / **'10 사이클 학습'** 버튼으로 직접 루프를
돌리고, 종목별 5개 예측·앙상블·적중 여부·발전 로그·신뢰도 추이를 볼 수 있습니다.

### 실데이터 모드 (`SA_OFFLINE=false`) — API 키 불필요, 추가 설치 불필요
실시세·실뉴스 모두 **파이썬 표준 라이브러리만으로** 받아옵니다(무료·무키).

```bash
export SA_OFFLINE=false        # 실시세 + 실뉴스
python run.py serve
```

| 항목 | 소스 | 방식 |
|---|---|---|
| **시세** | Yahoo Finance 차트 JSON | urllib 직접 호출(pandas 불필요), 프로세스 내 캐시 |
| **시장 뉴스** | Google News RSS(+CNBC·MarketWatch·한경·연합) | stdlib XML 파싱 |
| **종목 뉴스** | Google News 종목 검색 RSS | 종목별 직접 관련 기사 |
| **감성** | 사전(lexicon, 영문+국문) | 키 불필요 |

> **뉴스의 한계**: RSS는 '현재' 뉴스만 제공합니다. 과거 날짜(시드/백테스트)는
> 실제 시세로 평가하되 뉴스는 비웁니다. 뉴스 효과는 '오늘' 실시간 운영부터 반영됩니다.
>
> **애널리스트 의견**은 아직 시뮬레이션입니다(무료 실데이터 소스가 제한적).
> 시세·뉴스가 실데이터 핵심이며, 애널리스트 컨센서스 실연동은 향후 과제입니다.

### 종목 유니버스 (15)
미국: S&P500·나스닥 지수 + Apple·Microsoft·NVIDIA·Amazon·Alphabet·Tesla /
한국: 코스피 + 삼성전자·SK하이닉스·현대차·NAVER·카카오·LG에너지솔루션.
`app/config.py` 의 `universe` 에서 언제든 추가/교체할 수 있습니다.

### LLM 예측 에이전트(#5) 켜기 (선택)
구독형 AI는 코드 호출이 안 되므로 기본 비활성입니다. 별도 API 키가 있으면:
```bash
pip install anthropic
export SA_USE_LLM=true ANTHROPIC_API_KEY=sk-...
```

---

## 📱 모바일에서 쓰기 (무료 배포)

PC를 계속 켜둘 필요 없이, **무료 클라우드에 한 번만 배포**하면 휴대폰에서
24시간 접속할 수 있습니다. 저장소 루트의 `render.yaml` 로 Render에 바로 올라가며
**API 키·결제 불필요**입니다. 단계별 안내: [`DEPLOY_RENDER.md`](./DEPLOY_RENDER.md)

> 서버는 `$PORT` 환경변수와 `0.0.0.0` 바인딩을 지원하므로 Render·Railway·Fly.io
> 등 대부분의 PaaS에 그대로 올라갑니다. 콜드 스타트 시 `SA_SEED_CYCLES` 만큼
> 합성 학습을 미리 채워 첫 화면이 비지 않습니다.

---

## 🎯 신뢰도 게이트 (실거래 사용 기준)

`confidence_calibrator` 가 아래 조건을 **모두** 만족할 때만
`trade_ready = true` 로 전환합니다 (`.env` 로 조정 가능).

- 학습 사이클 수 ≥ `SA_MIN_CYCLES` (기본 10)
- 롤링 정확도 ≥ `SA_MIN_ACCURACY` (기본 0.58)

이 기준에 도달하기 전에는 대시보드 상단 배너가 **"학습/검증 단계"** 로 표시되며,
실투자 사용을 보류하도록 안내합니다.

---

## 🏗️ 구조

```
stock-analyzer/
├── run.py                      # CLI (serve / cycle / backtest / status / roster)
├── app/
│   ├── config.py               # 설정·종목 유니버스
│   ├── models.py               # 도메인 모델
│   ├── storage.py              # SQLite 영속 계층
│   ├── market_data.py          # 시세(yfinance + 합성 폴백)
│   ├── ensemble.py             # 5개 예측 가중 종합
│   ├── evaluation.py           # 예측 vs 실제 평가
│   ├── orchestrator.py         # 일일 사이클 조율
│   ├── agents/
│   │   ├── collectors/         # 수집 2인
│   │   ├── predictors/         # 예측 5인
│   │   └── improvers/          # 발전 3인
│   └── web/                    # stdlib 웹서버 + 대시보드(HTML/JS/CSS)
└── requirements.txt            # 선택적 의존성(실데이터/LLM)
```

## 🔭 다음 단계(확장 아이디어)
- 실데이터 모드 안정화(거래일 캘린더, 휴장일 처리)
- 예측 에이전트 추가 및 자동 A/B 비교
- LLM 기반 `strategy_critic` 의 로직 자동 수정 제안
- 사용자 인증 + 포트폴리오/알림 기능
