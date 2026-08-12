import os, re, json, requests
from bs4 import BeautifulSoup

session = requests.Session()
session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})

res = session.get('https://indratranslations.com/star-embracing-swordmaster/', timeout=30)
match = re.search(r'var\s+TD_Story_Chapters\s*=\s*(\[.*?\]);', res.text, re.DOTALL)
chapters = json.loads(match.group(1))

for c in chapters:
    num = c.get('num', 0)
    if 77 <= num <= 81:
        link = c.get('link', '').replace('\/', '/')
        title = c.get('title', '')
        print(f"ch{num}: {title} => {link}")
