#!/usr/bin/env python3
from __future__ import annotations

import re
import sqlite3
from pathlib import Path


ROOT = Path("crawling/skills")
ALL_SKILLS_DB = ROOT / "all_skills/all_skills.db"
OUTPUT_DB = ROOT / "all_skills/to_download.db"

SKILLS_SH_DB = ROOT / "skills_sh/skills.db"
SKILLS_DIRECTORY_DB = ROOT / "SkillsDirectory/skills_directory.db"
SKILLS_MP_DB = ROOT / "skills_mp/skillsmp.db"
CLAWHUB_DB = ROOT / "clawhub/clawHub.db"

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


def extract_github_repo(*candidates: str | None) -> str | None:
    for raw in candidates:
        text = (raw or "").strip()
        if not text or text == "0":
            continue

        match = GITHUB_URL_RE.search(text)
        if match:
            return normalize_repo(match.group("owner"), match.group("repo"))

        match = SKILLS_SH_RE.search(text)
        if match:
            return normalize_repo(match.group("owner"), match.group("repo"))

        match = OWNER_REPO_RE.match(text)
        if match:
            return normalize_repo(match.group("owner"), match.group("repo"))

    return None


def load_existing_github_repos() -> set[str]:
    repos: set[str] = set()

    def read_rows(db_path: Path, query: str) -> None:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            for row in conn.execute(query):
                repo = extract_github_repo(*[row[key] for key in row.keys()])
                if repo:
                    repos.add(repo)
        finally:
            conn.close()

    read_rows(SKILLS_SH_DB, "SELECT source, source_url FROM skills")
    read_rows(SKILLS_DIRECTORY_DB, "SELECT source, source_url FROM skills")
    read_rows(SKILLS_MP_DB, "SELECT github_url, name FROM skills")
    return repos


def load_existing_clawhub_slugs() -> set[str]:
    conn = sqlite3.connect(CLAWHUB_DB)
    try:
        return {
            row[0].strip().lower()
            for row in conn.execute("SELECT slug FROM skills WHERE slug IS NOT NULL AND TRIM(slug) != ''")
        }
    finally:
        conn.close()


def build_output_db(existing_repos: set[str], existing_clawhub_slugs: set[str]) -> dict[str, int]:
    if OUTPUT_DB.exists():
        OUTPUT_DB.unlink()

    source = sqlite3.connect(ALL_SKILLS_DB)
    source.row_factory = sqlite3.Row
    target = sqlite3.connect(OUTPUT_DB)

    try:
        target.execute(
            """
            CREATE TABLE all_skills (
                name TEXT,
                skill_star_count INTEGER,
                skill_fork_count INTEGER,
                skill_download_count INTEGER,
                skill_install_count INTEGER,
                developer TEXT,
                developer_is_org TEXT,
                repo_url TEXT,
                developer_github_stars INTEGER,
                source_plat TEXT,
                crawled_at TEXT,
                UNIQUE(name, repo_url)
            )
            """
        )

        inserted = 0
        skipped_existing = 0
        total = 0

        for row in source.execute("SELECT * FROM all_skills"):
            total += 1
            source_plat = (row["source_plat"] or "").strip().lower()
            name = (row["name"] or "").strip().lower()
            repo = extract_github_repo(row["repo_url"])

            already_seen = False
            if repo and repo in existing_repos:
                already_seen = True
            elif source_plat == "clawhub" and name and name in existing_clawhub_slugs:
                already_seen = True

            if already_seen:
                skipped_existing += 1
                continue

            target.execute(
                """
                INSERT INTO all_skills (
                    name,
                    skill_star_count,
                    skill_fork_count,
                    skill_download_count,
                    skill_install_count,
                    developer,
                    developer_is_org,
                    repo_url,
                    developer_github_stars,
                    source_plat,
                    crawled_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                tuple(row),
            )
            inserted += 1

        target.execute("CREATE INDEX idx_all_skills_source_plat ON all_skills (source_plat)")
        target.execute("CREATE INDEX idx_all_skills_repo_url ON all_skills (repo_url)")
        target.commit()

        return {
            "total": total,
            "inserted": inserted,
            "skipped_existing": skipped_existing,
        }
    finally:
        source.close()
        target.close()


def main() -> None:
    existing_repos = load_existing_github_repos()
    existing_clawhub_slugs = load_existing_clawhub_slugs()
    stats = build_output_db(existing_repos, existing_clawhub_slugs)

    print(f"Existing GitHub repos from old DBs: {len(existing_repos)}")
    print(f"Existing Clawhub slugs from old DBs: {len(existing_clawhub_slugs)}")
    print(f"All skills rows scanned:           {stats['total']}")
    print(f"Rows skipped as already crawled:   {stats['skipped_existing']}")
    print(f"Rows written to {OUTPUT_DB}: {stats['inserted']}")


if __name__ == "__main__":
    main()
