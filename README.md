# OpenClaw Project

OpenClaw 是一个用于扫描和分析技能（skills）的项目，主要关注安全扫描和元数据收集。

## 📦 Install Dependencies

本项目使用 [`uv`](https://github.com/astral-sh/uv) 管理 Python 虚拟环境和依赖。

```bash
uv venv
uv sync
```

## 🔧 Crawling Module

`crawling/` 目录包含用于收集和分析技能数据的工具，主要分为两个子模块：

### 1. Skills Crawling (`crawling/skills/`)

负责从 Skills.sh 平台爬取技能元数据和 GitHub 信息。

#### `crawling/skills/skills_sh/crawl_skills_sh.py`
- **功能**: 从 Skills.sh API 爬取所有技能的元数据
- **输出**: SQLite 数据库（`skills.db`）
- **主要参数**:
  - `--db`: 输出数据库路径（默认: `skills.db`）

#### `crawling/skills/skills_sh/download_skills.py`
- **功能**: 从 SQLite 数据库中读取技能的 GitHub 仓库信息，并下载这些仓库到本地
- **输入**: `skills.db`（包含 GitHub URLs）
- **输出**: 本地克隆的 GitHub 仓库目录
- **主要参数**:
  - `--db`: 输入数据库路径（默认: `skills.db`）
  - `--out`: 输出目录（默认: `downloaded_skills`）
  - `--limit`: 仅处理前 N 个唯一仓库（可选）
  - `--print-only`: 仅打印唯一仓库列表，不克隆

#### `crawling/skills/skills_sh/enrich_github_metadata_v2.py`
- **功能**: 从 SQLite 数据库中读取技能的 GitHub 仓库信息，并通过 GitHub API 获取仓库元数据（stars, 存在性等）
- **输入**: `sqlite.db`（默认，包含 `repo_marketplace_links` 表）
- **输出**: 更新的 SQLite 数据库（`sqlite.db`）
- **主要参数**:
  - `--db`: 输入/输出数据库路径（默认: `sqlite.db`）
  - `--token`: GitHub API Token（可选，用于提高速率限制）
  - `--verbose`: 打印处理进度

### 2. Security Crawling (`crawling/security_infos/`)

负责爬取技能的安全扫描信息。

#### `crawling/security_infos/openclaw/crawl_clawhub_security_to_sqlite.py`
- **功能**: 从 ClawHub Convex API 爬取技能的安全扫描数据（VirusTotal 和 OpenClaw 扫描结果）
- **输入**: `pipeline.jsonl`（包含技能列表）
- **输出**: SQLite 数据库（`clawhub_security_scans.sqlite`）
- **主要参数**:
  - `--input`: 输入的 `pipeline.jsonl` 路径（默认: `pipeline.jsonl`）
  - `--db`: 输出 SQLite 数据库路径（默认: `clawhub_security_scans.sqlite`）
  - `--workers`: 并发请求数（默认: 16）
  - `--timeout`: HTTP 超时时间（秒，默认: 25.0）
  - `--limit`: 限制爬取的技能数量（0 表示全部）

#### `crawling/security_infos/skills_sh/scrape_skills_security.py`
- **功能**: 从 Skills.sh 网站抓取技能的安全审计页面 HTML，并解析 Socket 审计结果
- **输入**: SQLite 数据库（`04_03_2026.db` 默认）
- **输出**: SQLite 数据库（`04_03_2026.db`，新增安全扫描表）
- **主要参数**:
  - `--db`: 数据库路径（默认: `04_03_2026.db`）
  - `--workers`: 并发请求数（默认: 10）
  - `--timeout`: HTTP 超时时间（秒，默认: 20）
  - `--resume`: 跳过已扫描的技能

## 🚀 使用示例

### 爬取技能元数据
```bash
cd crawling/skills/skills_sh
python crawl_skills_sh.py --db skills.db
```

### 补充 GitHub 元数据
```bash
cd crawling/skills/skills_sh
python enrich_github_metadata_v2.py --db sqlite.db --verbose
```

### 下载技能对应的 GitHub 仓库
```bash
cd crawling/skills/skills_sh
python download_skills.py --db skills.db --out downloaded_skills
```

### 爬取 ClawHub 安全扫描数据
```bash
cd crawling/security_infos/openclaw
python crawl_clawhub_security_to_sqlite.py --input pipeline.jsonl --db clawhub_security_scans.sqlite --workers 16
```

### 爬取 Skills.sh 安全审计信息
```bash
cd crawling/security_infos/skills_sh
python scrape_skills_security.py --db 04_03_2026.db --workers 10
```