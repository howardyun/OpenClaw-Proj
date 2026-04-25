import os
import re
import json
import shutil
import sqlite3
import subprocess
from pathlib import Path
from typing import Dict, Set
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

#  配置
DB_PATH = "all_skills.db"
OUTPUT_DIR = "skills_output"
FAILED_JSON = "failed_repos.json"
# 并发数
MAX_WORKERS = 6
# 临时文件目录
TMP_ROOT = Path(r"D:\tmp")

VALID_PLAT = ("skills.sh", "skillsmp", "skillsdirectory")

lock = threading.Lock()
progress = 0


#  repo 提取
def extract_repo(url: str) -> str | None:
    if not url:
        return None
    m = re.match(r"https://github\.com/([^/]+/[^/]+)", url)
    return m.group(1) if m else None


#  读取 repo
def load_repos(db_path: Path) -> Set[str]:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
        SELECT repo_url
        FROM all_skills
        WHERE source_plat IN (?, ?, ?)
    """, VALID_PLAT)

    repos = set()
    for (url,) in cur.fetchall():
        repo = extract_repo(url)
        if repo:
            repos.add(repo)

    conn.close()
    return repos


#  repo -> skill 映射
def load_repo_skills(db_path: Path) -> Dict[str, Set[str]]:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
        SELECT repo_url, name
        FROM all_skills
        WHERE source_plat IN (?, ?, ?)
    """, VALID_PLAT)

    repo_map: Dict[str, Set[str]] = {}

    for url, name in cur.fetchall():
        repo = extract_repo(url)
        if repo:
            repo_map.setdefault(repo, set()).add(name)

    conn.close()
    return repo_map


#  failed
def load_failed() -> Dict[str, str]:
    if not Path(FAILED_JSON).exists():
        return {}

    with open(FAILED_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)

    return {x["repo"]: x.get("error", "") for x in data}


def save_failed_atomic(failed: Dict[str, str]):
    tmp = FAILED_JSON + ".tmp"
    data = [{"repo": k, "error": v} for k, v in failed.items()]

    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    os.replace(tmp, FAILED_JSON)


# done / clean
def load_done_repos(output_dir: Path) -> Set[str]:
    done = set()
    if not output_dir.exists():
        return done

    for d in output_dir.iterdir():
        if d.is_dir() and (d / ".clean").exists():
            done.add(d.name.replace("__", "/"))

    return done


#  git clone
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

    r = subprocess.run(cmd, capture_output=True, env=env)

    if r.returncode != 0:
        err = r.stderr.decode(errors="ignore").lower()

        if "not found" in err:
            raise RuntimeError("REPO_NOT_FOUND")
        if "authentication" in err or "permission denied" in err:
            raise RuntimeError("PRIVATE_REPO")

        raise RuntimeError(err)

    return target


#  找 SKILL
def find_skill_dirs(repo_dir: Path):
    for root, _, files in os.walk(repo_dir):
        if "SKILL.md" in files:
            yield Path(root)


# = 提取
def extract_skills(repo_dir: Path, out_dir: Path, repo: str):
    dirs = list(find_skill_dirs(repo_dir))
    if not dirs:
        return False

    repo_out = out_dir / repo.replace("/", "__")
    repo_out.mkdir(parents=True, exist_ok=True)

    for d in dirs:
        target = repo_out / d.name

        if target.exists():
            shutil.rmtree(target, ignore_errors=True)

        shutil.copytree(d, target)

    return True


#  清理
def cleanup(repo: str, out_dir: Path, repo_map: Dict[str, Set[str]]):
    repo_out = out_dir / repo.replace("/", "__")
    if not repo_out.exists():
        return

    valid = repo_map.get(repo, set())

    for d in repo_out.iterdir():
        if not d.is_dir():
            continue

        if d.name not in valid:
            shutil.rmtree(d, ignore_errors=True)


#  worker
def process_repo(repo: str, out_dir: Path, total: int,
                 failed: Dict[str, str],
                 repo_map: Dict[str, Set[str]]):

    global progress
    tmp_dir = None

    try:
        tmp_dir = TMP_ROOT / repo.replace("/", "__")
        tmp_dir.mkdir(parents=True, exist_ok=True)

        # 1. clone
        repo_path = clone_repo(repo, tmp_dir)

        # 2. extract
        extract_skills(repo_path, out_dir, repo)

        repo_out = out_dir / repo.replace("/", "__")
        repo_out.mkdir(parents=True, exist_ok=True)

        # 3. cleanup
        cleanup(repo, out_dir, repo_map)

        # 4. clean 标记
        (repo_out / ".clean").touch()

        with lock:
            progress += 1
            print(f"[{progress}/{total}] OK {repo}")

            failed.pop(repo, None)
            save_failed_atomic(failed)

    except Exception as e:
        with lock:
            progress += 1
            print(f"[{progress}/{total}] FAIL {repo}: {e}")
            failed[repo] = str(e)
            save_failed_atomic(failed)

    finally:
        if tmp_dir and tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)


#  main
def main():
    db = Path(DB_PATH)

    repos = load_repos(db)
    repo_map = load_repo_skills(db)
    failed = load_failed()

    out_dir = Path(OUTPUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)

    # ✅ 已完成（clean）
    done = load_done_repos(out_dir)

    # ✅ 待处理 = 全量 - 已完成
    todo = list((repos | set(failed.keys())) - done)

    total = len(todo)

    print(f"TOTAL: {total}")
    print("START")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = [
            ex.submit(process_repo, r, out_dir, total, failed, repo_map)
            for r in todo
        ]

        for _ in as_completed(futures):
            pass

    print("DONE")


if __name__ == "__main__":
    main()