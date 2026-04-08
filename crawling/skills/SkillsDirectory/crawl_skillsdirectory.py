import argparse
import concurrent.futures
import re
import sqlite3
import threading
import time
from datetime import datetime, timezone
from typing import Any

import requests

API_URL = "https://www.skillsdirectory.com/api/skills"
SKILLS_SH_URL = "https://skills.sh/{skill_id}"
DEFAULT_DB = "skills.db"
DEFAULT_WORKERS = 24
REQUEST_TIMEOUT = 45
RETRIES = 3

GITHUB_URL_RE = re.compile(
    r"(?:https?://|git@)github\.com[:/](?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+?)(?:\.git)?(?:/|$)",
    re.IGNORECASE,
)
OWNER_REPO_RE = re.compile(r"^(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+)$")


def normalize_repo(owner: str, repo: str) -> str:
    return f"{owner.lower()}/{repo.lower()}"


def extract_repo(*candidates: str | None) -> str | None:
    for text in candidates:
        value = (text or "").strip()
        if not value:
            continue

        match = GITHUB_URL_RE.search(value)
        if match:
            return normalize_repo(match.group("owner"), match.group("repo"))

        match = OWNER_REPO_RE.match(value)
        if match:
            return normalize_repo(match.group("owner"), match.group("repo"))

    return None


def normalize_name(name: str) -> str:
    normalized_name = name.strip().strip("/")
    if not normalized_name:
        raise ValueError("empty name")
    return normalized_name


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS skills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            skill_id TEXT NOT NULL,
            name TEXT NOT NULL,
            installs INTEGER NOT NULL, -- github
            source_url TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(source, skill_id)
        )
        """
    )


def fetch_page(session: requests.Session, page: int) -> dict[str, Any]:
    last_exc: Exception | None = None
    for attempt in range(1, RETRIES + 1):
        try:
            resp = session.get(API_URL, params={"page": page}, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            if "skills" not in data or "pagination" not in data:
                raise RuntimeError(f"unexpected response shape on page={page}")
            return data
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt < RETRIES:
                time.sleep(0.8 * attempt)
    raise RuntimeError(f"failed page={page}: {last_exc}")


def map_skill(raw: dict[str, Any], now_iso: str) -> dict[str, Any] | None:
    slug = (raw.get("slug") or "").strip()
    if not slug:
        return None

    repo = extract_repo(raw.get("githubRepoFullName"), raw.get("sourceUrl"))
    if not repo:
        return None

    name = normalize_name((raw.get("name") or slug).strip())
    installs = int(raw.get("githubStars") or 0)
    skill_id = f"{repo}/{name}"

    return {
        "source": repo,
        "skill_id": skill_id,
        "name": name,
        "installs": installs,
        "source_url": SKILLS_SH_URL.format(skill_id=skill_id),
        "updated_at": now_iso,
    }


def upsert_many(conn: sqlite3.Connection, rows: list[dict[str, Any]]) -> None:
    conn.executemany(
        """
        INSERT INTO skills (source, skill_id, name, installs, source_url, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(source, skill_id) DO UPDATE SET
            name = excluded.name,
            installs = excluded.installs,
            source_url = excluded.source_url,
            updated_at = excluded.updated_at
        """,
        [
            (
                r["source"],
                r["skill_id"],
                r["name"],
                r["installs"],
                r["source_url"],
                r["updated_at"],
            )
            for r in rows
        ],
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scrape skillsdirectory.com skills into SQLite using the skills.sh-compatible schema"
    )
    parser.add_argument("--db", default=DEFAULT_DB, help=f"SQLite file (default: {DEFAULT_DB})")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS, help="Concurrent page workers")
    args = parser.parse_args()

    session = requests.Session()
    session.headers.update(
        {
            "user-agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/146.0.0.0 Safari/537.36"
            )
        }
    )

    first = fetch_page(session, 1)
    total_pages = int(first["pagination"]["totalPages"])
    total_count = int(first["pagination"]["totalCount"])
    print(f"total pages: {total_pages}, total skills reported: {total_count}")

    now_iso = datetime.now(timezone.utc).isoformat()

    all_rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    lock = threading.Lock()
    skipped = 0

    def ingest_page_data(data: dict[str, Any]) -> None:
        nonlocal skipped
        local_rows: list[tuple[tuple[str, str], dict[str, Any]]] = []
        local_skipped = 0
        for raw in data.get("skills", []):
            try:
                item = map_skill(raw, now_iso)
            except Exception as exc:  # noqa: BLE001
                local_skipped += 1
                slug = raw.get("slug")
                print(f"skip invalid skill slug={slug!r}: {exc}")
                continue
            if not item:
                local_skipped += 1
                continue
            key = (item["source"], item["skill_id"])
            local_rows.append((key, item))

        with lock:
            skipped += local_skipped
            for key, item in local_rows:
                if key in seen:
                    continue
                seen.add(key)
                all_rows.append(item)

    ingest_page_data(first)

    pages = list(range(2, total_pages + 1))
    done = 1

    def worker(page: int) -> tuple[int, dict[str, Any]]:
        return page, fetch_page(session, page)

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = [ex.submit(worker, p) for p in pages]
        for fut in concurrent.futures.as_completed(futures):
            page, data = fut.result()
            ingest_page_data(data)
            done += 1
            if done % 100 == 0 or done == total_pages:
                print(f"progress: {done}/{total_pages}, unique rows: {len(all_rows)}")

    conn = sqlite3.connect(args.db)
    init_db(conn)
    upsert_many(conn, all_rows)
    conn.commit()

    inserted_now = conn.execute(
        "SELECT COUNT(*) FROM skills WHERE source_url LIKE 'https://skills.sh/%'"
    ).fetchone()[0]

    conn.close()

    print(f"upserted rows this run: {len(all_rows)}")
    print(f"skipped rows this run: {skipped}")
    print(f"rows currently in DB from skillsdirectory.com: {inserted_now}")


if __name__ == "__main__":
    main()
