import requests
import sqlite3
import time
from datetime import datetime, UTC
from concurrent.futures import ThreadPoolExecutor
import threading

API_URL = "https://skillsmp.com/api/v1/skills/search"
TOKEN = "sk_live_skillsmp_YbRLMpddinAj9jPGVUZEg8c7FRGPa6s7SLxAwoURfiI"

HEADERS = {
    "Authorization": f"Bearer {TOKEN}"
}

DB = "skillsmp.db"


# 全局限流器
class RateLimiter:
    def __init__(self, rate_per_sec):
        self.interval = 1.0 / rate_per_sec
        self.lock = threading.Lock()
        self.last_time = time.monotonic()

    def wait(self):
        with self.lock:
            now = time.monotonic()
            wait_time = self.interval - (now - self.last_time)
            if wait_time > 0:
                time.sleep(wait_time)
            self.last_time = time.monotonic()


# 🔥 调速核心
limiter = RateLimiter(rate_per_sec=5)  # ≈300 req/min

# DB 写锁（防止 database is locked）
db_lock = threading.Lock()



# 初始化数据库
def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS skills (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE,
        author TEXT,
        github_url TEXT,
        stars INTEGER,
        crawled_at TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS progress (
        shard TEXT PRIMARY KEY,
        page INTEGER,
        done INTEGER DEFAULT 0
    )
    """)

    conn.commit()
    conn.close()



# shard 生成
def generate_shards():
    chars = "abcdefghijklmnopqrstuvwxyz0123456789"
    return [a + b for a in chars for b in chars]



# 获取进度
def get_progress(conn, shard):
    c = conn.cursor()
    c.execute("SELECT page, done FROM progress WHERE shard=?", (shard,))
    row = c.fetchone()

    if row:
        return row[0], row[1]
    else:
        return 1, 0



# 更新进度
def update_progress(conn, shard, page, done=0):
    with db_lock:
        conn.execute("""
        INSERT INTO progress (shard, page, done)
        VALUES (?, ?, ?)
        ON CONFLICT(shard)
        DO UPDATE SET page=excluded.page, done=excluded.done
        """, (shard, page, done))
        conn.commit()



# 插入数据
def insert_skill(conn, skill):
    with db_lock:
        conn.execute("""
        INSERT OR IGNORE INTO skills
        (name, author, github_url, stars, crawled_at)
        VALUES (?, ?, ?, ?, ?)
        """, (
            skill["name"],
            skill["author"],
            skill["githubUrl"],
            skill["stars"],
            datetime.now(UTC).isoformat()
        ))
        conn.commit()



# 请求
def fetch(shard, page):
    limiter.wait()  # 🔥 全局限流

    params = {
        "q": shard,
        "page": page,
        "limit": 100,
        "sortBy": "stars"
    }

    resp = requests.get(API_URL, headers=HEADERS, params=params, timeout=20)
    resp.raise_for_status()

    return resp.json(), resp.headers



# 单个 shard worker
def process_shard(shard):
    conn = sqlite3.connect(DB)

    page, done = get_progress(conn, shard)

    if done == 1:
        print(f"跳过 {shard}")
        return

    print(f"\n=== shard={shard} 从 page={page} 开始 ===")

    last_remaining = None
    MAX_RETRIES = 3

    for p in range(page, 21):

        for attempt in range(MAX_RETRIES):
            try:
                data, headers = fetch(shard, p)

                remaining = headers.get("X-RateLimit-Daily-Remaining")
                remaining = int(remaining) if remaining else -1
                last_remaining = remaining

                skills = data["data"]["skills"]

                # 空页处理
                if not skills:
                    print(f"{shard} page {p} -> 跳过空白页")
                    break  # 不重试，直接下一页

                # 正常写入
                for s in skills:
                    insert_skill(conn, s)

                update_progress(conn, shard, p)

                print(f"{shard} page {p} -> {len(skills)} | remaining={remaining}")

                # 成功 退出重试循环
                break

            except Exception as e:
                print(f"{shard} page {p} 第{attempt+1}次失败: {e}")
                time.sleep(2 * (attempt + 1))

        else:
            # ❗ 所有重试都失败
            print(f"❌ {shard} page {p} 多次失败，跳过")

        # API 限额检查
        if last_remaining == 0:
            print("API 限额用完，停止")
            conn.close()
            return

    update_progress(conn, shard, 20, done=1)

    print(f"✔ 完成 {shard} | 剩余: {last_remaining}")
    conn.close()



# 主逻辑（多线程）
def crawl():
    shards = generate_shards()

    # 🔥 线程数
    THREADS = 5

    with ThreadPoolExecutor(max_workers=THREADS) as executor:
        executor.map(process_shard, shards)


if __name__ == "__main__":
    init_db()
    crawl()