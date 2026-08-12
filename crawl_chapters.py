"""
crawl_chapters.py – Crawl raw English chapters from indratranslations.com
Sử dụng TD_Story_Chapters JSON từ trang chính để lấy danh sách URL,
sau đó extract nội dung từ div#chapter-content-text.
"""
import os
import sys
import re
import json
import time

os.environ["PYTHONUTF8"] = "1"
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup

# ==========================================
# CẤU HÌNH
# ==========================================
NOVEL_URL = "https://indratranslations.com/star-embracing-swordmaster/"
MAX_CHAPTER = 261
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "raw_chapters")
REQUEST_DELAY = 0.5  # giây giữa mỗi request

# ==========================================
# HTTP SESSION
# ==========================================
session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
})
retry_strategy = Retry(
    total=3,
    backoff_factor=2,
    status_forcelist=[500, 502, 503, 504],
    allowed_methods=["GET"],
)
adapter = HTTPAdapter(max_retries=retry_strategy)
session.mount("http://", adapter)
session.mount("https://", adapter)


def fetch_chapter_list():
    """Lấy danh sách chapter từ biến TD_Story_Chapters trên trang chính."""
    print(f"[*] Đang tải danh sách chương từ {NOVEL_URL}")
    res = session.get(NOVEL_URL, timeout=30)
    res.raise_for_status()

    # Tìm var TD_Story_Chapters = [...];
    match = re.search(r'var\s+TD_Story_Chapters\s*=\s*(\[.*?\]);', res.text, re.DOTALL)
    if not match:
        print("[LỖI] Không tìm thấy TD_Story_Chapters trên trang chính!")
        sys.exit(1)

    chapters = json.loads(match.group(1))
    print(f"[*] Tìm thấy {len(chapters)} chương trên web")
    return chapters


def extract_chapter_content(html_text):
    """Trích nội dung chương từ div#chapter-content-text."""
    soup = BeautifulSoup(html_text, "html.parser")
    content_div = soup.find("div", id="chapter-content-text")
    if not content_div:
        return None

    paragraphs = content_div.find_all("p")
    if not paragraphs:
        return content_div.get_text(separator="\n", strip=True)

    text_parts = []
    for p in paragraphs:
        text = p.get_text(strip=True)
        if text:
            text_parts.append(text)

    return "\n\n".join(text_parts)


def crawl_chapter(url):
    """Tải và extract nội dung 1 chương."""
    try:
        res = session.get(url, timeout=30)
        if res.status_code == 404:
            return None, "NOT_FOUND"
        if res.status_code in (403, 429):
            return None, f"BLOCKED_{res.status_code}"
        res.raise_for_status()

        content = extract_chapter_content(res.text)
        if not content or len(content) < 50:
            return None, "EMPTY_CONTENT"
        return content, "OK"

    except requests.exceptions.Timeout:
        return None, "TIMEOUT"
    except requests.exceptions.ConnectionError:
        return None, "CONNECTION_ERROR"
    except Exception as e:
        return None, f"ERROR_{type(e).__name__}"


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 1. Lấy danh sách chapter
    all_chapters = fetch_chapter_list()

    # 2. Lọc chỉ lấy chapter 1-MAX_CHAPTER
    target_chapters = [ch for ch in all_chapters if ch.get("num", 0) <= MAX_CHAPTER]
    target_chapters.sort(key=lambda x: x["num"])
    print(f"[*] Sẽ crawl {len(target_chapters)} chương (1-{MAX_CHAPTER})")

    # 3. Crawl từng chương
    success = 0
    skipped = 0
    failed = 0

    for ch in target_chapters:
        num = ch["num"]
        url = ch["link"].replace("\\/", "/")
        title = ch.get("title", f"Chapter {num}")
        out_file = os.path.join(OUTPUT_DIR, f"chapter_{num:03d}.txt")

        # Skip nếu đã crawl
        if os.path.exists(out_file) and os.path.getsize(out_file) > 50:
            skipped += 1
            continue

        print(f"  [{num:3d}/{MAX_CHAPTER}] {title}...", end=" ", flush=True)

        content, status = crawl_chapter(url)

        if status == "OK":
            with open(out_file, "w", encoding="utf-8") as f:
                f.write(f"# {title}\n\n{content}")
            success += 1
            print(f"OK ({len(content)} chars)")
        else:
            failed += 1
            print(f"FAIL ({status})")
            # Retry sau 5s nếu bị block
            if "BLOCKED" in status:
                print("  [!] Bị chặn, nghỉ 10s...")
                time.sleep(10)

        time.sleep(REQUEST_DELAY)

    print(f"\n[*] HOÀN TẤT: {success} thành công, {skipped} bỏ qua, {failed} thất bại")
    print(f"[*] File lưu tại: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
