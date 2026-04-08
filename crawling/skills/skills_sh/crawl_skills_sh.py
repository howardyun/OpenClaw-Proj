import concurrent.futures
import re
import sqlite3
import string
import threading
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import requests


BASE_URL = "https://skills.sh/"
SITEMAP_URL = urljoin(BASE_URL, "sitemap.xml")
SEARCH_API_URL = urljoin(BASE_URL, "api/search")
DB_FILE = "skills.db"
REQUEST_TIMEOUT = 45
SEARCH_LIMIT = 20_000
SEARCH_WORKERS = 24
SHARD_CHARS = string.ascii_lowercase + string.digits + "-_"


def build_skill_id(href: str) -> str:
    return href.strip("/")


def extract_repo_from_href(href: str) -> str:
    parts = href.strip("/").split("/")
    if len(parts) >= 2:
        return f"{parts[0]}/{parts[1]}"
    return "unknown"


def init_db(db_file: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_file)
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
    return conn


def upsert_skill(conn: sqlite3.Connection, item: dict) -> None:
    conn.execute(
        """
        INSERT INTO skills (source, skill_id, name, installs, source_url, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(source, skill_id) DO UPDATE SET
            name = excluded.name,
            installs = excluded.installs,
            source_url = excluded.source_url,
            updated_at = excluded.updated_at
        """,
        (
            item["source"],
            item["skill_id"],
            item["name"],
            item["installs"],
            item["source_url"],
            item["updated_at"],
        ),
    )


def fetch_text(url: str, headers: dict | None = None) -> str:
    resp = requests.get(url, timeout=REQUEST_TIMEOUT, headers=headers)
    resp.raise_for_status()
    return resp.text


def parse_sitemap_skill_paths(xml_text: str) -> list[str]:
    root = ET.fromstring(xml_text)
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    paths: list[str] = []

    for loc in root.findall(".//sm:url/sm:loc", ns):
        if loc.text is None:
            continue
        parsed = urlparse(loc.text.strip())
        path = parsed.path.strip("/")
        if not path:
            continue
        parts = path.split("/")
        if len(parts) != 3:
            continue
        paths.append("/" + "/".join(parts))

    seen = set()
    out = []
    for p in paths:
        if p in seen:
            continue
        seen.add(p)
        out.append(p)
    return out


def fetch_total_skills_from_rsc() -> int | None:
    headers = {
        "rsc": "1",
        "next-url": "/",
        "referer": BASE_URL,
        "accept": "text/x-component",
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/146.0.0.0 Safari/537.36"
        ),
    }
    text = fetch_text(urljoin(BASE_URL, "?_rsc=coverage-check"), headers=headers)
    m = re.search(r'"totalSkills":(\d+)', text)
    if not m:
        return None
    return int(m.group(1))


def _search_once(query: str) -> tuple[list[dict], bool]:
    """
    返回 (skills, saturated)：
    - skills: /api/search 返回的技能列表
    - saturated: 是否触达了 limit（意味着该分片可能被截断）
    """
    last_exc = None
    for _ in range(3):
        try:
            resp = requests.get(
                SEARCH_API_URL,
                params={"q": query, "limit": SEARCH_LIMIT},
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            skills = data.get("skills", []) or []
            saturated = (len(skills) >= SEARCH_LIMIT) or (data.get("count") == SEARCH_LIMIT)
            return skills, saturated
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
    raise RuntimeError(f"search failed for query={query!r}: {last_exc}")


def collect_skills_by_search_shards() -> tuple[dict[str, dict], list[str]]:
    """
    使用两字符分片（aa..zz, 00..99, -_, ...）高覆盖抓取。
    实测可接近 totalSkills（但不保证绝对 100%）。
    """
    queries = [a + b for a in SHARD_CHARS for b in SHARD_CHARS]
    skills_map: dict[str, dict] = {}
    saturated_queries: list[str] = []
    lock = threading.Lock()
    done = 0

    def worker(q: str) -> tuple[str, list[dict], bool]:
        skills, saturated = _search_once(q)
        return q, skills, saturated

    with concurrent.futures.ThreadPoolExecutor(max_workers=SEARCH_WORKERS) as executor:
        futures = [executor.submit(worker, q) for q in queries]
        for fut in concurrent.futures.as_completed(futures):
            q, skills, saturated = fut.result()
            with lock:
                for s in skills:
                    skill_id = s.get("id") or f"{s.get('source', '')}/{s.get('skillId', '')}"
                    source = s.get("source", "")
                    name = s.get("name", "")
                    installs = int(s.get("installs") or 0)
                    if not skill_id or "/" not in skill_id:
                        continue
                    if not source:
                        source = extract_repo_from_href("/" + skill_id)
                    if not name:
                        name = skill_id.split("/")[-1]

                    old = skills_map.get(skill_id)
                    if old is None or installs > old["installs"]:
                        skills_map[skill_id] = {
                            "skill_id": skill_id,
                            "source": source,
                            "name": name,
                            "installs": installs,
                        }
                if saturated:
                    saturated_queries.append(q)
                done += 1
                if done % 100 == 0:
                    print(
                        f"search shards progress: {done}/{len(queries)} "
                        f"unique={len(skills_map)} saturated={len(saturated_queries)}"
                    )

    saturated_queries.sort()
    return skills_map, saturated_queries


def refresh_skills_db(db_file: str = DB_FILE) -> dict[str, int | None | list[str]]:
    conn = init_db(db_file)
    print("fetching sitemap...")
    sitemap_xml = fetch_text(SITEMAP_URL)
    sitemap_paths = parse_sitemap_skill_paths(sitemap_xml)
    sitemap_ids = {build_skill_id(p) for p in sitemap_paths}
    print(f"sitemap skills: {len(sitemap_ids)}")

    print("collecting skills from /api/search shards...")
    skills_map, saturated_queries = collect_skills_by_search_shards()
    print(f"search unique skills: {len(skills_map)}")
    print(f"saturated shards (may still hide some): {len(saturated_queries)} -> {saturated_queries}")

    # 合并 sitemap 兜底（防止搜索接口漏掉个别条目）
    for skill_id in sitemap_ids:
        if skill_id not in skills_map:
            skills_map[skill_id] = {
                "skill_id": skill_id,
                "source": extract_repo_from_href("/" + skill_id),
                "name": skill_id.split("/")[-1],
                "installs": 0,
            }

    total_skills = None
    try:
        total_skills = fetch_total_skills_from_rsc()
    except Exception as exc:  # noqa: BLE001
        print(f"warning: failed to fetch totalSkills from RSC: {exc}")

    now = datetime.now(timezone.utc).isoformat()
    upserted = 0
    for skill_id, v in skills_map.items():
        href = "/" + skill_id
        source_url = urljoin(BASE_URL, href)

        item = {
            "source": v["source"],
            "skill_id": skill_id,
            "name": v["name"],
            "installs": int(v["installs"]),
            "source_url": source_url,
            "updated_at": now,
        }
        upsert_skill(conn, item)
        upserted += 1

    conn.commit()
    conn.close()

    return {
        "upserted_skills": upserted,
        "sitemap_count": len(sitemap_ids),
        "search_unique_count": len(skills_map),
        "coverage_total": total_skills,
        "saturated_queries": saturated_queries,
    }


def main() -> None:
    stats = refresh_skills_db(DB_FILE)

    coverage_total = stats["coverage_total"]
    upserted = stats["upserted_skills"]
    if coverage_total:
        ratio = upserted / coverage_total * 100
        print(f"coverage: {upserted}/{coverage_total} ({ratio:.2f}%)")
    print(f"done, total inserted/updated: {upserted}")


if __name__ == "__main__":
    main()
