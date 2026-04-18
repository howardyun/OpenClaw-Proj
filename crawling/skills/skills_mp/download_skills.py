import os
import re
import json
import shutil
import sqlite3
import subprocess
import tempfile
from pathlib import Path
from typing import List, Set, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading


# 配置
DB_PATH = "skillsmp.db"
OUTPUT_DIR = "skills_output"
FAILED_JSON = "failed_repos.json"
MAX_WORKERS = 6

lock = threading.Lock()
progress = 0



# 提取 repo
def extract_repo_from_url(url: str) -> str | None:
    if not url:
        return None
    m = re.match(r"https://github\.com/([^/]+/[^/]+)", url)
    return m.group(1) if m else None



# 读取 repo（数据库）
def load_repos(db_path: Path) -> Set[str]:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("SELECT github_url FROM skills")

    repos: Set[str] = set()
    for (url,) in cur.fetchall():
        repo = extract_repo_from_url(url)
        if repo:
            repos.add(repo)

    conn.close()
    return repos



# 读取失败 repo
def load_failed() -> Dict[str, str]:
    if not Path(FAILED_JSON).exists():
        return {}

    with open(FAILED_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)

    return {item["repo"]: item.get("error", "") for item in data}



# 保存失败 repo
def save_failed(failed_dict: Dict[str, str]):
    data = [{"repo": k, "error": v} for k, v in failed_dict.items()]

    with open(FAILED_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)



# clone repo（完整）
def clone_repo(repo: str, tmp_dir: Path) -> Path:
    target = tmp_dir / repo.replace("/", "__")

    cmd = [
        "git",
        "clone",
        f"https://github.com/{repo}.git",
        str(target),
    ]

    result = subprocess.run(cmd, capture_output=True)

    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode(errors="ignore"))

    return target



# 找 skill
def find_skill_folders(repo_dir: Path):
    for root, _, files in os.walk(repo_dir):
        if "SKILL.md" in files:
            yield Path(root)



# 提取 skill
def extract_skills(repo_dir: Path, output_dir: Path, repo: str):
    skill_dirs = list(find_skill_folders(repo_dir))
    if not skill_dirs:
        return False

    repo_out = output_dir / repo.replace("/", "__")
    repo_out.mkdir(parents=True, exist_ok=True)

    for skill_dir in skill_dirs:
        skill_name = skill_dir.name
        target = repo_out / skill_name

        if target.exists():
            shutil.rmtree(target, ignore_errors=True)

        shutil.copytree(skill_dir, target)

    return True



# 单任务
def process_repo(repo: str, tmp_dir: Path, out_dir: Path,
                 total: int, failed_dict: Dict[str, str]):
    global progress

    repo_out = out_dir / repo.replace("/", "__")
    done_flag = repo_out / ".done"

    # ✅ 强一致跳过
    if done_flag.exists():
        with lock:
            progress += 1
            print(f"[{progress}/{total}] [SKIP] {repo}")
        return

    try:
        repo_path = clone_repo(repo, tmp_dir)
        ok = extract_skills(repo_path, out_dir, repo)

        # 创建 done 标记
        repo_out.mkdir(parents=True, exist_ok=True)
        done_flag.touch()

        with lock:
            progress += 1
            print(f"[{progress}/{total}] [OK] {repo}")

        # ✅ 成功后从失败列表移除
        with lock:
            if repo in failed_dict:
                del failed_dict[repo]

    except Exception as e:
        with lock:
            progress += 1
            print(f"[{progress}/{total}] [FAIL] {repo}")

            failed_dict[repo] = str(e)



# 主函数
def main():
    db_repos = load_repos(Path(DB_PATH))
    failed_dict = load_failed()

    # ✅ 合并任务：优先失败的
    repos = list(set(db_repos) | set(failed_dict.keys()))
    total = len(repos)

    out_dir = Path(OUTPUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\nTOTAL TASKS: {total}")
    print(f"FAILED RETRY: {len(failed_dict)}")
    print(f"MAX WORKERS: {MAX_WORKERS}")
    print("\n=== START ===\n")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = [
                executor.submit(process_repo, repo, tmp_dir, out_dir, total, failed_dict)
                for repo in repos
            ]

            for _ in as_completed(futures):
                pass

    # 保存失败
    save_failed(failed_dict)

    print(f"\nFAILED LEFT: {len(failed_dict)}")
    print("ALL DONE")


if __name__ == "__main__":
    main()