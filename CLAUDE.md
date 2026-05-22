# CLAUDE.md

## Project Overview

This repository is a **Quartz v4.4.0** static site generator configured as a personal knowledge management system (KMS). Quartz converts Markdown files into a navigable website with a knowledge graph, full-text search, and bidirectional links. The content is primarily Korean-language structural engineering study notes.

- **Framework:** Quartz v4 (TypeScript + Preact)
- **Node version:** 20.9.0 (see `.node-version`)
- **Package manager:** npm >=9.3.1
- **Module system:** ES Modules (`"type": "module"`)
- **Language:** TypeScript 5.6.3 (strict mode)

## Repository Structure

```
kms/
├── quartz/              # Core SSG framework (do not modify unless extending Quartz itself)
│   ├── bootstrap-cli.mjs    # CLI entry point
│   ├── build.ts             # Main build orchestration
│   ├── cfg.ts               # Configuration type definitions
│   ├── depgraph.ts          # Dependency graph for incremental rebuilds
│   ├── worker.ts            # Worker thread implementation
│   ├── components/          # Preact UI components (Head, Graph, Search, Explorer, etc.)
│   ├── plugins/
│   │   ├── transformers/    # Markdown transformation plugins
│   │   ├── filters/         # Content filter plugins
│   │   └── emitters/        # Output generation plugins
│   ├── processors/          # parse.ts, filter.ts, emit.ts
│   ├── util/                # Path, theme, glob, logging utilities
│   ├── i18n/locales/        # 20 language locale files
│   ├── styles/              # SCSS stylesheets (base, variables, callouts, syntax, custom)
│   ├── static/              # Static assets (icon.png, og-image.png)
│   └── cli/                 # CLI argument/handler/helper modules
├── content/             # All user Markdown content (2,877+ files)
│   ├── index.md             # Site homepage
│   └── (NN) FolderName/     # Numbered category folders (Korean structural engineering topics)
├── docs/                # Quartz framework documentation (served separately)
├── public/              # Build output (git-ignored, generated)
├── quartz.config.ts     # PRIMARY config: site title, plugins, theme, analytics
├── quartz.layout.ts     # PRIMARY layout: which components appear where
├── tsconfig.json        # TypeScript configuration
├── package.json         # Dependencies and scripts
└── Dockerfile           # Two-stage Docker build
```

## Key Configuration Files

### `quartz.config.ts`
The main site configuration. Edit this to change:
- `pageTitle` — displayed site name
- `baseUrl` — production URL
- `locale` — site language (currently `en-US`)
- `ignorePatterns` — folders excluded from build (`private`, `templates`, `.obsidian`)
- `analytics` — analytics provider (currently Plausible)
- `theme` — fonts (Schibsted Grotesk / Source Sans Pro / IBM Plex Mono) and color palette
- `plugins.transformers` — Markdown processing pipeline
- `plugins.filters` — content inclusion/exclusion rules
- `plugins.emitters` — output types (HTML pages, RSS, sitemap, search index)

**Current active plugins:**
| Type | Plugin |
|---|---|
| Transformer | FrontMatter, CreatedModifiedDate, SyntaxHighlighting, ObsidianFlavoredMarkdown, GitHubFlavoredMarkdown, TableOfContents, CrawlLinks, Description, Latex (KaTeX) |
| Filter | RemoveDrafts |
| Emitter | AliasRedirects, ComponentResources, ContentPage, FolderPage, TagPage, ContentIndex (RSS + sitemap), Assets, Static, NotFoundPage |

### `quartz.layout.ts`
Controls which Preact components render on each page layout:
- **Shared** (all pages): `Head`, `Footer`
- **Content pages** (single notes):
  - `beforeBody`: Breadcrumbs, ArticleTitle, ContentMeta, TagList
  - `left sidebar`: PageTitle, Search, Darkmode, Explorer
  - `right sidebar`: Graph, TableOfContents, Backlinks
- **List pages** (folders/tags):
  - `beforeBody`: Breadcrumbs, ArticleTitle, ContentMeta
  - `left sidebar`: PageTitle, Search, Darkmode, Explorer

## Development Workflow

### Install dependencies
```bash
npm install
```

### Build the site
```bash
npx quartz build
```

### Build and serve locally (with hot reload)
```bash
npx quartz build --serve
```

### Type-check and lint
```bash
npm run check        # tsc --noEmit + prettier check
npm run format       # auto-format with prettier
```

### Run tests
```bash
npm test             # path utilities + dependency graph tests
```

### Build and serve the docs folder
```bash
npm run docs
```

### Docker
```bash
docker build -t kms .
docker run -p 8080:8080 kms
```
The container runs `npx quartz build --serve` as its CMD.

## Content Guidelines

Content lives in `content/`. Files follow these conventions:

- **Frontmatter:** YAML at the top of each file. Key fields:
  ```yaml
  ---
  title: Note Title
  tags: [tag1, tag2]
  draft: true   # set to exclude from build
  date: 2024-01-01
  ---
  ```
- **Draft exclusion:** Files with `draft: true` in frontmatter are excluded by the `RemoveDrafts` filter.
- **Ignored patterns:** Folders named `private`, `templates`, or `.obsidian` are excluded entirely.
- **Links:** Use Obsidian-style wikilinks `[[Note Title]]` — the `CrawlLinks` plugin resolves them using "shortest" strategy.
- **Math:** KaTeX syntax is supported via `$inline$` and `$$block$$`.
- **Folder naming:** Content folders use numbered prefixes like `(03) Category/` to control ordering.
- **Language:** Content is primarily Korean (한국어); the site locale is set to `en-US` but Korean filenames and content work fine.

### Content category structure
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

## Code Conventions

### TypeScript
- Strict mode is enabled — no implicit `any`, no implicit returns
- ES module imports (`import`/`export`), no CommonJS `require()`
- JSX uses Preact (`jsxImportSource: "preact"` in tsconfig)
- Target: `esnext`; incremental compilation enabled

### Formatting (Prettier)
- `printWidth`: 100
- `trailingComma`: all
- `tabWidth`: 2
- `semi`: false (no semicolons)
- `quoteProps`: as-needed

Run `npm run format` before committing TypeScript/JS changes.

### Plugin Architecture
Quartz plugins are pure TypeScript modules in `quartz/plugins/`. Each category has a defined interface:
- **Transformers** (`QuartzTransformerPlugin`): process the Markdown AST via remark/rehype
- **Filters** (`QuartzFilterPlugin`): decide which content files to include
- **Emitters** (`QuartzEmitterPlugin`): generate output files (HTML, JSON, XML, etc.)

When adding a new plugin, register it in `quartz.config.ts` in the appropriate array.

### Component Architecture
UI components live in `quartz/components/` and are Preact functional components. Client-side interactivity scripts are in `quartz/components/scripts/`. Component-scoped styles go in `quartz/components/styles/`.

## Build Pipeline

1. **Parse** — reads all Markdown files, parses frontmatter with `gray-matter`, builds a remark AST
2. **Transform** — applies transformer plugins to convert Markdown → HTML AST (remark → rehype)
3. **Filter** — removes drafts and ignored patterns
4. **Emit** — generates output files from emitter plugins (HTML, search index, RSS, sitemap)
5. **Assets** — copies static files to `public/`

The build uses a dependency graph (`quartz/depgraph.ts`) to avoid reprocessing unchanged files during `--serve` watch mode. Worker threads (`workerpool`) parallelize file processing.

## Git Workflow

- Active development branch: `claude/claude-md-docs-0Tpu6`
- Push with: `git push -u origin <branch-name>`
- The `.gitignore` excludes: `node_modules/`, `public/`, `.quartz-cache/`

## CI/CD

GitHub Actions workflows in `.github/workflows/`:
- `ci.yaml` — runs type-check and tests on push
- `docker-build-push.yaml` — builds and pushes Docker image

## Common Tasks

### Add or edit content
Create/edit `.md` files in `content/`. No build step needed during local `--serve` mode; the watcher picks up changes automatically.

### Change site title or URL
Edit `quartz.config.ts` → `configuration.pageTitle` and `configuration.baseUrl`.

### Add a new plugin
1. Create `quartz/plugins/{transformers,filters,emitters}/myplugin.ts`
2. Export it from `quartz/plugins/index.ts`
3. Register it in `quartz.config.ts`

### Customize theme colors
Edit the `colors.lightMode` and `colors.darkMode` objects in `quartz.config.ts`.

### Customize layout
Edit `quartz.layout.ts` to add, remove, or reorder components.

### Change fonts
Update `theme.typography` in `quartz.config.ts`. Fonts are loaded from Google Fonts by default (`fontOrigin: "googleFonts"`).
