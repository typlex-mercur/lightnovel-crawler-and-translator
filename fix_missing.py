"""Crawl chapter 79 (mislabeled as ch78 on website) and translate all 39 missing chapters."""
import os, re, json, time, sys, requests
from bs4 import BeautifulSoup

os.environ["PYTHONUTF8"] = "1"
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RAW_DIR = r"d:\Somecodes\lightnovel-translator\raw_chapters"
session = requests.Session()
session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})

# Step 1: Crawl chapter 79 (the duplicate ch78 on website)
url79 = "https://indratranslations.com/star-embracing-swordmaster/star-embracing-swordmaster-chapter-78-choices-made-by-a-child-3/"
print("[1] Crawling raw chapter 79...")
res = session.get(url79, timeout=30)
soup = BeautifulSoup(res.text, "html.parser")
div = soup.find("div", id="chapter-content-text")
paragraphs = div.find_all("p")
text = "\n\n".join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))
out = os.path.join(RAW_DIR, "chapter_079.txt")
with open(out, "w", encoding="utf-8") as f:
    f.write(f"# Chapter 79: Choices made by a child (3)\n\n{text}")
print(f"   OK ({len(text)} chars)")

print("\n[2] All raw chapters 62-100 ready. Now translating missing chapters...")
