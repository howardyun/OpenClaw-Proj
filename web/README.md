# Web Viewer

这个目录提供一个最小的 Flask 页面，用来触发单个 `skills.sh` skill 的扫描，并展示生成的 case 结果。

## 运行

在仓库根目录执行：

```bash
uv run flask --app web.app run --debug
```

默认配置会：

- 读取 `crawling/skills/skills_sh/skills.db`
- 从 `skills/skill_sh_test` 查找本地 repo
- 把扫描结果输出到 `outputs/web_runs`

## 页面能力

- `GET /`：输入 `skill_id`
- `POST /scan`：同步执行单 skill 扫描
- `GET /results/<run_id>/<skill_key>`：查看结果详情

## 可调配置

应用支持通过 `create_app({...})` 覆盖以下配置：

- `SCAN_PYTHON_BIN`
- `SCAN_SCRIPT_PATH`
- `SCAN_DB_PATH`
- `SCAN_REPOS_ROOT`
- `SCAN_OUTPUT_ROOT`
- `SCAN_MATRIX_PATH`
- `SCAN_LLM_REVIEW_MODE`

如果后续需要任务队列或异步扫描，建议在 `web/services/scan_runner.py` 上继续扩展，而不是把流程直接写进路由。
