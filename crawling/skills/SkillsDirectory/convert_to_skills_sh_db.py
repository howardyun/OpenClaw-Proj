#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sqlite3
from pathlib import Path

GITHUB_URL_RE = re.compile(
    r"(?:https?://|git@)github\.com[:/](?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+?)(?:\.git)?(?:/|$)",
    re.IGNORECASE,
)
OWNER_REPO_RE = re.compile(r"^(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+)$")
SKILLS_SH_RE = re.compile(
    r"https?://(?:www\.)?skills\.sh/(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+)(?:/|$)",
    re.IGNORECASE,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Convert crawling/skills/SkillsDirectory/skills_directory.db "
            "into the same record format used by crawling/skills/skills_sh/skills.db."
        )
    )
    parser.add_argument(
        "--input",
        default="crawling/skills/SkillsDirectory/skills_directory.db",
        help="Source SQLite DB path.",
    )
    parser.add_argument(
        "--output",
        default="crawling/skills/SkillsDirectory/skills.db",
        help="Output SQLite DB path.",
    )
    parser.add_argument(
        "--source-url-base",
        default="https://skills.sh",
        help="Base URL used to rewrite source_url in the target DB.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite output DB if it already exists.",
    )
    return parser


def normalize_repo(owner: str, repo: str) -> str:
    return f"{owner.lower()}/{repo.lower()}"


def extract_repo(source: str | None, source_url: str | None) -> str | None:
    for text in (source or "", source_url or ""):
        value = text.strip()
        if not value:
            continue

        for pattern in (GITHUB_URL_RE, SKILLS_SH_RE, OWNER_REPO_RE):
            match = pattern.search(value) if pattern is not OWNER_REPO_RE else pattern.match(value)
            if match:
                return normalize_repo(match.group("owner"), match.group("repo"))

    return None


def ensure_target_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS skills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            skill_id TEXT NOT NULL,
            name TEXT NOT NULL,
            installs INTEGER NOT NULL,
            source_url TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(source, skill_id)
        )
        """
    )


def normalize_name(name: str) -> str:
    normalized_name = name.strip().strip("/")
    if not normalized_name:
        raise ValueError("empty name")
    return normalized_name


def convert_row(row: sqlite3.Row, source_url_base: str) -> tuple[int, str, str, str, int, str, str]:
    repo = extract_repo(row["source"], row["source_url"])
    if repo is None:
        raise ValueError(f"unable to extract repo from source={row['source']!r}, source_url={row['source_url']!r}")

    normalized_name = normalize_name(row["name"])
    normalized_skill_id = f"{repo}/{normalized_name}"
    normalized_source_url = f"{source_url_base.rstrip('/')}/{normalized_skill_id}"

    return (
        int(row["id"]),
        repo,
        normalized_skill_id,
        normalized_name,
        int(row["installs"]),
        normalized_source_url,
        row["updated_at"],
    )


def convert_db(input_path: Path, output_path: Path, source_url_base: str) -> tuple[int, int]:
    src = sqlite3.connect(input_path)
    src.row_factory = sqlite3.Row

    dst = sqlite3.connect(output_path)
    try:
        ensure_target_db(dst)

        inserted = 0
        failed = 0

        for row in src.execute(
            "SELECT id, source, skill_id, name, installs, source_url, updated_at FROM skills ORDER BY id ASC"
        ):
            try:
                normalized = convert_row(row, source_url_base)
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print(f"[SKIP] id={row['id']} skill_id={row['skill_id']!r}: {exc}")
                continue

            dst.execute(
                """
                INSERT INTO skills (id, source, skill_id, name, installs, source_url, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source, skill_id) DO UPDATE SET
                    name = excluded.name,
                    installs = excluded.installs,
                    source_url = excluded.source_url,
                    updated_at = excluded.updated_at
                """,
                normalized,
            )
            inserted += 1

        dst.commit()
        return inserted, failed
    finally:
        src.close()
        dst.close()


def main() -> None:
    args = build_parser().parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    if not input_path.exists():
        raise FileNotFoundError(f"Input DB not found: {input_path}")

    if output_path.exists() and not args.overwrite:
        raise FileExistsError(
            f"Output DB already exists: {output_path}. Pass --overwrite to replace it."
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()

    inserted, failed = convert_db(input_path, output_path, args.source_url_base)
    print(f"input:    {input_path}")
    print(f"output:   {output_path}")
    print(f"inserted: {inserted}")
    print(f"failed:   {failed}")


if __name__ == "__main__":
    main()
