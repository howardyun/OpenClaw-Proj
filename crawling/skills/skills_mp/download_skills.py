import os
import re
import json
import shutil
import sqlite3
import subprocess
import tempfile
from pathlib import Path
from typing import Set, Dict
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


# 原子写入
def save_failed_atomic(failed_dict: Dict[str, str]):
    tmp_file = FAILED_JSON + ".tmp"
    data = [{"repo": k, "error": v} for k, v in failed_dict.items()]

    with open(tmp_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    os.replace(tmp_file, FAILED_JSON)


# 已完成 repo
def load_done_repos(output_dir: Path) -> Set[str]:
    done_repos = set()

    if not output_dir.exists():
        return done_repos

    for repo_dir in output_dir.iterdir():
        if not repo_dir.is_dir():
            continue

        done_flag = repo_dir / ".done"
        if done_flag.exists():
            repo = repo_dir.name.replace("__", "/")
            done_repos.add(repo)

    return done_repos


# clone repo（禁用交互）
def clone_repo(repo: str, tmp_dir: Path) -> Path:
    target = tmp_dir / repo.replace("/", "__")

    cmd = [
        "git",
        "-c", "credential.helper=",
        "-c", "core.askPass=",
        "clone",
        f"https://github.com/{repo}.git",
        str(target),
    ]

    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"

    result = subprocess.run(
        cmd,
        capture_output=True,
        env=env
    )

    if result.returncode != 0:
        err = result.stderr.decode(errors="ignore").lower()

        if "authentication" in err or "permission denied" in err:
            raise RuntimeError("PRIVATE_OR_NO_PERMISSION")

        if "not found" in err:
            raise RuntimeError("REPO_NOT_FOUND")

        raise RuntimeError(err)

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


# 单任务（每个 repo 独立临时目录 立即释放）
def process_repo(repo: str, out_dir: Path,
                 total: int, failed_dict: Dict[str, str]):
    global progress

    tmp_dir = None

    try:
        # 每个 repo 独立临时目录
        tmp_dir = Path(tempfile.mkdtemp())

        repo_path = clone_repo(repo, tmp_dir)
        extract_skills(repo_path, out_dir, repo)

        repo_out = out_dir / repo.replace("/", "__")
        repo_out.mkdir(parents=True, exist_ok=True)
        (repo_out / ".done").touch()

        with lock:
            progress += 1
            print(f"[{progress}/{total}] [OK] {repo}")

            if repo in failed_dict:
                del failed_dict[repo]
                save_failed_atomic(failed_dict)

    except Exception as e:
        err_msg = str(e)

        with lock:
            progress += 1

            if err_msg == "PRIVATE_OR_NO_PERMISSION":
                print(f"[{progress}/{total}] [SKIP_PRIVATE] {repo}")
                failed_dict.pop(repo, None)
                save_failed_atomic(failed_dict)
                return

            if err_msg == "REPO_NOT_FOUND":
                print(f"[{progress}/{total}] [NOT_FOUND] {repo}")
                failed_dict.pop(repo, None)
                save_failed_atomic(failed_dict)
                return

            print(f"[{progress}/{total}] [FAIL] {repo}")
            failed_dict[repo] = err_msg
            save_failed_atomic(failed_dict)

    finally:
        # 每个 repo 处理完立即删除临时目录
        if tmp_dir and tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)


# 主函数
def main():
    db_repos = load_repos(Path(DB_PATH))
    failed_dict = load_failed()

    out_dir = Path(OUTPUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)

    done_repos = load_done_repos(out_dir)

    all_repos = set(db_repos) | set(failed_dict.keys())
    repos = list(all_repos - done_repos)

    total = len(repos)

    print(f"\nTOTAL TASKS: {total}")
    print(f"ALREADY DONE: {len(done_repos)}")
    print(f"FAILED RETRY: {len(failed_dict)}")
    print(f"MAX WORKERS: {MAX_WORKERS}")
    print("\n=== START ===\n")

    if total == 0:
        print("Nothing to do.")
        return

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [
            executor.submit(process_repo, repo, out_dir, total, failed_dict)
            for repo in repos
        ]

        for _ in as_completed(futures):
            pass

    print(f"\nFAILED LEFT: {len(failed_dict)}")
    print("ALL DONE")


if __name__ == "__main__":
    main()