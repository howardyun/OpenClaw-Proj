#!/usr/bin/env python3
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import re
import sqlite3
import subprocess
import shutil
from pathlib import Path
from typing import Iterable

PROGRESS_FILE_NAME = ".downloaded_repos.txt"

GITHUB_URL_RE = re.compile(
    r"(?:https?://|git@)github\.com[:/](?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+?)(?:\.git)?(?:/|$)",
    re.IGNORECASE,
)
OWNER_REPO_RE = re.compile(r"^(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+)$")
SKILLS_SH_RE = re.compile(
    r"https?://(?:www\.)?skills\.sh/(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+)(?:/|$)",
    re.IGNORECASE,
)


def normalize_repo(owner: str, repo: str) -> str:
    return f"{owner.lower()}/{repo.lower()}"


def extract_github_repo(source: str | None, source_url: str | None) -> str | None:
    candidates = [source_url or "", source or ""]
    for text in candidates:
        s = text.strip()
        if not s:
            continue

        match = GITHUB_URL_RE.search(s)
        if match:
            return normalize_repo(match.group("owner"), match.group("repo"))

        match = SKILLS_SH_RE.search(s)
        if match:
            return normalize_repo(match.group("owner"), match.group("repo"))

        match = OWNER_REPO_RE.match(s)
        if match:
            return normalize_repo(match.group("owner"), match.group("repo"))

    return None


def load_unique_repos(db_path: Path, limit: int | None = None) -> list[str]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    repos: set[str] = set()
    query = "SELECT source, source_url FROM skills"
    for row in conn.execute(query):
        repo = extract_github_repo(row["source"], row["source_url"])
        if repo:
            repos.add(repo)
            if limit is not None and len(repos) >= limit:
                break

    conn.close()
    return sorted(repos)


def is_valid_repo_dir(target: Path, repo: str) -> bool:
    git_dir = target / ".git"
    if not git_dir.exists():
        return False
    proc = subprocess.run(
        ["git", "-C", str(target), "config", "--get", "remote.origin.url"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        return False
    remote = proc.stdout.strip().lower()
    expected = f"github.com/{repo.lower()}"
    return expected in remote


def load_progress(progress_file: Path) -> set[str]:
    if not progress_file.exists():
        return set()
    lines = progress_file.read_text(encoding="utf-8", errors="replace").splitlines()
    return {line.strip().lower() for line in lines if line.strip()}


def save_progress(progress_file: Path, repos: set[str]) -> None:
    ordered = sorted(repos)
    content = "".join(f"{repo}\n" for repo in ordered)
    progress_file.write_text(content, encoding="utf-8")


def append_progress(progress_file: Path, repo: str) -> None:
    with progress_file.open("a", encoding="utf-8") as f:
        f.write(f"{repo}\n")


def clone_repo(repo: str, output_dir: Path, skip_existing: bool = True) -> tuple[str, str]:
    target = output_dir / repo.replace("/", "__")
    if target.exists():
        if skip_existing and is_valid_repo_dir(target, repo):
            return ("skipped", repo)
        shutil.rmtree(target, ignore_errors=True)

    cmd = ["git", "clone", "--depth", "3", f"https://github.com/{repo}.git", str(target)]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode == 0:
        return ("downloaded", repo)

    if target.exists():
        # Clean incomplete clone directory on failure.
        shutil.rmtree(target, ignore_errors=True)
    return ("failed", f"{repo} -> {proc.stderr.strip() or proc.stdout.strip()}")


def download_repos(repos: Iterable[str], output_dir: Path, jobs: int = 8) -> tuple[int, int, list[str]]:
    downloaded = 0
    skipped = 0
    failures: list[str] = []
    progress_file = output_dir / PROGRESS_FILE_NAME
    all_repos = list(repos)
    completed = load_progress(progress_file)
    merged_completed = set(completed)
    for repo in all_repos:
        target = output_dir / repo.replace("/", "__")
        if target.exists() and is_valid_repo_dir(target, repo):
            merged_completed.add(repo.lower())
    if merged_completed != completed:
        save_progress(progress_file, merged_completed)
    completed = merged_completed

    repo_list: list[str] = []
    for repo in all_repos:
        target = output_dir / repo.replace("/", "__")
        if repo.lower() in completed and target.exists() and is_valid_repo_dir(target, repo):
            skipped += 1
            continue
        repo_list.append(repo)

    with ThreadPoolExecutor(max_workers=max(1, jobs)) as executor:
        future_to_repo = {executor.submit(clone_repo, repo, output_dir): repo for repo in repo_list}
        for future in as_completed(future_to_repo):
            repo = future_to_repo[future]
            try:
                status, detail = future.result()
            except Exception as exc:
                failures.append(f"{repo} -> {exc}")
                print(f"[FAIL]  {repo} -> {exc}")
                continue

            if status == "downloaded":
                downloaded += 1
                append_progress(progress_file, repo)
                print(f"[OK]    {detail}")
            elif status == "skipped":
                skipped += 1
                if repo.lower() not in completed:
                    append_progress(progress_file, repo)
                    completed.add(repo.lower())
                print(f"[SKIP]  {detail}")
            else:
                failures.append(detail)
                print(f"[FAIL]  {detail}")

    return downloaded, skipped, failures


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Read skills.db, extract GitHub repositories from source/source_url, "
            "deduplicate, and download each repo once."
        )
    )
    parser.add_argument("--db", default="skills.db", help="Path to SQLite DB (default: skills.db)")
    parser.add_argument("--out", default="downloaded_skills", help="Output directory")
    parser.add_argument("--limit", type=int, default=None, help="Only process first N unique repos")
    parser.add_argument("--jobs", type=int, default=8, help="Parallel clone workers (default: 8)")
    parser.add_argument("--print-only", action="store_true", help="Only print unique repos, do not clone")
    args = parser.parse_args()

    db_path = Path(args.db)
    out_dir = Path(args.out)

    if not db_path.exists():
        raise FileNotFoundError(f"DB not found: {db_path}")

    repos = load_unique_repos(db_path, args.limit)
    print(f"Unique GitHub repos found: {len(repos)}")

    if args.print_only:
        for repo in repos:
            print(repo)
        return

    out_dir.mkdir(parents=True, exist_ok=True)
    downloaded, skipped, failures = download_repos(repos, out_dir, jobs=args.jobs)

    print("\nSummary")
    print(f"  downloaded: {downloaded}")
    print(f"  skipped:    {skipped}")
    print(f"  failed:     {len(failures)}")

    if failures:
        print("\nFailures:")
        for item in failures:
            print(f"  - {item}")


if __name__ == "__main__":
    main()
