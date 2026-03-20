#!/usr/bin/env python3
import argparse
import re
import sqlite3
import subprocess
import shutil
from pathlib import Path
from typing import Iterable


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


def clone_repo(repo: str, output_dir: Path, skip_existing: bool = True) -> tuple[str, str]:
    target = output_dir / repo.replace("/", "__")
    if skip_existing and target.exists():
        return ("skipped", repo)

    cmd = ["git", "clone", "--depth", "3", f"https://github.com/{repo}.git", str(target)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode == 0:
        return ("downloaded", repo)

    if target.exists():
        # Clean incomplete clone directory on failure.
        shutil.rmtree(target, ignore_errors=True)
    return ("failed", f"{repo} -> {proc.stderr.strip() or proc.stdout.strip()}")


def download_repos(repos: Iterable[str], output_dir: Path) -> tuple[int, int, list[str]]:
    downloaded = 0
    skipped = 0
    failures: list[str] = []

    for repo in repos:
        status, detail = clone_repo(repo, output_dir)
        if status == "downloaded":
            downloaded += 1
            print(f"[OK]    {detail}")
        elif status == "skipped":
            skipped += 1
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
    downloaded, skipped, failures = download_repos(repos, out_dir)

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
