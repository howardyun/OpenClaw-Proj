import requests
import sqlite3
import time
from datetime import datetime
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# 配置
API_URL = "https://wry-manatee-359.convex.cloud/api/query"
DOWNLOAD_PREFIX = "https://wry-manatee-359.convex.site/api/v1/download?slug="

headers = {
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0",
    "Connection": "close"
}


# Session + Retry（增强版）
session = requests.Session()

retry = Retry(
    total=5,
    backoff_factor=1.5,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["POST"]
)

adapter = HTTPAdapter(max_retries=retry)
session.mount("https://", adapter)


# SQLite 初始化
conn = sqlite3.connect("clawHub.db")
cursor_db = conn.cursor()

cursor_db.execute("""
CREATE TABLE IF NOT EXISTS skills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT UNIQUE,
    displayname TEXT,
    owner TEXT,
    downloads INTEGER,
    stars INTEGER,
    download_url TEXT,
    crawled_at TEXT
)
""")

conn.commit()


# 安全请求函数
def safe_post(payload):
    for i in range(5):
        try:
            r = session.post(API_URL, json=payload, headers=headers, timeout=30)

            if r.status_code != 200:
                print(f"[retry {i+1}] bad status: {r.status_code}")
                time.sleep(2 * (i + 1))
                continue

            try:
                return r.json()
            except Exception as e:
                print(f"[retry {i+1}] JSON decode error: {e}")
                time.sleep(2 * (i + 1))
                continue

        except Exception as e:
            print(f"[retry {i+1}] request error: {e}")
            time.sleep(2 * (i + 1))

    return None


# 爬虫主逻辑
cursor = None
page_count = 0

while True:

    args = {
        "dir": "desc",
        "highlightedOnly": False,
        "nonSuspiciousOnly": True,
        "numItems": 25,
        "sort": "downloads"
    }

    if cursor:
        args["cursor"] = cursor

    payload = {
        "path": "skills:listPublicPageV4",
        "format": "convex_encoded_json",
        "args": [args]
    }

    data = safe_post(payload)

    if not data:
        print("❌ request failed permanently")
        break

    value = data.get("value", {})
    page = value.get("page", [])
    cursor = value.get("nextCursor")

    print(f"\n📦 page {page_count}, items={len(page)}")

    if not page:
        break

    for item in page:

        skill = item.get("skill", {})
        stats = skill.get("stats", {})

        slug = skill.get("slug")
        displayname = skill.get("displayName")

        owner = item.get("ownerHandle")  # ✅ 新增

        downloads = int(stats.get("downloads", 0))
        stars = int(stats.get("stars", 0))

        download_url = DOWNLOAD_PREFIX + (slug or "")

        crawled_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        try:
            cursor_db.execute("""
            INSERT OR IGNORE INTO skills (
                slug,
                displayname,
                owner,
                downloads,
                stars,
                download_url,
                crawled_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                slug,
                displayname,
                owner,
                downloads,
                stars,
                download_url,
                crawled_at
            ))

        except Exception as e:
            print(f"[DB ERROR] {e}")

        print(displayname, owner, downloads, stars)

    conn.commit()

    page_count += 1

    if not cursor:
        print("✔ finished (no more cursor)")
        break

    time.sleep(1.5)

conn.close()