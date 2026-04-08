#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from crawl_skills_sh import refresh_skills_db
from download_skills import download_repos, load_unique_repos


def compute_new_repos(before_repos: list[str], after_repos: list[str]) -> list[str]:
    before_set = {repo.lower() for repo in before_repos}
    return [repo for repo in after_repos if repo.lower() not in before_set]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Refresh skills.db from skills.sh, compare repository sets before/after, "
            "and download only newly discovered GitHub repositories."
        )
    )
    parser.add_argument("--db", default="skills.db", help="Path to SQLite DB (default: skills.db)")
    parser.add_argument("--out", default="downloaded_skills", help="Output directory")
    parser.add_argument("--jobs", type=int, default=8, help="Parallel clone workers (default: 8)")
    parser.add_argument(
        "--limit-new-repos",
        type=int,
        default=None,
        help="Only download the first N newly discovered repos",
    )
    parser.add_argument(
        "--print-only",
        action="store_true",
        help="Refresh DB and print newly discovered repos without cloning",
    )
    parser.add_argument(
        "--keep-going",
        action="store_true",
        help="Keep processing all new repos and summarize failures instead of raising",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    db_path = Path(args.db)
    out_dir = Path(args.out)

    if not db_path.exists():
        raise FileNotFoundError(f"DB not found: {db_path}")

    before_repos = load_unique_repos(db_path)
    print(f"Unique GitHub repos before refresh: {len(before_repos)}")

    refresh_stats = refresh_skills_db(str(db_path))

    after_repos = load_unique_repos(db_path)
    print(f"Unique GitHub repos after refresh:  {len(after_repos)}")

    new_repos = compute_new_repos(before_repos, after_repos)
    total_new_repos = len(new_repos)
    print(f"New GitHub repos discovered:       {total_new_repos}")

    if args.limit_new_repos is not None:
        new_repos = new_repos[: max(0, args.limit_new_repos)]
        print(f"New GitHub repos selected:         {len(new_repos)}")

    print("\nRefresh Summary")
    print(f"  sitemap skills: {refresh_stats['sitemap_count']}")
    print(f"  search unique:  {refresh_stats['search_unique_count']}")
    print(f"  upserted:       {refresh_stats['upserted_skills']}")
    coverage_total = refresh_stats["coverage_total"]
    if coverage_total:
        print(f"  coverage total: {coverage_total}")

    if args.print_only:
        if new_repos:
            print("\nNew repos:")
            for repo in new_repos:
                print(repo)
        return

    if not new_repos:
        print("\nDownload Summary")
        print("  downloaded: 0")
        print("  skipped:    0")
        print("  failed:     0")
        return

    out_dir.mkdir(parents=True, exist_ok=True)
    downloaded, skipped, failures = download_repos(new_repos, out_dir, jobs=args.jobs)

    print("\nDownload Summary")
    print(f"  downloaded: {downloaded}")
    print(f"  skipped:    {skipped}")
    print(f"  failed:     {len(failures)}")

    if failures:
        print("\nFailures:")
        for item in failures:
            print(f"  - {item}")
        if not args.keep_going:
            raise RuntimeError(f"Failed to download {len(failures)} repositories.")


if __name__ == "__main__":
    main()
