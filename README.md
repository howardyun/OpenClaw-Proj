# OpenClaw Project

OpenClaw 是一个围绕技能生态数据采集与安全分析的 Python 项目，当前主要覆盖两个来源：`skills.sh` 与 `SkillsDirectory`。仓库内脚本负责抓取技能清单、补充 GitHub 元数据、批量下载对应仓库，并将安全审计结果落库到 SQLite，方便后续研究、统计与复查。

> [!NOTE]
> 当前项目仍以脚本驱动为主，根目录的 `main.py` 只是一个占位入口；实际功能集中在 `crawling/` 目录。

## Features

- 从 `skills.sh` 的 sitemap 与搜索接口采集技能列表，并写入统一的 `skills` 表。
- 从 `SkillsDirectory` API 抓取技能目录数据，并写入独立的 `skills_directory.db`。
- 从技能记录中提取 GitHub 仓库地址，去重后并发克隆到本地。
- 通过 GitHub API 为仓库补充存在性、重定向、Stars 等元数据。
- 抓取 `skills.sh` 与 OpenClaw/ClawHub 的安全扫描结果，并保存为可查询的 SQLite 表。

## Project Layout

```text
.
├── analyzer/
│   ├── security matrix.md
│   └── skills_security_matrix/
├── docs/
│   └── analyzer/
├── main.py
├── pyproject.toml
└── crawling/
    ├── skills/
    │   ├── skills_sh/
    │   │   ├── crawl_skills_sh.py
    │   │   ├── download_skills.py
    │   │   └── enrich_github_metadata_v2.py
    │   └── SkillsDirectory/
    │       ├── crawl_skillsdirectory.py
    │       └── download_skills.py
    └── security_infos/
        ├── openclaw/
        │   └── crawl_clawhub_security_to_sqlite.py
        └── skills_sh/
            ├── get_from_api.py
            └── scrape_skills_security.py
```

## Requirements

- Python `3.13+`
- [`uv`](https://github.com/astral-sh/uv) 用于环境和依赖管理
- `git`，用于下载技能关联仓库

## Setup

```bash
uv venv
uv sync
```

如果你不使用 `uv`，当前项目依赖很少，至少需要安装 `requests`。

## Data Pipelines

### 1. skills.sh 数据采集

#### `crawling/skills/skills_sh/crawl_skills_sh.py`

从 `skills.sh` 的 sitemap、搜索分片接口以及首页 RSC 数据中收集技能信息，并写入 `skills.db`。

- 输出数据库：`skills.db`
- 主要表：`skills`
- 特点：搜索分片 + sitemap 兜底，尽量提高覆盖率

运行示例：

```bash
cd crawling/skills/skills_sh
python crawl_skills_sh.py
```

#### `crawling/skills/skills_sh/download_skills.py`

从 `skills.db` 的 `skills` 表读取 `source` / `source_url`，提取 GitHub 仓库名，去重后并发下载。脚本会维护 `.downloaded_repos.txt` 进度文件，并自动跳过已经存在且远端匹配的仓库。

主要参数：

- `--db`：SQLite 数据库路径，默认 `skills.db`
- `--out`：仓库下载目录，默认 `downloaded_skills`
- `--limit`：仅处理前 N 个唯一仓库
- `--jobs`：并发克隆数，默认 `8`
- `--print-only`：只打印仓库列表，不执行克隆

运行示例：

```bash
cd crawling/skills/skills_sh
python download_skills.py --db skills.db --out downloaded_skills --jobs 8
```

#### `crawling/skills/skills_sh/enrich_github_metadata_v2.py`

读取 SQLite 中 `repo_marketplace_links.repository` 的 `owner/repo` 列表，通过 GitHub API 补充仓库元数据，并写入 `github_repo_metadata_v2`。

主要参数：

- `--db`：数据库路径，默认 `sqlite.db`
- `--token`：必填，GitHub API Token
- `--timeout`：单次请求超时，默认 `20`
- `--sleep-ms`：仓库之间的等待时间，默认 `120`
- `--limit`：最多处理多少个仓库，`0` 表示全部
- `--only-missing`：仅处理尚未写入 `github_repo_metadata_v2` 的仓库，默认开启
- `--all`：强制重跑全部仓库
- `--verbose`：打印详细进度

运行示例：

```bash
cd crawling/skills/skills_sh
python enrich_github_metadata_v2.py --db sqlite.db --token <github-token> --verbose
```

> [!IMPORTANT]
> 这个脚本不是直接从 `skills.db` 读取仓库，而是依赖数据库中的 `repo_marketplace_links` 表。旧 README 里这部分说明是过时的。

### 2. SkillsDirectory 数据采集

#### `crawling/skills/SkillsDirectory/crawl_skillsdirectory.py`

新增的目录采集脚本。它会调用 `https://www.skillsdirectory.com/api/skills`，分页抓取技能目录，并将结果 upsert 到 `skills_directory.db` 的 `skills` 表。

主要参数：

- `--db`：输出数据库路径，默认 `skills_directory.db`
- `--workers`：并发抓取页数，默认 `24`

运行示例：

```bash
cd crawling/skills/SkillsDirectory
python crawl_skillsdirectory.py --db skills_directory.db --workers 24
```

#### `crawling/skills/SkillsDirectory/download_skills.py`

新增的仓库下载脚本，逻辑与 `skills_sh/download_skills.py` 基本一致，适合配合 `SkillsDirectory` 生成的 `skills_directory.db` 使用。它支持从以下字段中解析仓库信息：

- GitHub URL，如 `https://github.com/owner/repo`
- SSH 地址，如 `git@github.com:owner/repo.git`
- `owner/repo`
- `skills.sh/owner/repo` 形式的链接

主要参数：

- `--db`：SQLite 数据库路径，默认 `skills.db`；用于 `SkillsDirectory` 时建议显式传入 `skills_directory.db`
- `--out`：仓库下载目录，默认 `downloaded_skills`
- `--limit`：仅处理前 N 个唯一仓库
- `--jobs`：并发克隆数，默认 `8`
- `--print-only`：只打印仓库列表，不执行克隆

运行示例：

```bash
cd crawling/skills/SkillsDirectory
python download_skills.py --db skills_directory.db --out downloaded_skills --jobs 8
```

> [!TIP]
> 由于这个脚本的默认参数仍是 `skills.db`，如果你在 `SkillsDirectory` 目录下运行，推荐总是显式指定 `--db skills_directory.db`，这样更安全也更清晰。

### 3. 安全审计数据采集

#### `crawling/security_infos/openclaw/crawl_clawhub_security_to_sqlite.py`

从 `pipeline.jsonl` 中读取技能，调用 ClawHub Convex API 的 `skills:getBySlug` 查询接口，抓取 VirusTotal 与 OpenClaw 安全扫描数据，并写入 SQLite。

主要参数：

- `--input`：输入 `pipeline.jsonl` 路径
- `--db`：输出数据库路径
- `--workers`：并发 worker 数
- `--timeout`：请求超时时间
- `--retries`：失败重试次数
- `--limit`：仅处理前 N 个技能
- `--resume`：跳过已抓取 slug
- `--commit-every`：每处理多少条记录提交一次事务，默认 `200`

运行示例：

```bash
cd crawling/security_infos/openclaw
python crawl_clawhub_security_to_sqlite.py --input pipeline.jsonl --db clawhub_security_scans.sqlite --workers 16
```

#### `crawling/security_infos/skills_sh/scrape_skills_security.py`

通过抓取 `skills.sh` 技能详情页和具体审计页 HTML，提取各扫描器状态，以及 `Socket` 审计中的详细 finding 信息。

主要参数：

- `--db`：数据库路径，默认 `04_03_2026.db`
- `--limit`：限制处理技能数
- `--offset`：从指定偏移开始
- `--timeout`：HTTP 超时秒数
- `--sleep`：每个技能后的等待时间
- `--commit-every`：每处理多少个技能提交一次事务，默认 `100`
- `--workers`：并发抓取数，默认 `100`

运行示例：

```bash
cd crawling/security_infos/skills_sh
python scrape_skills_security.py --db 04_03_2026.db --workers 50
```

#### `crawling/security_infos/skills_sh/get_from_api.py`

这是另一条较新的采集路径：直接读取 `skills.sh` 的 `/api/audits/{page}` 接口，把扫描器结果 JSON 落库到 `skill_security_scanner_results`，并补充 `result_json` / `scanner_json` 字段，适合保留原始接口返回。

主要参数：

- `--db`：数据库路径，默认 `04_03_2026.db`
- `--start-page`：起始页，默认 `1`
- `--max-pages`：最多抓取多少页
- `--timeout`：HTTP 超时秒数
- `--sleep`：分页请求间隔
- `--workers`：并发抓取数，默认 `100`
- `--commit-every`：每处理多少页提交一次事务，默认 `5`

运行示例：

```bash
cd crawling/security_infos/skills_sh
python get_from_api.py --db 04_03_2026.db --start-page 1 --max-pages 100
```

## Typical Workflow

如果你想从零开始构建一套可分析的数据集，可以按下面顺序执行：

1. 运行 `crawl_skills_sh.py` 或 `crawl_skillsdirectory.py` 获取技能基础列表。
2. 运行对应的 `download_skills.py`，把唯一 GitHub 仓库下载到本地。
3. 如果数据库中已有 `repo_marketplace_links`，运行 `enrich_github_metadata_v2.py` 补充仓库元数据。
4. 根据研究目标，选择 HTML 抓取版或 API 版安全采集脚本，将审计结果写入 SQLite。

## Skills Security Matrix Analyzer

仓库现在提供一个离线 CLI，用来直接分析本地 skill 语料目录中的声明层与实现层能力漂移。

运行示例：

```bash
python main.py \
  --skills-dir skills \
  --output-dir outputs/skills_security_matrix \
  --format json,csv \
  --case-study-skill 1password-hardened-1.0.0
```

核心行为：

- 解析 [`analyzer/security matrix.md`](/home/szk/code/OpenClaw-Proj/analyzer/security%20matrix.md) 为标准化分类表
- 发现本地 skill 目录并生成结构画像
- 仅从 `SKILL.md` 及其显式引用材料提取声明层证据
- 从代码、脚本、配置中提取实现层证据
- 计算声明/实现漂移，并把分类结果映射到矩阵中的 `主要风险` 与 `控制要求`
- 一次运行同时产出 JSON、CSV 与按 skill 切分的 case-study 文件

更详细的输入、输出和证据语义说明见 [`docs/analyzer/skills-security-matrix-analyzer.md`](/home/szk/code/OpenClaw-Proj/docs/analyzer/skills-security-matrix-analyzer.md)。

## Notes

- 仓库里当前提交了示例数据库文件：`crawling/skills/skills_sh/skills.db` 与 `crawling/skills/SkillsDirectory/skills_directory.db`。进行大规模实验时，建议使用你自己的副本，避免污染原始样本。
- `main.py` 目前不是正式 CLI 入口；如果后续要对外发布为工具，建议把 `crawling/` 下的能力统一封装为可复用命令。
