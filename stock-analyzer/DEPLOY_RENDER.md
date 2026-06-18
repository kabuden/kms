# Render 무료 배포 가이드 (모바일 상시 접속용)

이 문서대로 **PC 브라우저에서 한 번만** 설정하면, 이후엔 PC를 꺼도 휴대폰에서
24시간 접속할 수 있습니다. **API 키·결제 카드 불필요**(무료 등급).

> 한 줄 요약: 깃허브 → Render 연결 → Blueprint 자동 인식 → 배포 끝.

---

## 0. 사전 준비
- 이 저장소가 GitHub에 있어야 합니다. (지금 `claude/stock-prediction-analyzer-kscp4j`
  브랜치에 코드가 올라가 있습니다. 배포 전에 이 브랜치를 `main`/기본 브랜치에
  머지하거나, 아래 4단계에서 배포 브랜치를 이 브랜치로 지정하세요.)
- 무료 Render 계정 (https://render.com — GitHub 계정으로 가입 가능)

## 1. Render에 로그인 → New → Blueprint
1. https://dashboard.render.com 접속 후 로그인
2. 우측 상단 **New +** → **Blueprint** 선택
3. 본인의 GitHub 저장소(`kabuden/kms`) 연결 → 선택

## 2. Blueprint 자동 인식
- 저장소 루트의 `render.yaml` 을 Render가 자동으로 읽습니다.
- 서비스 이름 `stock-analyzer`, 무료(free) 플랜, 싱가포르 리전이 미리 설정돼 있습니다.
- **Apply** 클릭

## 3. 배포 대기 (2~4분)
- 빌드(파이썬 준비) → 시작(`python run.py serve`) → 콜드 스타트 시 합성 20사이클
  시드 → 헬스체크 통과 순으로 진행됩니다.
- 상태가 **Live** 가 되면 완료.

## 4. (필요 시) 배포 브랜치 지정
- 기본 브랜치가 아닌 `claude/stock-prediction-analyzer-kscp4j` 를 배포하려면:
  서비스 → **Settings** → **Branch** 를 해당 브랜치로 변경 → 수동 **Deploy**.

## 5. 휴대폰에서 접속
- 서비스 상단의 `https://stock-analyzer-xxxx.onrender.com` 주소를 폰 브라우저로 열기
- 홈 화면에 **추가**하면 앱처럼 쓸 수 있습니다(별도 앱 설치 불필요).

---

## ⚠️ 무료 등급에서 꼭 알아둘 점
| 항목 | 내용 | 대응 |
|---|---|---|
| **잠자기** | 15분간 접속이 없으면 자동으로 잠듦. 다음 접속 시 깨어나는 데 30초~1분 | 정상 동작. 잠깐 기다리면 열림 |
| **학습 초기화** | 무료는 디스크가 휘발성 → 재시작/재배포 시 DB 초기화 | `SA_SEED_CYCLES=20` 으로 첫 화면에 학습 곡선(합성)을 자동 채움 |
| **누적 학습 보관** | 매일 쌓는 학습을 영구 보존하려면 영구 디스크(유료) 필요 | `render.yaml` 하단 `disk:` 주석 해제 + `SA_DB_DIR=/var/data` 추가 |

## 환경변수 (대시보드 Settings → Environment 에서 변경 가능)
| 변수 | 기본 | 의미 |
|---|---|---|
| `SA_OFFLINE` | `true` | 합성 데이터(무키·무료). 실시세를 쓰려면 `false`(아래 참고) |
| `SA_USE_LLM` | `false` | LLM 예측 #5. **구독형 AI는 코드 호출 불가**이므로 그대로 두세요 |
| `SA_SEED_CYCLES` | `20` | 콜드 스타트 시 미리 채울 합성 학습 사이클 수 |
| `SA_MIN_CYCLES` | `10` | 실거래 게이트: 최소 학습 사이클 |
| `SA_MIN_ACCURACY` | `0.58` | 실거래 게이트: 최소 롤링 정확도 |

### 실시세/뉴스(yfinance·RSS)를 켜고 싶다면
`render.yaml` 의 `buildCommand` 를 아래로 바꾸고 `SA_OFFLINE=false` 로 변경:
```
buildCommand: "pip install -r requirements.txt"
```
> 단, 무료 등급은 메모리·빌드 시간이 제한적이라 yfinance(=pandas 등) 설치가
> 무거울 수 있습니다. 먼저 합성 모드로 충분히 검증한 뒤 전환을 권장합니다.

---

## 대안: Render 없이 빠르게 폰에서 보기 (PC 켜둔 동안만)
```bash
cd stock-analyzer
python run.py serve --port 8000
# 다른 터미널에서
npx cloudflared tunnel --url http://localhost:8000   # 또는: ngrok http 8000
```
출력되는 `https://....` 주소를 폰에서 열면 됩니다. (PC를 끄면 끊깁니다.)
