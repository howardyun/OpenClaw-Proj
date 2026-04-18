import os
import requests
import time
import sqlite3
from urllib.parse import unquote

DB_FILE = "clawHub.db"
SAVE_FOLDER = r"D:\skills"

RETRY_TIMES = 3
DELAY = 0.5

if not os.path.exists(SAVE_FOLDER):
    os.makedirs(SAVE_FOLDER)


def direct_download(url, retry=0):
    """直接下载文件，使用服务器返回的文件名"""

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept": "*/*",
        "Referer": "https://clawhub.ai/"
    }

    try:
        with requests.get(url, headers=headers, stream=True, timeout=30) as r:

            r.raise_for_status()

            content_disposition = r.headers.get("Content-Disposition", "")

            if "filename=" in content_disposition:
                filename = content_disposition.split("filename=")[-1].strip('"\'')
            else:
                slug = url.split("slug=")[-1] if "slug=" in url else url.split("/")[-1]
                slug = unquote(slug)
                filename = f"{slug}.zip"

            save_path = os.path.join(SAVE_FOLDER, filename)

            with open(save_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

            file_size = os.path.getsize(save_path)

            return True, save_path, file_size

    except Exception as e:

        if retry < RETRY_TIMES:
            time.sleep(1)
            return direct_download(url, retry + 1)

        return False, str(e), 0


def load_urls_from_db():
    """从数据库读取下载链接"""

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, displayname, download_url
        FROM skills
        WHERE download_url IS NOT NULL
    """)

    rows = cursor.fetchall()

    conn.close()

    return rows


def run():

    print("=" * 60)
    print("📥 开始下载 Skill 文件...")
    print(f"📁 保存目录: {SAVE_FOLDER}")
    print(f"🗄️ 数据库: {DB_FILE}")
    print("=" * 60)

    rows = load_urls_from_db()

    total = len(rows)

    print(f"总计需要下载: {total} 个文件\n")

    success_count = 0
    fail_count = 0
    total_size = 0

    for i, row in enumerate(rows, 1):

        idx = row[0]
        skill_name = row[1]
        url = row[2]

        if not url or "http" not in url:
            print(f"⏭️ [{i}/{total}] 第{idx}条：无效链接")
            continue

        print(f"⬇️ [{i}/{total}] 下载: {skill_name}...", end=" ")

        success, info, size = direct_download(url)

        if success:
            print(f"✅ {info} ({size/1024:.1f}KB)")
            success_count += 1
            total_size += size
        else:
            print(f"❌ 失败: {info}")
            fail_count += 1

        if i < total:
            time.sleep(DELAY)

    print("\n" + "=" * 60)
    print("🏁 下载完成!")
    print(f"✅ 成功: {success_count} 个")
    print(f"❌ 失败: {fail_count} 个")
    print(f"📊 总大小: {total_size/1024/1024:.2f} MB")
    print(f"📁 保存目录: {os.path.abspath(SAVE_FOLDER)}")
    print("=" * 60)


if __name__ == "__main__":
    run()