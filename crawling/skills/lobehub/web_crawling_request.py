import sqlite3
import time
import re
import requests
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup
import threading

BASE_URL = "https://lobehub.com/zh/skills?category=all&page={}"
DB_PATH = "lobehub.db"

MAX_PAGE = 14044
RETRY_TIMES = 3
MAX_WORKERS = 10


lock = threading.Lock()



# DB
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS skills (
        id TEXT PRIMARY KEY,
        name TEXT,
        author TEXT,
        rating REAL,
        downloads REAL,
        github_url TEXT,
        crawled_at TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS progress (
        page INTEGER PRIMARY KEY
    )
    """)

    conn.commit()
    conn.close()


def get_done_pages():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT page FROM progress")
    pages = {row[0] for row in c.fetchall()}
    conn.close()
    return pages


def mark_page_done(page):
    with lock:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO progress(page) VALUES(?)", (page,))
        conn.commit()
        conn.close()


def save_skills(skills):
    with lock:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        for s in skills:
            c.execute("""
            INSERT OR REPLACE INTO skills
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                s["id"],
                s["name"],
                s["author"],
                s["rating"],
                s["downloads"],
                s["github_url"],
                s["crawled_at"]
            ))

        conn.commit()
        conn.close()



# GitHub URL
def build_github_url(skill_id):
    parts = skill_id.split("-")
    if len(parts) < 2:
        return None

    author = parts[0]

    if len(parts) == 2:
        repo = parts[1]
    else:
        repo = "-".join(parts[1:-1])

    return f"https://github.com/{author}/{repo}"



# 解析数字
def parse_number(text):
    if not text:
        return None

    text = text.strip().lower().replace(",", "")

    try:
        if "k" in text:
            return float(text.replace("k", "")) * 1000
        return float(text)
    except:
        return None



def parse_page(html):
    soup = BeautifulSoup(html, "html.parser")
    results = []

    cards = soup.select("a[href^='/skills/']")

    for card in cards:
        try:
            href = card.get("href")
            skill_id = href.split("/skills/")[-1]

            name = card.select_one("h2")
            name = name.text.strip() if name else None

            img = card.select_one("img")
            author = None
            if img and "github.com" in img.get("src", ""):
                author = img["src"].split("github.com/")[-1].replace(".png", "")

            rating = None
            downloads = None

            #  找所有 icon 区块
            for div in card.select("div"):
                txt = div.get_text(" ", strip=True)

                # rating
                if "lucide-star" in str(div):
                    m = re.search(r"(\d+\.\d+)", txt)
                    if m:
                        v = float(m.group(1))
                        if 0 <= v <= 5:
                            rating = v

                # downloads
                if "lucide-download" in str(div):
                    m = re.search(r"(\d+(?:\.\d+)?k?)", txt.lower())
                    if m:
                        downloads = parse_number(m.group(1))

            results.append({
                "id": skill_id,
                "name": name,
                "author": author,
                "rating": rating,
                "downloads": downloads,
                "github_url": build_github_url(skill_id),
                "crawled_at": datetime.now(timezone.utc).isoformat()
            })

        except Exception as e:
            print("parse error:", e)

    return results



# 请求单页
def fetch_page(page_num):
    url = BASE_URL.format(page_num)

    for i in range(RETRY_TIMES):
        try:
            r = requests.get(url, timeout=15)
            if r.status_code == 200:
                return parse_page(r.text)
        except Exception as e:
            print(f"⚠️ page {page_num} retry {i+1}: {e}")

        time.sleep(1)

    return None



# worker
def worker(page_num):
    data = fetch_page(page_num)

    if not data:
        print(f"❌ page {page_num} failed")
        return

    save_skills(data)
    mark_page_done(page_num)

    print(f"✅ page {page_num} ({len(data)})")


# main
def main():
    init_db()
    done = get_done_pages()

    pages = [i for i in range(1, MAX_PAGE + 1) if i not in done]

    print(f"待爬页数: {len(pages)}")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = [ex.submit(worker, p) for p in pages]

        for i, _ in enumerate(as_completed(futures), 1):
            print(f"进度: {i}/{len(pages)}")



if __name__ == "__main__":
    main()