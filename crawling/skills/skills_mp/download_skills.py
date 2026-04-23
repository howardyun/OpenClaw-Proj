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

TMP_ROOT = Path(r"D:\tmp")   # 临时目录

lock = threading.Lock()
progress = 0



# repo 提取

def extract_repo_from_url(url: str) -> str | None:
    if not url:
        return None
    m = re.match(r"https://github\.com/([^/]+/[^/]+)", url)
    return m.group(1) if m else None



# 读取 repo

def load_repos(db_path: Path) -> Set[str]:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT github_url FROM skills")

    repos = set()
    for (url,) in cur.fetchall():
        repo = extract_repo_from_url(url)
        if repo:
            repos.add(repo)

    conn.close()
    return repos



# repo -> skill 映射

def load_skill_names(db_path: Path) -> Dict[str, Set[str]]:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT github_url, name FROM skills")

    repo_skills: Dict[str, Set[str]] = {}

    for url, name in cur.fetchall():
        repo = extract_repo_from_url(url)
        if repo:
            repo_skills.setdefault(repo, set()).add(name)

    conn.close()
    return repo_skills



# failed

def load_failed() -> Dict[str, str]:
    if not Path(FAILED_JSON).exists():
        return {}

    with open(FAILED_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)

    return {x["repo"]: x.get("error", "") for x in data}


def save_failed_atomic(failed_dict: Dict[str, str]):
    tmp = FAILED_JSON + ".tmp"
    data = [{"repo": k, "error": v} for k, v in failed_dict.items()]

    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    os.replace(tmp, FAILED_JSON)



# 已完成 repo

def load_done_repos(output_dir: Path) -> Set[str]:
    done = set()

    if not output_dir.exists():
        return done

    for d in output_dir.iterdir():
        if d.is_dir() and (d / ".done").exists():
            done.add(d.name.replace("__", "/"))

    return done



# git clone

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

        if "authentication" in err or "permission denied" in err:
            raise RuntimeError("PRIVATE_OR_NO_PERMISSION")
        if "not found" in err:
            raise RuntimeError("REPO_NOT_FOUND")

        raise RuntimeError(err)

    return target



# 找 SKILL.md

def find_skill_folders(repo_dir: Path):
    for root, _, files in os.walk(repo_dir):
        if "SKILL.md" in files:
            yield Path(root)



# 提取 skill

def extract_skills(repo_dir: Path, out_dir: Path, repo: str):
    skill_dirs = list(find_skill_folders(repo_dir))
    if not skill_dirs:
        return False

    repo_out = out_dir / repo.replace("/", "__")
    repo_out.mkdir(parents=True, exist_ok=True)

    for s in skill_dirs:
        name = s.name
        target = repo_out / name

        if target.exists():
            shutil.rmtree(target, ignore_errors=True)

        shutil.copytree(s, target)

    return True



# 清理无效 skill

def cleanup_skills(repo: str, out_dir: Path, repo_skill_map: Dict[str, Set[str]]):
    repo_out = out_dir / repo.replace("/", "__")

    if not repo_out.exists():
        return

    valid = repo_skill_map.get(repo, set())

    for d in repo_out.iterdir():
        if not d.is_dir():
            continue

        if d.name in [".done", ".cleaned"]:
            continue

        if d.name not in valid:
            shutil.rmtree(d, ignore_errors=True)



# 单 repo

def process_repo(repo: str, out_dir: Path, total: int,
                 failed_dict: Dict[str, str],
                 repo_skill_map: Dict[str, Set[str]]):

    global progress

    tmp_dir = None

    try:
        tmp_dir = TMP_ROOT / repo.replace("/", "__")
        tmp_dir.mkdir(parents=True, exist_ok=True)

        repo_path = clone_repo(repo, tmp_dir)
        extract_skills(repo_path, out_dir, repo)

        repo_out = out_dir / repo.replace("/", "__")
        repo_out.mkdir(parents=True, exist_ok=True)

        done_flag = repo_out / ".done"
        cleaned_flag = repo_out / ".cleaned"


        # done

        done_flag.touch()


        # cleanup only once

        if not cleaned_flag.exists():
            cleanup_skills(repo, out_dir, repo_skill_map)
            cleaned_flag.touch()

        with lock:
            progress += 1
            print(f"[{progress}/{total}] [OK] {repo}")

            failed_dict.pop(repo, None)
            save_failed_atomic(failed_dict)

    except Exception as e:
        with lock:
            progress += 1
            print(f"[{progress}/{total}] [FAIL] {repo}: {e}")
            failed_dict[repo] = str(e)
            save_failed_atomic(failed_dict)

    finally:
        if tmp_dir and tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)



# main

def main():
    db_repos = load_repos(Path(DB_PATH))
    failed_dict = load_failed()
    repo_skill_map = load_skill_names(Path(DB_PATH))

    out_dir = Path(OUTPUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)

    done = load_done_repos(out_dir)

    repos = list((set(db_repos) | set(failed_dict.keys())) - done)

    total = len(repos)

    print(f"TOTAL: {total}")
    print("START")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = [
            ex.submit(process_repo, r, out_dir, total, failed_dict, repo_skill_map)
            for r in repos
        ]

        for _ in as_completed(futures):
            pass

    print("DONE")


if __name__ == "__main__":
    main()