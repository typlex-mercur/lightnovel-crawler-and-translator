"""
preprocess.py – Phase 0: Xây dựng "bộ não dịch"
1. Extract bản dịch VN từ EPUB → samples/vi/
2. Copy raw EN tương ứng → samples/en/
3. Tạo Style Guide từ phân tích mẫu
4. Tạo Translation Memory (paragraph-level alignment + embeddings)
5. Tạo Glossary khởi tạo
"""
import os
import sys
import re
import json
import time
import zipfile
import math

os.environ["PYTHONUTF8"] = "1"
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from bs4 import BeautifulSoup
from google import genai
from google.genai import types

# ==========================================
# CẤU HÌNH
# ==========================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
EPUB_FILES = [
    r"C:\Users\Admin\Downloads\1-50 - Tinh Tú Kiếm Sĩ.epub",
    r"C:\Users\Admin\Downloads\51-100 - Tinh Tú Kiếm Sĩ.epub",
]
RAW_DIR = os.path.join(SCRIPT_DIR, "raw_chapters")
SAMPLES_EN_DIR = os.path.join(SCRIPT_DIR, "samples", "en")
SAMPLES_VI_DIR = os.path.join(SCRIPT_DIR, "samples", "vi")
TRANSLATED_DIR = os.path.join(SCRIPT_DIR, "translated_chapters")

STYLE_GUIDE_FILE = os.path.join(SCRIPT_DIR, "style_guide.txt")
TM_FILE = os.path.join(SCRIPT_DIR, "translation_memory.json")
GLOSSARY_FILE = os.path.join(SCRIPT_DIR, "glossary.json")

API_KEYS_FILE = os.environ.get("GEMINI_API_KEYS_FILE", "D:/Somecodes/API/api_keys.txt")
EMBEDDING_MODEL = "gemini-embedding-2"
TEXT_MODEL = "gemini-3.5-flash"

SAFETY_SETTINGS = [
    types.SafetySetting(category=c, threshold=types.HarmBlockThreshold.BLOCK_NONE)
    for c in [
        types.HarmCategory.HARM_CATEGORY_HARASSMENT,
        types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
        types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
        types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
    ]
]


def load_api_keys():
    with open(API_KEYS_FILE, "r", encoding="utf-8") as f:
        keys = [l.strip() for l in f if l.strip() and not l.strip().startswith("#")]
    keys = [k for k in keys if len(k) > 30]
    print(f"[*] Đã nạp {len(keys)} API keys")
    return keys


API_KEYS = load_api_keys()
_key_index = 0
_client_cache = {}


def get_client():
    global _key_index
    key = API_KEYS[_key_index]
    if key not in _client_cache:
        _client_cache[key] = genai.Client(api_key=key)
    return _client_cache[key]


def rotate_key():
    global _key_index
    _key_index = (_key_index + 1) % len(API_KEYS)
    print(f"  [KEY] Xoay sang key #{_key_index + 1}")


# ==========================================
# BƯỚC 0a: EXTRACT EPUB
# ==========================================
def extract_epub_chapters():
    """Trích xuất text từ EPUB files → samples/vi/chapter_XXX.txt"""
    os.makedirs(SAMPLES_VI_DIR, exist_ok=True)
    os.makedirs(SAMPLES_EN_DIR, exist_ok=True)
    os.makedirs(TRANSLATED_DIR, exist_ok=True)

    total_extracted = 0

    for epub_path in EPUB_FILES:
        if not os.path.exists(epub_path):
            print(f"[!] Không tìm thấy EPUB: {epub_path}")
            continue

        print(f"[*] Đang xử lý EPUB: {os.path.basename(epub_path)}")

        with zipfile.ZipFile(epub_path, "r") as z:
            xhtml_files = sorted([
                n for n in z.namelist()
                if n.endswith(".xhtml") and "Chuong" in n
            ])

            for xhtml_name in xhtml_files:
                # Parse chapter number từ filename: "0_Chuong-1-1-slug.xhtml"
                match = re.search(r'Chuong-(\d+)', xhtml_name)
                if not match:
                    continue
                chapter_num = int(match.group(1))

                vi_file = os.path.join(SAMPLES_VI_DIR, f"chapter_{chapter_num:03d}.txt")
                if os.path.exists(vi_file) and os.path.getsize(vi_file) > 50:
                    continue

                content = z.read(xhtml_name).decode("utf-8")
                soup = BeautifulSoup(content, "html.parser")

                # Lấy title
                title_tag = soup.find("h1")
                title = title_tag.get_text(strip=True) if title_tag else f"Chương {chapter_num}"

                # Lấy nội dung (các thẻ <p>)
                paragraphs = []
                for p in soup.find_all("p"):
                    text = p.get_text(strip=True)
                    # Bỏ metadata (Tác giả, Trans)
                    if text and not text.startswith("Tác giả:") and not text.startswith("Trans:"):
                        paragraphs.append(text)

                if paragraphs:
                    with open(vi_file, "w", encoding="utf-8") as f:
                        f.write(f"# {title}\n\n")
                        f.write("\n\n".join(paragraphs))
                    total_extracted += 1

                    # Copy vào translated_chapters luôn
                    trans_file = os.path.join(TRANSLATED_DIR, f"chapter_{chapter_num:03d}.txt")
                    if not os.path.exists(trans_file):
                        with open(trans_file, "w", encoding="utf-8") as f:
                            f.write(f"# {title}\n\n")
                            f.write("\n\n".join(paragraphs))

    # Copy raw EN tương ứng → samples/en/
    en_copied = 0
    for vi_file in os.listdir(SAMPLES_VI_DIR):
        en_src = os.path.join(RAW_DIR, vi_file)
        en_dst = os.path.join(SAMPLES_EN_DIR, vi_file)
        if os.path.exists(en_src) and not os.path.exists(en_dst):
            with open(en_src, "r", encoding="utf-8") as f:
                content = f.read()
            with open(en_dst, "w", encoding="utf-8") as f:
                f.write(content)
            en_copied += 1

    print(f"[*] Extract EPUB: {total_extracted} chương VN, {en_copied} chương EN copied")
    return total_extracted


# ==========================================
# BƯỚC 0b: STYLE GUIDE
# ==========================================
def generate_style_guide():
    """Phân tích 10 chương mẫu để rút ra style guide."""
    if os.path.exists(STYLE_GUIDE_FILE) and os.path.getsize(STYLE_GUIDE_FILE) > 100:
        print(f"[*] Style guide đã tồn tại, bỏ qua")
        return

    print("[*] Đang tạo Style Guide từ samples...")

    # Chọn 10 chương đại diện (đầu, giữa, cuối)
    sample_chapters = [1, 5, 10, 20, 30, 40, 50, 60, 80, 100]
    pairs_text = []

    for ch in sample_chapters:
        en_file = os.path.join(SAMPLES_EN_DIR, f"chapter_{ch:03d}.txt")
        vi_file = os.path.join(SAMPLES_VI_DIR, f"chapter_{ch:03d}.txt")
        if not os.path.exists(en_file) or not os.path.exists(vi_file):
            continue

        with open(en_file, "r", encoding="utf-8") as f:
            en_text = f.read()[:2000]  # Lấy 2000 ký tự đầu
        with open(vi_file, "r", encoding="utf-8") as f:
            vi_text = f.read()[:2000]

        pairs_text.append(f"--- Chương {ch} ---\n[EN]:\n{en_text}\n\n[VN]:\n{vi_text}")

    if not pairs_text:
        print("[!] Không đủ samples để tạo style guide")
        return

    prompt = f"""Phân tích các cặp bản dịch EN→VN dưới đây và rút ra BỘ QUY TẮC DỊCH chi tiết.
Đây là light novel thể loại fantasy/kiếm hiệp phương Tây.

{chr(10).join(pairs_text[:5])}

Hãy tạo một tài liệu Style Guide bao gồm:

1. **Văn phong tổng quan**: Giọng kể, mức trang trọng, phong cách câu
2. **Quy tắc xử lý tên riêng**: Giữ nguyên hay dịch, format
3. **Quy tắc hội thoại**: Dấu ngoặc, cách xuống dòng, xưng hô
4. **Quy tắc thuật ngữ**: Những từ nào giữ nguyên EN, từ nào dịch
5. **Pattern dịch thường gặp**: Các cụm từ EN phổ biến được dịch thế nào
6. **Quy tắc về dấu câu**: Dấu lửng, dấu chấm than, etc.
7. **Những điều KHÔNG NÊN làm**: Over-translate, thêm thắt, etc.

Viết bằng tiếng Việt. Trả về dạng Markdown rõ ràng, ngắn gọn, có thể dùng trực tiếp làm system prompt."""

    client = get_client()
    try:
        response = client.models.generate_content(
            model=TEXT_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                safety_settings=SAFETY_SETTINGS,
                temperature=0.3,
            )
        )
        style_guide = response.text
        with open(STYLE_GUIDE_FILE, "w", encoding="utf-8") as f:
            f.write(style_guide)
        print(f"[*] Style guide đã lưu ({len(style_guide)} chars)")
    except Exception as e:
        print(f"[!] Lỗi tạo style guide: {e}")
        rotate_key()


# ==========================================
# BƯỚC 0c: TRANSLATION MEMORY
# ==========================================
def build_translation_memory():
    """Tạo Translation Memory: align paragraphs EN↔VN + tạo embeddings."""
    if os.path.exists(TM_FILE) and os.path.getsize(TM_FILE) > 1000:
        print(f"[*] Translation Memory đã tồn tại, bỏ qua")
        return

    print("[*] Đang xây dựng Translation Memory...")

    # Bước 1: Align paragraphs
    pairs = []
    for ch_num in range(1, 101):
        en_file = os.path.join(SAMPLES_EN_DIR, f"chapter_{ch_num:03d}.txt")
        vi_file = os.path.join(SAMPLES_VI_DIR, f"chapter_{ch_num:03d}.txt")
        if not os.path.exists(en_file) or not os.path.exists(vi_file):
            continue

        with open(en_file, "r", encoding="utf-8") as f:
            en_text = f.read()
        with open(vi_file, "r", encoding="utf-8") as f:
            vi_text = f.read()

        # Chia thành paragraphs (bỏ title line)
        en_paras = [p.strip() for p in en_text.split("\n\n") if p.strip() and not p.strip().startswith("#")]
        vi_paras = [p.strip() for p in vi_text.split("\n\n") if p.strip() and not p.strip().startswith("#")]

        # Gộp thành nhóm ~3-5 paragraphs cho mỗi đoạn
        en_groups = _group_paragraphs(en_paras, group_size=4)
        vi_groups = _group_paragraphs(vi_paras, group_size=4)

        # Align theo vị trí tương đối
        min_groups = min(len(en_groups), len(vi_groups))
        for i in range(min_groups):
            en_chunk = en_groups[i]
            vi_chunk = vi_groups[i]

            # Lọc: bỏ cặp lệch quá nhiều
            en_len = len(en_chunk)
            vi_len = len(vi_chunk)
            if en_len > 0 and vi_len > 0:
                ratio = max(en_len, vi_len) / min(en_len, vi_len)
                if ratio < 4:  # Cho phép lệch tới 4x
                    pairs.append({
                        "en": en_chunk,
                        "vi": vi_chunk,
                        "chapter": ch_num,
                    })

    print(f"[*] Đã align {len(pairs)} cặp đoạn từ {min(100, ch_num)} chương")

    # Bước 2: Tạo embeddings cho phần EN
    print("[*] Đang tạo embeddings (có thể mất vài phút)...")
    batch_size = 100  # Gemini embedding cho phép batch
    total_batches = math.ceil(len(pairs) / batch_size)

    for batch_idx in range(total_batches):
        start = batch_idx * batch_size
        end = min(start + batch_size, len(pairs))
        batch_texts = [p["en"][:2000] for p in pairs[start:end]]  # Truncate nếu quá dài

        success = False
        for attempt in range(5):
            try:
                client = get_client()
                result = client.models.embed_content(
                    model=EMBEDDING_MODEL,
                    contents=batch_texts,
                )
                for i, embedding in enumerate(result.embeddings):
                    pairs[start + i]["embedding"] = embedding.values
                success = True
                break
            except Exception as e:
                print(f"  [!] Embedding batch {batch_idx+1}/{total_batches} lỗi: {e}")
                rotate_key()
                time.sleep(2 ** attempt)

        if not success:
            print(f"  [!] Bỏ qua batch {batch_idx+1} sau 5 lần thử")
            for i in range(start, end):
                pairs[i]["embedding"] = []

        if (batch_idx + 1) % 10 == 0:
            print(f"  [{batch_idx+1}/{total_batches}] batches hoàn thành")
        time.sleep(0.1)

    # Bước 3: Lưu TM
    with open(TM_FILE, "w", encoding="utf-8") as f:
        json.dump({"pairs": pairs}, f, ensure_ascii=False)

    file_size_mb = os.path.getsize(TM_FILE) / (1024 * 1024)
    print(f"[*] Translation Memory đã lưu: {len(pairs)} cặp, {file_size_mb:.1f} MB")


def _group_paragraphs(paragraphs, group_size=4):
    """Gộp paragraphs thành nhóm."""
    groups = []
    for i in range(0, len(paragraphs), group_size):
        chunk = "\n\n".join(paragraphs[i:i + group_size])
        if chunk.strip():
            groups.append(chunk)
    return groups


# ==========================================
# BƯỚC 0d: GLOSSARY
# ==========================================
def generate_glossary():
    """Dùng AI scan samples để tạo glossary khởi tạo."""
    if os.path.exists(GLOSSARY_FILE) and os.path.getsize(GLOSSARY_FILE) > 100:
        print(f"[*] Glossary đã tồn tại, bỏ qua")
        return

    print("[*] Đang tạo Glossary khởi tạo...")

    # Thu thập nội dung từ 15 chương mẫu
    sample_texts = []
    for ch in [1, 3, 5, 10, 15, 20, 25, 30, 40, 50, 60, 70, 80, 90, 100]:
        en_file = os.path.join(SAMPLES_EN_DIR, f"chapter_{ch:03d}.txt")
        vi_file = os.path.join(SAMPLES_VI_DIR, f"chapter_{ch:03d}.txt")
        if not os.path.exists(en_file) or not os.path.exists(vi_file):
            continue
        with open(en_file, "r", encoding="utf-8") as f:
            en = f.read()[:1500]
        with open(vi_file, "r", encoding="utf-8") as f:
            vi = f.read()[:1500]
        sample_texts.append(f"[Chương {ch} EN]:\n{en}\n\n[Chương {ch} VN]:\n{vi}")

    if not sample_texts:
        print("[!] Không đủ samples")
        return

    prompt = f"""Phân tích các đoạn truyện light novel EN↔VN dưới đây.
Trích xuất danh sách TẤT CẢ nhân vật, thế lực/gia tộc, và địa danh quan trọng.

{chr(10).join(sample_texts[:8])}

YÊU CẦU:
- Chỉ liệt kê những thứ CẦN NHỚ: tên khó, dễ nhầm, hoặc có đặc điểm nhận diện
- KHÔNG liệt kê thuật ngữ phổ biến giữ nguyên EN (Aura, Mana, Gold...)

QUY TẮC VỀ MÔ TẢ (identity):
- PHẢI viết bằng tiếng Việt, KHÔNG dùng tiếng Anh.
- Mô tả KHÁCH QUAN về bản thân nhân vật/địa danh: ngoại hình, xuất thân, chức vụ, đặc điểm nhận diện.
- KHÔNG mô tả hành động nhân vật làm trong chương (VD: "người đã tặng X cho Y" là SAI).
- KHÔNG mô tả mối quan hệ với nhân vật khác trừ khi đó là đặc điểm nhận diện chính (VD: "con trai của X" là OK).
- VÍ DỤ ĐÚNG: "Thiếu niên tóc vàng xuất thân từ khu ổ chuột, có tài năng kiếm thuật"
- VÍ DỤ ĐÚNG: "Hiệp sĩ trẻ tuổi thuộc Đội Diệt Rồng, con trai Công tước Dragulia"
- VÍ DỤ ĐÚNG: "Thành phố cảng phía Tây, trung tâm thương mại quan trọng"
- VÍ DỤ SAI: "Người đã cung cấp thông tin cho nhóm của Vlad" (mô tả hành động, không khách quan)
- VÍ DỤ SAI: "A man who confronts Vlad" (tiếng Anh, mô tả hành động)

Trả về JSON đúng format:
{{
  "entries": [
    {{
      "name_en": "tên tiếng Anh",
      "name_vi": "tên tiếng Việt (hoặc giữ nguyên)",
      "identity": "mô tả khách quan bằng tiếng Việt: ngoại hình, xuất thân, chức vụ",
      "type": "character|faction|location",
      "first_seen": số_chương_xuất_hiện_đầu_tiên
    }}
  ]
}}"""

    client = get_client()
    try:
        response = client.models.generate_content(
            model=TEXT_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                safety_settings=SAFETY_SETTINGS,
                response_mime_type="application/json",
                temperature=0.2,
            )
        )
        glossary = json.loads(response.text)
        with open(GLOSSARY_FILE, "w", encoding="utf-8") as f:
            json.dump(glossary, f, ensure_ascii=False, indent=2)
        entry_count = len(glossary.get("entries", []))
        print(f"[*] Glossary đã lưu: {entry_count} entries")
    except Exception as e:
        print(f"[!] Lỗi tạo glossary: {e}")
        rotate_key()


# ==========================================
# MAIN
# ==========================================
def main():
    print("=" * 50)
    print("=== PHASE 0: PRE-PROCESS ===")
    print("=" * 50)

    # Kiểm tra raw chapters
    if not os.path.exists(RAW_DIR) or len(os.listdir(RAW_DIR)) < 10:
        print("[!] Cần chạy crawl_chapters.py trước để có raw chapters!")
        print(f"    Hiện có: {len(os.listdir(RAW_DIR)) if os.path.exists(RAW_DIR) else 0} files")
        return

    print(f"\n--- Bước 1/4: Extract EPUB ---")
    extract_epub_chapters()

    print(f"\n--- Bước 2/4: Style Guide ---")
    generate_style_guide()

    print(f"\n--- Bước 3/4: Translation Memory ---")
    build_translation_memory()

    print(f"\n--- Bước 4/4: Glossary ---")
    generate_glossary()

    print(f"\n{'=' * 50}")
    print("[*] PRE-PROCESS HOÀN TẤT!")
    print(f"  - Style Guide: {STYLE_GUIDE_FILE}")
    print(f"  - Translation Memory: {TM_FILE}")
    print(f"  - Glossary: {GLOSSARY_FILE}")
    print(f"{'=' * 50}")


if __name__ == "__main__":
    main()
