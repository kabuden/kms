# CLAUDE.md

## 프로젝트 개요

이 저장소는 개인 지식 관리 시스템(KMS)으로 구성된 **Quartz v4.4.0** 정적 사이트 생성기입니다. Quartz는 Markdown 파일을 지식 그래프, 전문 검색, 양방향 링크를 갖춘 웹사이트로 변환합니다. 콘텐츠는 주로 한국어로 작성된 건축구조 공학 학습 노트입니다.

- **프레임워크:** Quartz v4 (TypeScript + Preact)
- **Node 버전:** 20.9.0 (`.node-version` 참고)
- **패키지 매니저:** npm >=9.3.1
- **모듈 시스템:** ES Modules (`"type": "module"`)
- **언어:** TypeScript 5.6.3 (strict 모드)

## 저장소 구조

```
kms/
├── quartz/              # 핵심 SSG 프레임워크 (Quartz 자체를 확장하는 경우가 아니면 수정 금지)
│   ├── bootstrap-cli.mjs    # CLI 진입점
│   ├── build.ts             # 빌드 오케스트레이션
│   ├── cfg.ts               # 설정 타입 정의
│   ├── depgraph.ts          # 증분 빌드를 위한 의존성 그래프
│   ├── worker.ts            # 워커 스레드 구현
│   ├── components/          # Preact UI 컴포넌트 (Head, Graph, Search, Explorer 등)
│   ├── plugins/
│   │   ├── transformers/    # Markdown 변환 플러그인
│   │   ├── filters/         # 콘텐츠 필터 플러그인
│   │   └── emitters/        # 출력 생성 플러그인
│   ├── processors/          # parse.ts, filter.ts, emit.ts
│   ├── util/                # 경로, 테마, glob, 로깅 유틸리티
│   ├── i18n/locales/        # 20개 언어 로케일 파일
│   ├── styles/              # SCSS 스타일시트 (base, variables, callouts, syntax, custom)
│   ├── static/              # 정적 에셋 (icon.png, og-image.png)
│   └── cli/                 # CLI 인수/핸들러/헬퍼 모듈
├── content/             # 모든 사용자 Markdown 콘텐츠 (2,877개 이상 파일)
│   ├── index.md             # 사이트 홈페이지
│   └── (NN) 폴더명/         # 번호가 붙은 카테고리 폴더 (건축구조 주제)
├── docs/                # Quartz 프레임워크 문서 (별도 서빙)
├── public/              # 빌드 출력 결과 (git 제외, 자동 생성)
├── quartz.config.ts     # 주요 설정: 사이트 제목, 플러그인, 테마, 분석
├── quartz.layout.ts     # 주요 레이아웃: 컴포넌트 배치 위치
├── tsconfig.json        # TypeScript 설정
├── package.json         # 의존성 및 스크립트
└── Dockerfile           # 2단계 Docker 빌드
```

## 주요 설정 파일

### `quartz.config.ts`
메인 사이트 설정 파일. 다음 항목을 수정할 수 있습니다:
- `pageTitle` — 표시되는 사이트 이름
- `baseUrl` — 프로덕션 URL
- `locale` — 사이트 언어 (현재 `en-US`)
- `ignorePatterns` — 빌드에서 제외할 폴더 (`private`, `templates`, `.obsidian`)
- `analytics` — 분석 제공자 (현재 Plausible)
- `theme` — 폰트 (Schibsted Grotesk / Source Sans Pro / IBM Plex Mono) 및 색상 팔레트
- `plugins.transformers` — Markdown 처리 파이프라인
- `plugins.filters` — 콘텐츠 포함/제외 규칙
- `plugins.emitters` — 출력 유형 (HTML 페이지, RSS, 사이트맵, 검색 인덱스)

**현재 활성화된 플러그인:**
| 유형 | 플러그인 |
|---|---|
| Transformer | FrontMatter, CreatedModifiedDate, SyntaxHighlighting, ObsidianFlavoredMarkdown, GitHubFlavoredMarkdown, TableOfContents, CrawlLinks, Description, Latex (KaTeX) |
| Filter | RemoveDrafts |
| Emitter | AliasRedirects, ComponentResources, ContentPage, FolderPage, TagPage, ContentIndex (RSS + 사이트맵), Assets, Static, NotFoundPage |

### `quartz.layout.ts`
각 페이지 레이아웃에 렌더링할 Preact 컴포넌트를 제어합니다:
- **공통** (모든 페이지): `Head`, `Footer`
- **콘텐츠 페이지** (단일 노트):
  - `beforeBody`: Breadcrumbs, ArticleTitle, ContentMeta, TagList
  - `왼쪽 사이드바`: PageTitle, Search, Darkmode, Explorer
  - `오른쪽 사이드바`: Graph, TableOfContents, Backlinks
- **목록 페이지** (폴더/태그):
  - `beforeBody`: Breadcrumbs, ArticleTitle, ContentMeta
  - `왼쪽 사이드바`: PageTitle, Search, Darkmode, Explorer

## 개발 워크플로우

### 의존성 설치
```bash
npm install
```

### 사이트 빌드
```bash
npx quartz build
```

### 로컬 빌드 및 서빙 (핫 리로드 포함)
```bash
npx quartz build --serve
```

### 타입 검사 및 린트
```bash
npm run check        # tsc --noEmit + prettier 검사
npm run format       # prettier 자동 포맷
```

### 테스트 실행
```bash
npm test             # 경로 유틸리티 + 의존성 그래프 테스트
```

### docs 폴더 빌드 및 서빙
```bash
npm run docs
```

### Docker
```bash
docker build -t kms .
docker run -p 8080:8080 kms
```
컨테이너는 `npx quartz build --serve`를 CMD로 실행합니다.

## 콘텐츠 작성 규칙

콘텐츠는 `content/` 폴더에 위치합니다. 파일은 다음 규칙을 따릅니다:

- **Frontmatter:** 각 파일 상단의 YAML. 주요 필드:
  ```yaml
  ---
  title: 노트 제목
  tags: [태그1, 태그2]
  draft: true   # 빌드에서 제외하려면 설정
  date: 2024-01-01
  ---
  ```
- **초안 제외:** frontmatter에 `draft: true`가 있는 파일은 `RemoveDrafts` 필터로 제외됩니다.
- **무시 패턴:** `private`, `templates`, `.obsidian` 폴더는 완전히 제외됩니다.
- **링크:** Obsidian 스타일 위키링크 `[[노트 제목]]` 사용 — `CrawlLinks` 플러그인이 "shortest" 전략으로 해결합니다.
- **수식:** KaTeX 문법을 `$인라인$` 및 `$$블록$$` 형식으로 지원합니다.
- **폴더 이름:** 콘텐츠 폴더는 `(03) 카테고리/` 형식의 번호 접두사로 순서를 제어합니다.
- **언어:** 콘텐츠는 주로 한국어(한국어)이며, 사이트 로케일은 `en-US`로 설정되어 있지만 한국어 파일명과 콘텐츠도 정상 동작합니다.

### 콘텐츠 카테고리 구조
```
(02) ...
(03) 구조설계/
    1. 일반 및 기타/
    2. 설계개념 및 하중/
    3. 내진설계/
    4. RC(철콘)/
    5. STL(철골)/
    6. 역학/
(11) 서술형 노트/
(12) 계산형 노트/
(21) 문제모음/
(22) 풀이모음/
(31) 회차별 기출문제/
(32) 134회 대비/
(37) 기술사준비/
(41) 참고자료/
(51) 면접준비/
(98) 템플릿/
(99) 첨부파일/
```

## 코드 컨벤션

### TypeScript
- strict 모드 활성화 — 암묵적 `any` 및 암묵적 반환 금지
- ES 모듈 임포트 (`import`/`export`), CommonJS `require()` 사용 금지
- JSX는 Preact 사용 (tsconfig에서 `jsxImportSource: "preact"`)
- 타깃: `esnext`; 증분 컴파일 활성화

### 포맷팅 (Prettier)
- `printWidth`: 100
- `trailingComma`: all
- `tabWidth`: 2
- `semi`: false (세미콜론 없음)
- `quoteProps`: as-needed

TypeScript/JS 변경 사항을 커밋하기 전에 `npm run format`을 실행하세요.

### 플러그인 아키텍처
Quartz 플러그인은 `quartz/plugins/`에 위치한 순수 TypeScript 모듈입니다. 각 카테고리는 정의된 인터페이스를 가집니다:
- **Transformers** (`QuartzTransformerPlugin`): remark/rehype를 통해 Markdown AST 처리
- **Filters** (`QuartzFilterPlugin`): 포함할 콘텐츠 파일 결정
- **Emitters** (`QuartzEmitterPlugin`): 출력 파일 생성 (HTML, JSON, XML 등)

새 플러그인 추가 시 `quartz.config.ts`의 해당 배열에 등록하세요.

### 컴포넌트 아키텍처
UI 컴포넌트는 `quartz/components/`에 위치하며 Preact 함수형 컴포넌트입니다. 클라이언트 측 인터랙티비티 스크립트는 `quartz/components/scripts/`에, 컴포넌트 스코프 스타일은 `quartz/components/styles/`에 있습니다.

## 빌드 파이프라인

1. **Parse** — 모든 Markdown 파일을 읽고 `gray-matter`로 frontmatter를 파싱하여 remark AST를 생성
2. **Transform** — 트랜스포머 플러그인을 적용해 Markdown → HTML AST 변환 (remark → rehype)
3. **Filter** — 초안 및 무시 패턴 제거
4. **Emit** — 이미터 플러그인으로 출력 파일 생성 (HTML, 검색 인덱스, RSS, 사이트맵)
5. **Assets** — 정적 파일을 `public/`으로 복사

빌드는 의존성 그래프(`quartz/depgraph.ts`)를 사용해 `--serve` 워치 모드 중 변경되지 않은 파일의 재처리를 방지합니다. 워커 스레드(`workerpool`)가 파일 처리를 병렬화합니다.

## Git 워크플로우

- 활성 개발 브랜치: `claude/claude-md-docs-0Tpu6`
- 푸시 명령: `git push -u origin <브랜치명>`
- `.gitignore` 제외 항목: `node_modules/`, `public/`, `.quartz-cache/`

## CI/CD

`.github/workflows/`의 GitHub Actions 워크플로우:
- `ci.yaml` — 푸시 시 타입 검사 및 테스트 실행
- `docker-build-push.yaml` — Docker 이미지 빌드 및 푸시

## 자주 하는 작업

### 콘텐츠 추가 또는 편집
`content/`에 `.md` 파일을 생성/편집하세요. 로컬 `--serve` 모드에서는 빌드 단계가 필요 없으며, 파일 감시자가 변경 사항을 자동으로 감지합니다.

### 사이트 제목 또는 URL 변경
`quartz.config.ts` → `configuration.pageTitle` 및 `configuration.baseUrl` 수정.

### 새 플러그인 추가
1. `quartz/plugins/{transformers,filters,emitters}/myplugin.ts` 파일 생성
2. `quartz/plugins/index.ts`에서 export
3. `quartz.config.ts`에 등록

### 테마 색상 커스터마이징
`quartz.config.ts`의 `colors.lightMode` 및 `colors.darkMode` 객체 수정.

### 레이아웃 커스터마이징
`quartz.layout.ts`를 편집해 컴포넌트를 추가, 제거, 재배치하세요.

### 폰트 변경
`quartz.config.ts`의 `theme.typography`를 수정하세요. 기본적으로 Google Fonts에서 로드됩니다 (`fontOrigin: "googleFonts"`).
