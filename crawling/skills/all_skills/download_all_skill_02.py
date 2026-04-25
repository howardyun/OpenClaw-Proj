import os
import sqlite3
import requests
import zipfile
import shutil
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading


# 配置
DB_PATH = "all_skills.db"
BASE_URL = "https://wry-manatee-359.convex.site/api/v1/download?slug="

OUTPUT_DIR = Path("clawhub_output")
TMP_DIR = Path(r"D:\tmp")

MAX_WORKERS = 2
TIMEOUT = 60
MAX_RETRY = 5

lock = threading.Lock()


# 初始化目录

OUTPUT_DIR.mkdir(exist_ok=True)
TMP_DIR.mkdir(parents=True, exist_ok=True)



# 工具：强制清理文件

def safe_delete(path: Path):
    try:
        if path.exists():
            path.unlink()
    except Exception:
        pass


def cleanup(name: str, zip_path: Path):
    """清理所有临时残留文件"""
    tmp_file = TMP_DIR / f"{name}.tmp"
    tmp_zip = TMP_DIR / f"{name}.zip"

    safe_delete(tmp_file)
    safe_delete(tmp_zip)
    safe_delete(zip_path)



# 读取任务

def load_tasks():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT name
        FROM all_skills
        WHERE source_plat='clawhub'
    """)

    rows = cursor.fetchall()
    conn.close()

    return [r[0] for r in rows if r[0]]



# 判断是否完成

def is_done(name: str) -> bool:
    target_dir = OUTPUT_DIR / name
    return target_dir.exists() and any(target_dir.iterdir())



# 下载

def download_zip(name: str, zip_path: Path):
    url = BASE_URL + name

    for attempt in range(MAX_RETRY):
        try:
            r = requests.get(url, stream=True, timeout=TIMEOUT)

            #  404
            if r.status_code == 404:
                with lock:
                    print(f"[404 SKIP] {name}")
                return "NOT_FOUND"

            #  429
            if r.status_code == 429:
                wait = 2 ** attempt
                with lock:
                    print(f"[429] {name} retry in {wait}s")
                time.sleep(wait)
                continue

            r.raise_for_status()


            # 下载到 D:\tmp

            tmp_file = TMP_DIR / f"{name}.tmp"

            with open(tmp_file, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        f.write(chunk)

            final_zip = TMP_DIR / f"{name}.zip"
            tmp_file.rename(final_zip)

            # 移动到输出目录
            zip_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(final_zip), str(zip_path))

            return "OK"

        except Exception as e:
            wait = 2 ** attempt
            with lock:
                print(f"[RETRY] {name} error={e}, wait {wait}s")
            time.sleep(wait)

    raise Exception(f"FAILED DOWNLOAD: {name}")



# 解压

def extract_zip(zip_path: Path, target_dir: Path):
    target_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        zip_ref.extractall(target_dir)



# 单任务

def process(name: str, idx: int, total: int):
    zip_path = OUTPUT_DIR / f"{name}.zip"
    target_dir = OUTPUT_DIR / name

    try:
        if is_done(name):
            with lock:
                print(f"[SKIP] {idx}/{total} {name}")
            return

        with lock:
            print(f"[START] {idx}/{total} {name}")

        result = download_zip(name, zip_path)

        if result == "NOT_FOUND":
            cleanup(name, zip_path)
            return

        extract_zip(zip_path, target_dir)

        with lock:
            print(f"[DONE] {idx}/{total} {name}")

    except Exception as e:
        with lock:
            print(f"[ERROR] {idx}/{total} {name} -> {e}")

    finally:

        #  强制清理

        cleanup(name, zip_path)



# 主函数

def main():
    names = load_tasks()
    total = len(names)

    print(f"TOTAL TASKS: {total}")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [
            executor.submit(process, name, idx, total)
            for idx, name in enumerate(names, 1)
        ]

        for _ in as_completed(futures):
            pass

    print("ALL DONE")


if __name__ == "__main__":
    main()