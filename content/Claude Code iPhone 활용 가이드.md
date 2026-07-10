---
Created: 2026-04-21 00:00
tags:
  - ✏️
aliases:
---

# 아이폰에서 Claude Code 사용하기

아이폰에서 Claude Code를 활용하는 방법을 정리한 실용 가이드.

---

## 1. Claude iOS 앱 활용

- App Store에서 **Claude** 앱 다운로드
- `claude.ai/code` 에서 웹 세션 시작 및 모니터링 가능
- Safari 등 모바일 브라우저로 `claude.ai/code` 접속하여 사용

---

## 2. Remote Control (핵심 기능)

데스크톱에서 실행 중인 Claude Code 세션을 아이폰으로 모니터링·제어하는 기능.

**설정 방법:**
1. 데스크톱에서 `claude` 실행
2. Remote Control 활성화
3. 아이폰으로 QR 코드 스캔하여 연결

**주요 특징:**
- 메시지 실시간 동기화
- 로컬 환경(파일, 툴, 컨텍스트) 유지
- Push 알림 지원 → 긴 작업 완료 시 알림 수신
- 지원 플랜: Pro / Max / Team / Enterprise

---

## 3. SSH 앱을 통한 CLI 접근

원격 서버에서 직접 `claude` CLI를 실행하는 방식.

| 앱 | 특징 |
|---|---|
| Termius | GUI 친화적, 무료 기본 제공 |
| Blink Shell | 고급 사용자용, 유료 |

원격 서버에 SSH 접속 → `claude` 명령어 실행

---

## 4. 아이폰의 한계

- 네이티브 터미널 없음 → SSH 앱 필수
- 작은 화면으로 코드 편집 어려움
- 일부 인터랙티브 CLI 명령어(예: `vim`, `less`) 미지원 또는 불편

---

## 5. 실용적 워크플로우 추천

| 상황 | 추천 방법 |
|---|---|
| 가벼운 질문·코드 생성 | Claude iOS 앱 또는 모바일 웹 |
| 진행 중인 작업 모니터링 | Remote Control |
| PR 리뷰 | 모바일 웹 브라우저 (`github.com`) |
| 서버 작업이 필요한 경우 | Termius + SSH |

---

## 참고

- Remote Control은 데스크톱에서 세션이 먼저 실행되어 있어야 함
- 로컬 파일 직접 편집은 아이폰에서 불가 → 원격 서버 경유 필요
